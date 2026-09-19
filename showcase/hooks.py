"""14 个事件钩子的实现。

**装饰器必须留在 main.py**：AstrBot 在 10 处直接索引 ``star_map[handler.handler_module_path]``
（通用钩子派发 ``core/pipeline/context_utils.py``、``core/core_lifecycle.py``、``core/star/star_manager.py``
的插件加载/卸载、``core/pipeline/result_decorate/stage.py``、``core/platform/manager.py`` 等），
而 ``star_map`` 只为「定义了 Star 子类的模块」建条目 —— 也就是插件主模块。把被装饰的函数放到子模块里，
轻则钩子被跳过（异常被吞掉，只在日志里留一条 traceback），重则在 ``context_utils.py`` 里
KeyError 冒泡进管线。

所以 main.py 里保留「装饰器 + 一行委托」，实现放在这里 —— 和官方内置插件把指令实现放进
``commands/`` 是同一个套路。
"""

from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from mcp.types import CallToolResult

LOG = "[showcase]"


class ShowcaseHooks:
    """所有钩子的实现，由 main.py 的装饰器方法委托过来。

    大部分钩子只做观察与计数（``count_hook`` 返回 False 时直接跳过），
    其中两个按配置真的干活：``on_llm_request`` 注入临时上下文、``on_decorating_result`` 改写消息链。

    Attributes:
        plugin: 插件实例，用于读配置、计数与记录日志。
    """

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    async def on_astrbot_loaded(self) -> None:
        """AstrBot 整体加载完成时触发。"""
        if not self.plugin.count_hook("on_astrbot_loaded"):
            return
        logger.info(f"{LOG} on_astrbot_loaded")

    async def on_platform_loaded(self) -> None:
        """平台适配器加载完成时触发。"""
        if not self.plugin.count_hook("on_platform_loaded"):
            return
        logger.info(f"{LOG} on_platform_loaded")

    async def on_plugin_loaded(self, metadata: Any) -> None:
        """任意插件加载完成时触发。

        Args:
            metadata: 被加载插件的 StarMetadata。
        """
        if not self.plugin.count_hook("on_plugin_loaded"):
            return
        logger.debug(f"{LOG} on_plugin_loaded: {getattr(metadata, 'name', '?')}")

    async def on_plugin_unloaded(self, metadata: Any) -> None:
        """任意插件卸载完成时触发。

        Args:
            metadata: 被卸载插件的 StarMetadata。
        """
        if not self.plugin.count_hook("on_plugin_unloaded"):
            return
        logger.debug(f"{LOG} on_plugin_unloaded: {getattr(metadata, 'name', '?')}")

    async def on_plugin_error(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        handler_name: str,
        error: Exception,
        traceback_text: str,
    ) -> None:
        """插件处理消息抛异常时触发；调用 event.stop_event() 可屏蔽默认报错回显。"""
        if not self.plugin.count_hook("on_plugin_error"):
            return
        logger.warning(
            f"{LOG} on_plugin_error: plugin={plugin_name} "
            f"handler={handler_name} err={error}"
        )

    async def on_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        """消息确定要调用 LLM、但还没拿到会话锁时触发（可发“思考中”提示）。"""
        if not self.plugin.count_hook("on_waiting_llm_request"):
            return
        logger.debug(f"{LOG} on_waiting_llm_request: {event.unified_msg_origin}")

    async def on_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """每次 LLM 请求前触发；开启 inject_context 后往请求里注入一条临时上下文。

        用 ``extra_user_content_parts`` + ``mark_as_temp()`` 而不是拼 ``system_prompt``：
        临时片段不会写进历史，也不破坏 system prompt 的缓存前缀。
        """
        if not self.plugin.count_hook("on_llm_request"):
            return
        if self.plugin.inject_context:
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

    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse) -> None:
        """LLM 返回后触发；可读取 reasoning_content、改写 result_chain。"""
        if not self.plugin.count_hook("on_llm_response"):
            return
        logger.debug(f"{LOG} on_llm_response: {len(resp.completion_text or '')} 字")

    async def on_agent_begin(
        self, event: AstrMessageEvent, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        """Agent 开始运行时触发。"""
        if not self.plugin.count_hook("on_agent_begin"):
            return
        logger.debug(f"{LOG} on_agent_begin: {event.unified_msg_origin}")

    async def on_agent_done(
        self,
        event: AstrMessageEvent,
        run_context: ContextWrapper[AstrAgentContext],
        resp: LLMResponse,
    ) -> None:
        """Agent 运行完成后触发。"""
        if not self.plugin.count_hook("on_agent_done"):
            return
        logger.debug(f"{LOG} on_agent_done: {len(resp.completion_text or '')} 字")

    async def on_using_llm_tool(
        self, event: AstrMessageEvent, tool: FunctionTool, tool_args: dict | None
    ) -> None:
        """调用函数工具之前触发。"""
        if not self.plugin.count_hook("on_using_llm_tool"):
            return
        logger.debug(f"{LOG} on_using_llm_tool: {tool.name} args={tool_args}")

    async def on_llm_tool_respond(
        self,
        event: AstrMessageEvent,
        tool: FunctionTool,
        tool_args: dict | None,
        tool_result: CallToolResult | None,
    ) -> None:
        """函数工具返回之后触发。"""
        if not self.plugin.count_hook("on_llm_tool_respond"):
            return
        logger.debug(f"{LOG} on_llm_tool_respond: {tool.name}")

    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """消息发送前触发；这里真正改写消息链（不只是记日志）。

        两件事：按配置给所有回复加前缀；把 /showcase extras 挂在事件上的内容追加出来
        （演示同一次事件里不同 handler 之间用 set_extra/get_extra 传信息）。
        """
        if not self.plugin.count_hook("on_decorating_result"):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        if self.plugin.reply_prefix:
            result.chain.insert(0, Plain(self.plugin.reply_prefix))
        note = event.get_extra("showcase_note")
        if note:
            result.chain.append(Plain(f"\n（event extra：{note}）"))
        logger.debug(
            f"{LOG} on_decorating_result: 处理后 {len(result.chain)} 个组件"
            f"（prefix={bool(self.plugin.reply_prefix)}, extra={bool(note)}）"
        )

    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """消息真正发出后触发；这里只做内存计数，落盘交给 /showcase state。"""
        if not self.plugin.count_hook("after_message_sent"):
            return
        self.plugin.sent_count += 1
        logger.debug(
            f"{LOG} after_message_sent: 累计已发送 {self.plugin.sent_count} 条"
        )
