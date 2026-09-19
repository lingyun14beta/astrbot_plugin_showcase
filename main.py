"""AstrBot Showcase —— 把 AstrBot 插件的扩展点挨个演示一遍的示例插件。

覆盖范围（每一项都能在聊天里或 WebUI 里跑通）：
  1. metadata.yaml      —— 插件元数据、支持平台、AstrBot 版本约束
  2. _conf_schema.json  —— WebUI 插件配置页的全部字段类型
  3. 指令               —— 指令组、子指令、别名、参数解析、GreedyStr、权限
  4. 过滤器             —— regex / event_message_type / platform_adapter_type /
                           permission_type / custom_filter
  5. 事件钩子           —— on_llm_request、on_agent_done、after_message_sent 等全部钩子
  6. LLM 工具           —— @filter.llm_tool 函数工具与 context.llm_generate
  7. 消息组件           —— At / Plain 等消息链构造
  8. WebUI Page         —— pages/showcase/ + register_web_api 提供的后端接口
  9. i18n               —— .astrbot-plugin/i18n 的配置项、插件信息与页面文案
 10. 持久化             —— KV 存储与插件数据目录

调试约定：事件钩子只在配置项 `enabled_features` 勾选 "hooks" 时才写日志，方便逐个观察。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, ToolSet, logger, sp
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import error_response, json_response, request
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry
from mcp.types import CallToolResult

from .showcase.cron import CronDemo
from .showcase.push import PushService
from .showcase.rules import fuzzy_hit, invalid_regexes, match_reply
from .showcase.tools import ShowcaseSlowReportTool, ShowcaseStatusTool
from .showcase.wizard import ShowcaseWizard

PLUGIN_NAME = "astrbot_plugin_showcase"
LOG = "[showcase]"
I18N_DIR = Path(__file__).resolve().parent / ".astrbot-plugin" / "i18n"
WEB_API_DISABLED = "插件未启用，或 enabled_features 未勾选 web_api"


class PluginEnabledFilter(filter.CustomFilter):
    """插件总开关过滤器：`enabled=false` 时指令组整体不唤醒。

    AstrBot 只会用 `(raise_error)` 一个参数实例化 CustomFilter，拿不到插件实例，
    因此这里通过 star_map 按模块路径反查已加载的插件对象来读配置。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        metadata = star_map.get(__name__)
        plugin = metadata.star_cls if metadata else None
        return bool(plugin and plugin.enabled)


class FuzzyKeywordFilter(filter.CustomFilter):
    """模糊匹配过滤器：消息里能近似匹配到某个配置关键词时才放行。

    判定逻辑在 ``showcase/rules.py`` 的 :func:`fuzzy_hit` 里（纯函数，可单测）：
    用的是「关键词被消息连续覆盖的比例」而不是「整条消息与关键词的整体相似度」，
    后者在带指令词的消息上会被稀释 —— "/showcase-fuzzy" 与 "showcase" 只有 0.70，
    永远达不到默认阈值 0.75，指令也就永远不会触发。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        metadata = star_map.get(__name__)
        plugin = metadata.star_cls if metadata else None
        if plugin is None:
            return False
        return fuzzy_hit(
            plugin.keywords, event.get_message_str(), plugin.similarity_threshold
        )


class ShowcasePlugin(Star):
    """AstrBot 插件能力全景示例。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        # Star 基类负责初始化 self.context；日志统一走 astrbot.api.logger，
        # 它会按调用方模块自动路由到本插件专属的 logger（低版本回退全局 logger）。
        super().__init__(context, config)
        self.config = config

        # ---- 读取配置：AstrBotConfig 是 dict 子类，缺键时用默认值兜底 ----
        self.enabled = bool(config.get("enabled", True))
        self.greeting = str(config.get("greeting", "") or "")
        self.keywords = [str(k) for k in (config.get("keywords") or [])]
        self.similarity_threshold = float(config.get("similarity_threshold", 0.75))
        self.cooldown_seconds = int(config.get("cooldown_seconds", 5))
        self.features = {str(f) for f in (config.get("enabled_features") or [])}
        self.rules = [r for r in (config.get("rules") or []) if isinstance(r, dict)]

        # 嵌套 object 字段在配置里就是普通 dict，逐层取即可。
        advanced = config.get("advanced") or {}
        self.max_lines = int(advanced.get("max_lines", 10))
        self.strict_mode = bool(advanced.get("strict_mode", False))

        # 新增演示项的配置：主动推送间隔、多轮会话超时、子 agent 指令、
        # cron 表达式、回复前缀、是否注入临时上下文。
        self.push_interval = int(config.get("push_interval_seconds", 60))
        self.session_timeout_seconds = int(config.get("session_timeout_seconds", 30))
        self.agent_instruction = str(config.get("agent_instruction", "") or "")
        self.cron_expression = str(config.get("cron_expression", "") or "*/30 * * * *")
        self.reply_prefix = str(config.get("reply_prefix", "") or "")
        self.inject_context = bool(config.get("inject_context", False))

        # 规则里的无效正则在加载时检查一次，避免每条消息都重复尝试并刷日志。
        for broken in invalid_regexes(self.rules):
            logger.warning(f"{LOG} 正则规则无效，已跳过：{broken!r}")

        # 配置里的日志级别作用到插件自己的 logger。注意：AstrBot >= 4.26.8 才有插件
        # 专属 logger（名字形如 astrbot.plugin.<插件名>）；更低版本 astrbot.api.logger
        # 就是全局 logger，改级别会波及整个 AstrBot，因此只在拿到专属 logger 时设置。
        level_name = str(config.get("log_level", "info")).upper()
        if getattr(logger, "name", "").startswith("astrbot.plugin."):
            logger.setLevel(getattr(logging, level_name, logging.INFO))

        # 持久化：KV 存储（免建表）与插件数据目录（更新/重装插件不会覆盖）。
        # 显式传插件名，避免依赖 get_data_dir() 的调用栈推断。
        self.data_dir = StarTools.get_data_dir(PLUGIN_NAME)

        # 运行期状态：会话冷却时间戳、各钩子调用次数、已发送条数（内存计数，
        # 只在用户主动查看时才落盘，避免每条消息都写一次存储）。
        self._last_ping: dict[str, float] = {}
        self._hook_counts: dict[str, int] = {}
        self._sent_count = 0

        # ---- 子模块里的有状态逻辑（装饰器全留在本文件，见 showcase/__init__.py 的说明）----
        self.push = PushService(self)
        self.wizard = ShowcaseWizard(self)
        self.cron = CronDemo(self)
        # 类式函数工具：手写 JSON Schema，注册进 context 维护的工具列表。
        # 其中慢报告工具声明为 is_background_task，调用后立刻返回任务号。
        self.status_tool = ShowcaseStatusTool(plugin=self)
        self.slow_tool = ShowcaseSlowReportTool(plugin=self)
        if "agent" in self.features:
            context.add_llm_tools(self.status_tool, self.slow_tool)

        # ---- 注册 WebUI Page 用到的后端接口 ----
        # 路由必须带插件名前缀；插件页里 bridge.apiGet("state") 调用时不带前缀。
        context.register_web_api(
            f"/{PLUGIN_NAME}/ping", self.api_ping, ["GET"], "连通性测试"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/state", self.api_state, ["GET"], "插件运行状态"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/commands",
            self.api_commands,
            ["GET"],
            "本插件注册的指令与钩子",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/kv", self.api_kv, ["POST"], "写入一条 KV 记录"
        )
        logger.info(
            f"{LOG} 已加载：features={sorted(self.features)} rules={len(self.rules)}"
        )

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """插件实例化之后、on_plugin_loaded 钩子之前被调用。"""
        logger.info(f"{LOG} initialize(): 数据目录 {self.data_dir}")
        # 主动推送是后台任务：在这里启动，terminate() 里必须取消。
        if self.enabled and "push" in self.features:
            if self.push.start():
                logger.info(f"{LOG} 推送循环已启动，间隔 {self.push_interval}s")

    async def terminate(self) -> None:
        """插件被停用、重载或卸载时被调用。"""
        await self.push.stop()
        total = sum(self._hook_counts.values())
        logger.info(f"{LOG} terminate(): 本次共触发钩子 {total} 次")

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def hook_counters_text(self) -> str:
        """把各扩展点的触发次数拼成一行，供指令与 LLM 工具复用。

        Returns:
            形如 "on_llm_request=3, on_message=5" 的文本，从未触发时返回提示语。
        """
        return (
            ", ".join(f"{k}={v}" for k, v in sorted(self._hook_counts.items()))
            or "（暂无）"
        )

    def _hook(self, name: str, feature: str = "hooks") -> bool:
        """记录一次钩子调用，并返回该扩展点是否在配置中启用。

        Args:
            name: 钩子名，用于计数展示。
            feature: enabled_features 里的开关名，默认 "hooks"。

        Returns:
            配置的 enabled_features 中包含 feature 时为 True。
        """
        self._hook_counts[name] = self._hook_counts.get(name, 0) + 1
        return feature in self.features

    def _t(self, key: str, locale: str = "zh-CN", default: str = "") -> str:
        """按点分路径读取插件自己的 i18n 文案。

        AstrBot 目前只把 `.astrbot-plugin/i18n` 交给 WebUI 使用，没有提供聊天侧取词
        API，因此插件要本地化聊天文本需要自行读取（见 docs 的 plugin-i18n 指南）。

        Args:
            key: 点分路径，如 "pages.showcase.title"。
            locale: 语言代码，取值为 i18n 目录下的文件名。
            default: 找不到时的回退文案。

        Returns:
            命中的字符串；未命中时返回 default。
        """
        try:
            data = json.loads((I18N_DIR / f"{locale}.json").read_text("utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return default
        value: Any = data
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value if isinstance(value, str) else default

    def _match_rules(self, text: str) -> str | None:
        """按配置里的 template_list 规则匹配消息文本。

        算法在 ``showcase/rules.py`` 的 :func:`match_reply` 里（纯函数，可单测）。

        Args:
            text: 已去掉首尾空白的消息文本。

        Returns:
            命中的回复内容；没有规则命中时返回 None。
        """
        return match_reply(self.rules, text)

    # ------------------------------------------------------------------
    # 指令：指令组 / 子指令 / 别名 / 参数解析
    # ------------------------------------------------------------------

    @filter.custom_filter(PluginEnabledFilter, False)
    @filter.command_group("showcase", alias={"展示"})
    def showcase_group(self) -> None:
        """AstrBot 能力展示指令组。"""

    @showcase_group.command("hello")
    async def showcase_hello(self, event: AstrMessageEvent) -> None:
        """回复插件配置里的问候语。"""
        yield event.plain_result(self.greeting or "（greeting 未配置）")

    @showcase_group.command("ping")
    async def showcase_ping(self, event: AstrMessageEvent) -> None:
        """返回 pong，并按配置的 cooldown_seconds 做会话级冷却。"""
        now = time.time()
        umo = event.unified_msg_origin
        remain = self.cooldown_seconds - (now - self._last_ping.get(umo, 0.0))
        if remain > 0:
            yield event.plain_result(f"冷却中，请 {remain:.0f} 秒后再试。")
            return
        self._last_ping[umo] = now
        yield event.plain_result(f"pong（cooldown_seconds={self.cooldown_seconds}）")

    @showcase_group.command("config")
    async def showcase_config(self, event: AstrMessageEvent) -> None:
        """打印配置摘要，演示 object 嵌套读取与 max_lines 限长。"""
        advanced = self.config.get("advanced") or {}
        lines = [
            f"enabled = {self.enabled}",
            f"log_level = {self.config.get('log_level')}",
            f"cooldown_seconds = {self.cooldown_seconds}",
            f"similarity_threshold = {self.similarity_threshold}",
            f"enabled_features = {sorted(self.features)}",
            f"keywords = {self.keywords}",
            f"aliases = {sorted((self.config.get('aliases') or {}).keys())}",
            f"rules = {len(self.rules)} 条",
            f"manual_files = {self.config.get('manual_files') or []}",
            f"chat_provider_id = {self.config.get('chat_provider_id') or '（未配置）'}",
            f"api_token = {'已配置' if self.config.get('api_token') else '未配置'}（secret 字段）",
            f"advanced.max_lines = {self.max_lines}",
            f"advanced.strict_mode = {self.strict_mode}",
            f"advanced.rule_limit = {advanced.get('rule_limit')}（condition 字段，不参与逻辑）",
            f"advanced.debug_dump = {advanced.get('debug_dump')}（invisible 字段）",
            f"cron_expression = {self.cron_expression}",
            f"reply_prefix = {self.reply_prefix or '（未设置）'}",
            f"inject_context = {self.inject_context}",
        ]
        # 行数超过 max_lines 时截断，并把截断本身也展示出来（这正是该字段的用途）。
        shown = lines[: self.max_lines]
        if len(lines) > len(shown):
            shown.append(f"……已截断，共 {len(lines)} 行（max_lines={self.max_lines}）")
        yield event.plain_result("\n".join(shown))

    @showcase_group.command("rules")
    async def showcase_rules(self, event: AstrMessageEvent) -> None:
        """列出 template_list 规则的解析结果。"""
        if not self.rules:
            yield event.plain_result("尚未配置规则（rules），可在插件配置页添加。")
            return
        lines = []
        for rule in self.rules[: self.max_lines]:
            key = rule.get("__template_key", "?")
            if key == "keyword":
                lines.append(
                    f"[keyword] {rule.get('pattern', '')} → {rule.get('reply', '')}"
                )
            elif key == "regex":
                lines.append(
                    f"[regex priority={rule.get('priority', 0)}] "
                    f"{rule.get('expression', '')} → {rule.get('reply', '')}"
                )
            else:
                lines.append(f"[{key}] {rule}")
        broken = invalid_regexes(self.rules)
        if broken:
            lines.append(f"⚠️ 无效正则（已跳过）：{broken}")
        yield event.plain_result("\n".join(lines))

    @showcase_group.command("say")
    async def showcase_say(self, event: AstrMessageEvent, alias: str) -> None:
        """按别名回复 dict 类型配置里的内容。

        Args:
            alias: 配置 aliases 中的键名。
        """
        aliases = self.config.get("aliases") or {}
        if alias not in aliases:
            known = ", ".join(sorted(aliases)) or "（空）"
            yield event.plain_result(f"没有别名 {alias}。已配置：{known}")
            return
        yield event.plain_result(str(aliases[alias]))

    @showcase_group.command("notes")
    async def showcase_notes(self, event: AstrMessageEvent) -> None:
        """读取配置中上传文件的第一行，演示 file 字段与插件数据目录。"""
        files = self.config.get("manual_files") or []
        if not files:
            yield event.plain_result(
                "尚未上传文件（manual_files），可在插件配置页上传。"
            )
            return
        target = self.data_dir / str(files[0])
        try:
            first_line = target.read_text("utf-8", errors="replace").splitlines()[0]
        except (OSError, IndexError) as exc:
            yield event.plain_result(f"读取 {target} 失败：{exc}")
            return
        yield event.plain_result(f"{target.name}：{first_line[:200]}")

    @showcase_group.command("ask")
    async def showcase_ask(self, event: AstrMessageEvent, prompt: GreedyStr) -> None:
        """用配置的模型回答一句话，演示 context.llm_generate。

        Args:
            prompt: 问题文本；GreedyStr 会把剩余全部参数拼起来。
        """
        provider_id = str(self.config.get("chat_provider_id", "") or "").strip()
        if not provider_id:
            yield event.plain_result(
                "未配置「演示用模型」（chat_provider_id），"
                "请先在插件配置里选择一个 Provider。"
            )
            return
        question = str(prompt).strip()
        if not question:
            yield event.plain_result("用法：/showcase ask 你的问题")
            return
        try:
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=question,
                system_prompt="你是 AstrBot 插件能力展示助手，回答控制在三句话以内。",
            )
        except Exception as exc:
            logger.error(f"{LOG} llm_generate 失败: {exc}")
            yield event.plain_result(f"调用模型失败：{exc}")
            return
        yield event.plain_result(resp.completion_text or "（模型没有返回文本）")

    @showcase_group.command("card")
    async def showcase_card(self, event: AstrMessageEvent) -> None:
        """把一段 HTML 渲染成图片发送，演示 Star.html_render（T2I）。"""
        html = (
            "<div style='padding:24px;font-family:sans-serif'>"
            "<h2>AstrBot Showcase</h2>"
            f"<p>插件：{PLUGIN_NAME}</p>"
            f"<p>会话：{event.unified_msg_origin}</p>"
            f"<p>平台：{event.get_platform_name()}</p>"
            "</div>"
        )
        try:
            # return_url=False 拿到的是本地文件路径（渲染层默认值也是 False）；
            # 传 True 会返回渲染端点的 URL，依赖该端点可被聊天平台访问。
            image = await self.html_render(html, {}, return_url=False)
        except Exception as exc:
            logger.warning(f"{LOG} html_render 失败: {exc}")
            yield event.plain_result("T2I 渲染不可用，已跳过。")
            return
        yield event.image_result(image)

    @showcase_group.command("chain")
    async def showcase_chain(self, event: AstrMessageEvent) -> None:
        """构造多组件消息链，演示 message_components。"""
        chain = [
            At(qq=event.get_sender_id(), name=event.get_sender_name() or ""),
            Plain(
                " 这是一条由 At + Plain 组成的消息链。"
                f"平台 {event.get_platform_name()}，"
                f"群 {event.get_group_id() or '私聊'}"
                "（Face / Image / Record 等组件用法相同）。"
            ),
        ]
        yield event.chain_result(chain)

    @showcase_group.command("state")
    async def showcase_state(self, event: AstrMessageEvent) -> None:
        """读写插件 KV 存储并展示钩子调用计数，演示持久化。"""
        counters = self.hook_counters_text()
        if "storage" not in self.features:
            yield event.plain_result(
                f"enabled_features 未勾选 storage，本次不写入 KV。\n"
                f"内存计数：已发送 {self._sent_count} 条\n钩子计数：{counters}"
            )
            return
        record = {
            "umo": event.unified_msg_origin,
            "at": time.strftime("%H:%M:%S"),
            "sent_count": self._sent_count,
        }
        await self.put_kv_data("last_state_call", record)
        stored = await self.get_kv_data("last_state_call", None)
        yield event.plain_result(f"KV last_state_call = {stored}\n钩子计数：{counters}")

    @showcase_group.command("i18n")
    async def showcase_i18n(
        self, event: AstrMessageEvent, locale: str = "zh-CN"
    ) -> None:
        """读取 i18n 文案，演示插件侧国际化。

        Args:
            locale: 语言代码，默认 zh-CN。
        """
        available = ", ".join(sorted(p.stem for p in I18N_DIR.glob("*.json"))) or "无"
        yield event.plain_result(
            f"locale = {locale}\n可用语言 = {available}\n"
            f"metadata.display_name = "
            f"{self._t('metadata.display_name', locale, '（缺失）')}\n"
            f"config.greeting.description = "
            f"{self._t('config.greeting.description', locale, '（缺失）')}\n"
            f"pages.showcase.title = "
            f"{self._t('pages.showcase.title', locale, '（缺失）')}"
        )

    # ------------------------------------------------------------------
    # 小交互 API：表情回应 / 输入状态 / 拦截 LLM
    # ------------------------------------------------------------------

    @showcase_group.command("react")
    async def showcase_react(self, event: AstrMessageEvent) -> None:
        """给触发消息贴一个表情回应，演示 event.react()。"""
        try:
            await event.react("🫡")
        except Exception as exc:  # 并非所有平台都支持表情回应
            yield event.plain_result(f"当前平台不支持表情回应：{exc}")
            return
        yield event.plain_result("已回应 🫡（部分平台会显示为「已读」类反馈）。")

    @showcase_group.command("typing")
    async def showcase_typing(self, event: AstrMessageEvent) -> None:
        """先发「正在输入」再回复，演示 event.send_typing() / stop_typing()。"""
        try:
            await event.send_typing()
            await asyncio.sleep(1.5)
            await event.stop_typing()
        except Exception as exc:  # 支持度依平台而异
            yield event.plain_result(f"当前平台不支持输入状态：{exc}")
            return
        yield event.plain_result("刚才那 1.5 秒是「正在输入」状态。")

    @showcase_group.command("silent")
    async def showcase_silent(self, event: AstrMessageEvent, text: GreedyStr) -> None:
        """只回复指定内容并阻止后续 LLM 处理，演示 event.should_call_llm()。

        Args:
            text: 要回复的文本。
        """
        event.should_call_llm(False)
        yield event.plain_result(
            f"{text}\n（这条消息不会交给模型，已用 should_call_llm(False) 拦下）"
        )

    # ------------------------------------------------------------------
    # 状态管理：嵌套指令组 + sp 的三种作用域
    # ------------------------------------------------------------------

    @showcase_group.group("memo")
    def showcase_memo_group(self) -> None:
        """会话级备忘指令组（嵌套指令组示例）。"""

    @showcase_memo_group.command("set")
    async def showcase_memo_set(
        self, event: AstrMessageEvent, value: GreedyStr
    ) -> None:
        """写入一条会话级备忘（sp.session_put）。

        Args:
            value: 备忘内容，会吃掉剩余全部参数。
        """
        await sp.session_put(event.unified_msg_origin, "memo", str(value))
        yield event.plain_result(
            f"已写入会话级备忘：{value}\n（按 unified_msg_origin 隔离，换个会话读不到）"
        )

    @showcase_memo_group.command("get")
    async def showcase_memo_get(self, event: AstrMessageEvent) -> None:
        """读取会话级备忘，并与插件级 KV 对照。"""
        session_value = await sp.session_get(event.unified_msg_origin, "memo", None)
        plugin_value = await self.get_kv_data("memo", None)
        yield event.plain_result(
            f"会话级（sp.session_get，按 umo 隔离）= {session_value}\n"
            f"插件级（get_kv_data，全插件共享）= {plugin_value}\n"
            f"作用域选择：跟会话走的用前者，跟插件走的用后者。"
        )

    @showcase_memo_group.command("del")
    async def showcase_memo_del(self, event: AstrMessageEvent) -> None:
        """删除会话级备忘（sp.session_remove）。"""
        await sp.session_remove(event.unified_msg_origin, "memo")
        yield event.plain_result("会话级备忘已删除。")

    # ------------------------------------------------------------------
    # LLM 工具：类式工具 + 运行时开关
    # ------------------------------------------------------------------

    @showcase_group.command("tools")
    async def showcase_tools(
        self, event: AstrMessageEvent, action: str = "list"
    ) -> None:
        """列出/启用/停用本插件的 LLM 工具。

        Args:
            action: list（默认）、on 或 off。
        """
        action = action.strip().lower()
        tool_name = self.status_tool.name
        if action in {"on", "off"}:
            if "agent" not in self.features:
                yield event.plain_result(
                    "enabled_features 未勾选 agent，类式工具未注册。"
                )
                return
            if action == "on":
                ok = await self.context.activate_llm_tool_async(tool_name)
            else:
                ok = await self.context.deactivate_llm_tool_async(tool_name)
            yield event.plain_result(
                f"{'启用' if action == 'on' else '停用'} {tool_name}："
                f"{'成功' if ok else '未找到该工具'}"
            )
            return

        tools = self.context.get_llm_tool_manager().func_list
        lines = [
            f"- {t.name}（{'启用' if getattr(t, 'active', True) else '停用'}）"
            for t in tools
        ]
        yield event.plain_result(
            f"当前共 {len(tools)} 个 LLM 工具：\n" + "\n".join(lines[: self.max_lines])
        )

    @showcase_group.command("agent")
    async def showcase_agent(self, event: AstrMessageEvent, prompt: GreedyStr) -> None:
        """让模型在工具循环里自己调用工具，演示 context.tool_loop_agent()。

        Args:
            prompt: 交给模型的任务描述。
        """
        if "agent" not in self.features:
            yield event.plain_result("enabled_features 未勾选 agent。")
            return
        provider_id = str(self.config.get("chat_provider_id", "") or "").strip()
        if not provider_id:
            yield event.plain_result(
                "未配置「演示用模型」（chat_provider_id），请先在插件配置里选择 Provider。"
            )
            return
        instruction = self.agent_instruction or (
            "你是 AstrBot 插件能力展示助手。需要了解插件状态时调用工具，"
            "然后用三句话以内回答。"
        )
        tools = ToolSet()
        tools.add_tool(self.status_tool)
        try:
            resp = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=str(prompt),
                tools=tools,
                system_prompt=instruction,
                max_steps=3,
            )
        except Exception as exc:
            logger.error(f"{LOG} tool_loop_agent 失败: {exc}")
            yield event.plain_result(f"工具循环失败：{exc}")
            return
        yield event.plain_result(resp.completion_text or "（模型没有返回文本）")

    # ------------------------------------------------------------------
    # 主动推送：后台任务 + context.send_message
    # ------------------------------------------------------------------

    @showcase_group.group("push")
    def showcase_push_group(self) -> None:
        """主动推送指令组。"""

    @showcase_push_group.command("on")
    async def showcase_push_on(self, event: AstrMessageEvent) -> None:
        """把当前会话加入推送列表。"""
        if "push" not in self.features:
            yield event.plain_result("enabled_features 未勾选 push。")
            return
        targets = await self.push.subscribe(event.unified_msg_origin)
        if not self.push.running and self.push.start():
            logger.info(f"{LOG} 推送循环已按需启动")
        yield event.plain_result(
            f"已订阅，当前 {len(targets)} 个会话，每 {self.push_interval} 秒推送一条。"
        )

    @showcase_push_group.command("off")
    async def showcase_push_off(self, event: AstrMessageEvent) -> None:
        """把当前会话移出推送列表。"""
        targets = await self.push.unsubscribe(event.unified_msg_origin)
        yield event.plain_result(f"已退订，剩余 {len(targets)} 个会话。")

    @showcase_push_group.command("status")
    async def showcase_push_status(self, event: AstrMessageEvent) -> None:
        """查看推送状态。"""
        targets = await self.push.targets()
        yield event.plain_result(
            f"循环运行中 = {self.push.running}\n"
            f"间隔 = {self.push_interval}s\n"
            f"本轮已推送 = {self.push.sent} 条\n"
            f"订阅会话 = {targets or '（空）'}"
        )

    # ------------------------------------------------------------------
    # 多轮会话：@session_waiter
    # ------------------------------------------------------------------

    @showcase_group.command("wizard")
    async def showcase_wizard(self, event: AstrMessageEvent) -> None:
        """启动两轮问答向导，演示 @session_waiter 多轮会话。"""
        await self.wizard.entry(event)

    @showcase_group.command("pipeline")
    async def showcase_pipeline(
        self, event: AstrMessageEvent, prompt: GreedyStr
    ) -> None:
        """把问题交给 AstrBot 的正常会话管线，演示 event.request_llm()。

        与 /showcase ask（llm_generate 直调）不同：这条路径会带上当前会话的人设、
        工具与历史记录，等同于"用户正常说话时"的处理方式。

        Args:
            prompt: 要问的问题。
        """
        yield event.request_llm(prompt=str(prompt))

    @showcase_group.command("history")
    async def showcase_history(self, event: AstrMessageEvent, count: int = 5) -> None:
        """读取当前会话的历史消息，演示 ConversationManager。

        Args:
            count: 最多显示几条，默认 5。
        """
        umo = event.unified_msg_origin
        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )
        if not conversation_id:
            yield event.plain_result("当前会话还没有对话记录（先聊两句再来）。")
            return
        (
            rows,
            total,
        ) = await self.context.conversation_manager.get_human_readable_context(
            umo, conversation_id, page=1, page_size=max(1, min(count, self.max_lines))
        )
        body = "\n".join(rows) or "（没有可读记录）"
        yield event.plain_result(
            f"会话 {conversation_id[:8]}… 共 {total} 条，最近 {len(rows)} 条：\n{body}"
        )

    @showcase_group.command("extras")
    async def showcase_extras(self, event: AstrMessageEvent, note: GreedyStr) -> None:
        """往当前事件上挂一条 extra，演示 event.set_extra/get_extra。

        extra 挂在事件对象上，同一次事件里的其它 handler（这里是 on_decorating_result）
        能读到它 —— 这是插件之间、插件内部 handler 之间传递信息的方式。

        Args:
            note: 要挂上去的内容。
        """
        event.set_extra("showcase_note", str(note))
        yield event.plain_result(
            f"已把 {note!r} 挂到本次事件上，稍后 on_decorating_result 会读出来。"
        )

    @showcase_group.command("stream")
    async def showcase_stream(self, event: AstrMessageEvent) -> None:
        """分块发送消息，演示 event.send_streaming()（仅部分平台支持）。"""

        async def chunks():
            for index in range(1, 4):
                yield MessageChain().message(f"流式第 {index}/3 块…")
                await asyncio.sleep(0.6)

        try:
            await event.send_streaming(chunks(), use_fallback=True)
        except Exception as exc:
            yield event.plain_result(f"当前平台不支持流式发送：{exc}")
            return
        yield event.plain_result(
            "流式发送结束（官方支持 Telegram、QQ 官方私聊；aiocqhttp 走 fallback）。"
        )

    @showcase_group.group("cron")
    def showcase_cron_group(self) -> None:
        """定时任务指令组，演示 context.cron_manager。"""

    @showcase_cron_group.command("add")
    async def showcase_cron_add(
        self, event: AstrMessageEvent, expression: str = ""
    ) -> None:
        """注册一个 cron 作业，到点往当前会话推送消息。

        Args:
            expression: cron 表达式（分 时 日 月 周），留空则用配置里的 cron_expression。
        """
        cron_expression = expression.strip() or self.cron_expression
        job_id = await self.cron.add(event.unified_msg_origin, cron_expression)
        yield event.plain_result(
            f"已注册作业 {job_id[:8]}…（{cron_expression}）。\n"
            "用 /showcase cron list 查看，/showcase cron run 立刻触发一次。"
        )

    @showcase_cron_group.command("list")
    async def showcase_cron_list(self, event: AstrMessageEvent) -> None:
        """列出本插件注册的 cron 作业。"""
        yield event.plain_result(await self.cron.describe())

    @showcase_cron_group.command("run")
    async def showcase_cron_run(self, event: AstrMessageEvent) -> None:
        """立刻触发一次已注册的作业。"""
        if not await self.cron.run_now():
            yield event.plain_result("还没有作业，先 /showcase cron add。")
            return
        yield event.plain_result("已触发，稍等一下会收到推送。")

    @showcase_cron_group.command("del")
    async def showcase_cron_del(self, event: AstrMessageEvent) -> None:
        """删除本插件注册的作业。"""
        deleted = await self.cron.delete()
        yield event.plain_result("作业已删除。" if deleted else "没有可删除的作业。")

    # ------------------------------------------------------------------
    # 顶层指令：过滤器演示
    # ------------------------------------------------------------------

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent) -> None:
        """原 helloworld 模板指令，保留作为最小可用示例。"""
        yield event.plain_result(
            f"Hello, {event.get_sender_name()}, 你发了 {event.message_str}!"
        )

    @filter.command("showcase-admin")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def showcase_admin(self, event: AstrMessageEvent) -> None:
        """仅管理员可用，演示 permission_type 过滤器。"""
        yield event.plain_result("你是管理员，这条指令只有管理员能触发。")

    @filter.command("showcase-platform")
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def showcase_platform(self, event: AstrMessageEvent) -> None:
        """报告当前平台信息；把 ALL 换成 AIOCQHTTP 等即可限定平台。"""
        yield event.plain_result(
            f"platform_name = {event.get_platform_name()}\n"
            f"unified_msg_origin = {event.unified_msg_origin}\n"
            f"消息类型 = {event.get_message_type()}\n"
            f"是否私聊 = {event.is_private_chat()}，是否管理员 = {event.is_admin()}"
        )

    @filter.regex(r"^showcase-regex\s+(?P<word>\S+)")
    async def showcase_regex(self, event: AstrMessageEvent) -> None:
        """正则监听示例：发送 showcase-regex <词> 触发（不受唤醒前缀限制）。"""
        match = re.search(
            r"^showcase-regex\s+(?P<word>\S+)", event.get_message_str().strip()
        )
        yield event.plain_result(
            f"正则命中，捕获到 {(match.group('word') if match else '')!r}"
        )

    @filter.command("showcase-fuzzy")
    @filter.custom_filter(FuzzyKeywordFilter)
    async def showcase_fuzzy(self, event: AstrMessageEvent) -> None:
        """与配置关键词足够相似时才触发，演示 custom_filter。"""
        yield event.plain_result(
            f"模糊匹配通过（阈值 {self.similarity_threshold}，关键词 {self.keywords}）"
        )

    @filter.command("showcase-recall")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def showcase_recall(self, event: AstrMessageEvent) -> None:
        """撤回触发本条指令的消息，演示平台原生 API（仅 aiocqhttp / QQ 生效）。"""
        message_id = getattr(event.message_obj, "message_id", None)
        if not message_id:
            yield event.plain_result("当前事件里拿不到 message_id，无法撤回。")
            return
        try:
            await event.bot.api.call_action("delete_msg", message_id=message_id)
        except Exception as exc:  # 该适配器或协议端可能不支持撤回
            yield event.plain_result(f"撤回失败：{exc}")
            return
        yield event.plain_result("已撤回你刚才那条消息。")

    # ------------------------------------------------------------------
    # 消息监听 + template_list 规则
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        """监听所有消息并按规则回复，演示 event_message_type 与规则匹配。"""
        if not self.enabled or "message" not in self.features:
            return
        text = event.get_message_str().strip()
        # 指令类消息交给指令处理，避免规则把 /showcase xxx 也吃掉。
        if not text or event.is_at_or_wake_command:
            return

        reply = self._match_rules(text)
        if reply:
            # 默认不拦截后续处理，LLM 仍会再回复一次；想让规则独占这条消息，
            # 在 yield 之前调用 event.stop_event() 即可。
            yield event.plain_result(reply)
            return

        # strict_mode：命中关键词但没有任何规则匹配时给出提示（默认静默）。
        if self.strict_mode and any(
            kw and kw.lower() in text.lower() for kw in self.keywords
        ):
            yield event.plain_result(f"{LOG} 关键词命中，但没有规则匹配这条消息。")

    # ------------------------------------------------------------------
    # LLM 工具：模型可自主调用
    # ------------------------------------------------------------------

    @filter.llm_tool(name="showcase_echo")
    async def showcase_echo_tool(self, event: AstrMessageEvent, text: str) -> str:
        """回显指定文本，用于演示 AstrBot 的函数工具（function calling）。

        Args:
            text(string): 需要回显的文本内容。

        Returns:
            带 [showcase] 前缀的回显结果；返回值会回填给模型继续生成回复。
        """
        if self._hook("llm_tool.showcase_echo", "llm_tool"):
            logger.info(f"{LOG} LLM 工具 showcase_echo 被调用：{text!r}")
        return f"[showcase] {text}"

    # ------------------------------------------------------------------
    # 事件钩子：全部注册一遍，各自只做观察与计数
    # ------------------------------------------------------------------

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self) -> None:
        """AstrBot 整体加载完成时触发。"""
        if not self._hook("on_astrbot_loaded"):
            return
        logger.info(f"{LOG} on_astrbot_loaded")

    @filter.on_platform_loaded()
    async def on_platform_loaded(self) -> None:
        """平台适配器加载完成时触发。"""
        if not self._hook("on_platform_loaded"):
            return
        logger.info(f"{LOG} on_platform_loaded")

    @filter.on_plugin_loaded()
    async def on_plugin_loaded(self, metadata: Any) -> None:
        """任意插件加载完成时触发。

        Args:
            metadata: 被加载插件的 StarMetadata。
        """
        if not self._hook("on_plugin_loaded"):
            return
        logger.debug(f"{LOG} on_plugin_loaded: {getattr(metadata, 'name', '?')}")

    @filter.on_plugin_unloaded()
    async def on_plugin_unloaded(self, metadata: Any) -> None:
        """任意插件卸载完成时触发。

        Args:
            metadata: 被卸载插件的 StarMetadata。
        """
        if not self._hook("on_plugin_unloaded"):
            return
        logger.debug(f"{LOG} on_plugin_unloaded: {getattr(metadata, 'name', '?')}")

    @filter.on_plugin_error()
    async def on_plugin_error(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        handler_name: str,
        error: Exception,
        traceback_text: str,
    ) -> None:
        """插件处理消息抛异常时触发；调用 event.stop_event() 可屏蔽默认报错回显。"""
        if not self._hook("on_plugin_error"):
            return
        logger.warning(
            f"{LOG} on_plugin_error: plugin={plugin_name} "
            f"handler={handler_name} err={error}"
        )

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        """消息确定要调用 LLM、但还没拿到会话锁时触发（可发“思考中”提示）。"""
        if not self._hook("on_waiting_llm_request"):
            return
        logger.debug(f"{LOG} on_waiting_llm_request: {event.unified_msg_origin}")

    @filter.on_llm_request()
    async def on_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """每次 LLM 请求前触发；开启 inject_context 后往请求里注入一条临时上下文。

        用 ``extra_user_content_parts`` + ``mark_as_temp()`` 而不是拼 ``system_prompt``：
        临时片段不会写进历史，也不破坏 system prompt 的缓存前缀。
        """
        if not self._hook("on_llm_request"):
            return
        if self.inject_context:
            req.extra_user_content_parts.append(
                TextPart(
                    text=(
                        f"[showcase] 当前时间 {time.strftime('%Y-%m-%d %H:%M:%S')}，"
                        f"会话 {event.unified_msg_origin}，平台 {event.get_platform_name()}。"
                    )
                ).mark_as_temp()
            )
        logger.debug(
            f"{LOG} on_llm_request: prompt={len(req.prompt or '')} 字, "
            f"contexts={len(req.contexts or [])}, 临时片段={len(req.extra_user_content_parts)}"
        )

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse) -> None:
        """LLM 返回后触发；可读取 reasoning_content、改写 result_chain。"""
        if not self._hook("on_llm_response"):
            return
        logger.debug(f"{LOG} on_llm_response: {len(resp.completion_text or '')} 字")

    @filter.on_agent_begin()
    async def on_agent_begin(
        self, event: AstrMessageEvent, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        """Agent 开始运行时触发。"""
        if not self._hook("on_agent_begin"):
            return
        logger.debug(f"{LOG} on_agent_begin: {event.unified_msg_origin}")

    @filter.on_agent_done()
    async def on_agent_done(
        self,
        event: AstrMessageEvent,
        run_context: ContextWrapper[AstrAgentContext],
        resp: LLMResponse,
    ) -> None:
        """Agent 运行完成后触发。"""
        if not self._hook("on_agent_done"):
            return
        logger.debug(f"{LOG} on_agent_done: {len(resp.completion_text or '')} 字")

    @filter.on_using_llm_tool()
    async def on_using_llm_tool(
        self, event: AstrMessageEvent, tool: FunctionTool, tool_args: dict | None
    ) -> None:
        """调用函数工具之前触发。"""
        if not self._hook("on_using_llm_tool"):
            return
        logger.debug(f"{LOG} on_using_llm_tool: {tool.name} args={tool_args}")

    @filter.on_llm_tool_respond()
    async def on_llm_tool_respond(
        self,
        event: AstrMessageEvent,
        tool: FunctionTool,
        tool_args: dict | None,
        tool_result: CallToolResult | None,
    ) -> None:
        """函数工具返回之后触发。"""
        if not self._hook("on_llm_tool_respond"):
            return
        logger.debug(f"{LOG} on_llm_tool_respond: {tool.name}")

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """消息发送前触发；这里真正改写消息链（不只是记日志）。

        两件事：按配置给所有回复加前缀；把 /showcase extras 挂在事件上的内容追加出来
        （演示同一次事件里不同 handler 之间用 set_extra/get_extra 传信息）。
        """
        if not self._hook("on_decorating_result"):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        if self.reply_prefix:
            result.chain.insert(0, Plain(self.reply_prefix))
        note = event.get_extra("showcase_note")
        if note:
            result.chain.append(Plain(f"\n（event extra：{note}）"))
        logger.debug(
            f"{LOG} on_decorating_result: 处理后 {len(result.chain)} 个组件"
            f"（prefix={bool(self.reply_prefix)}, extra={bool(note)}）"
        )

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """消息真正发出后触发；这里只做内存计数，落盘交给 /showcase state。"""
        if not self._hook("after_message_sent"):
            return
        self._sent_count += 1
        logger.debug(f"{LOG} after_message_sent: 累计已发送 {self._sent_count} 条")

    # ------------------------------------------------------------------
    # WebUI Page 的后端接口（pages/showcase/index.html 通过 bridge 调用）
    # ------------------------------------------------------------------

    async def api_ping(self):
        """GET /ping：最小连通性示例。"""
        if not self.enabled or "web_api" not in self.features:
            return error_response(WEB_API_DISABLED, status_code=403)
        return json_response({"message": "pong", "plugin": PLUGIN_NAME})

    async def api_state(self):
        """GET /state：插件运行状态，供 Page 展示。"""
        if not self.enabled or "web_api" not in self.features:
            return error_response(WEB_API_DISABLED, status_code=403)
        return json_response(
            {
                "plugin_id": self.plugin_id,
                "enabled": self.enabled,
                "features": sorted(self.features),
                "keywords": self.keywords,
                "rules": len(self.rules),
                "greeting_preview": self.greeting[:60],
                "hook_counts": self._hook_counts,
                "sent_count": self._sent_count,
                "locales": sorted(p.stem for p in I18N_DIR.glob("*.json")),
                "data_dir": str(self.data_dir),
                "kv_last": await self.get_kv_data("last_kv", None),
                "secret_configured": bool(self.config.get("api_token")),
                "operator": request.username,
            }
        )

    async def api_commands(self):
        """GET /commands：列出本插件注册的指令与钩子。"""
        if not self.enabled or "web_api" not in self.features:
            return error_response(WEB_API_DISABLED, status_code=403)
        items = [
            {
                "handler": md.handler_name,
                "event_type": getattr(md.event_type, "name", str(md.event_type)),
                "desc": (md.desc or "").splitlines()[0] if md.desc else "",
            }
            for md in star_handlers_registry
            if md.handler_module_path == __name__
        ]
        return json_response({"count": len(items), "handlers": items})

    async def api_kv(self):
        """POST /kv：写入一条 KV 记录并回读，演示 bridge.apiPost。"""
        if not self.enabled or "web_api" not in self.features:
            return error_response(WEB_API_DISABLED, status_code=403)
        if "storage" not in self.features:
            return error_response("enabled_features 未勾选 storage", status_code=403)
        payload = await request.json(default={}) or {}
        record = {
            "value": str(payload.get("value", ""))[:200],
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        await self.put_kv_data("last_kv", record)
        return json_response({"stored": await self.get_kv_data("last_kv", None)})
