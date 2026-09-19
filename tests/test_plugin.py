"""集成测试：需要本机安装 AstrBot（没装时整个文件会被跳过）。

CI 上跑不了这部分（装 AstrBot 太重），所以纯逻辑单测放在 ``tests/test_rules.py``，
这里覆盖"插件能不能被加载、扩展点有没有注册上、各条指令的核心行为对不对"。

本地跑法（在装好 AstrBot 的环境里）：

    pytest tests/test_plugin.py -q
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import tempfile
import types
from pathlib import Path

import pytest

try:  # 没装 AstrBot（或装坏了）时整份文件跳过，纯逻辑测试仍在 tests/test_rules.py 里跑
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.star.star import star_map
    from astrbot.core.star.star_handler import star_handlers_registry
except Exception as exc:  # noqa: BLE001 - 任何导入失败都视为"环境不具备"
    pytest.skip(
        f"需要可用的 AstrBot 环境才能跑集成测试：{exc}", allow_module_level=True
    )

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT.parent))
MODULE = importlib.import_module(f"{PLUGIN_ROOT.name}.main")
MODULE_NAME = MODULE.__name__

SCHEMA = json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))
ALL_FEATURES = ["hooks", "llm_tool", "web_api", "storage", "message", "agent", "push"]


class FakeCronManager:
    """记录 cron 调用，不真的排程。"""

    def __init__(self) -> None:
        self.added: list[dict] = []
        self.ran: list[str] = []
        self.deleted: list[str] = []
        self.jobs: list = []

    async def add_basic_job(self, **kwargs):
        self.added.append(kwargs)
        job = types.SimpleNamespace(
            job_id="job0001abcd",
            name=kwargs["name"],
            cron_expression=kwargs["cron_expression"],
            enabled=True,
        )
        self.jobs.append(job)
        return job

    async def list_jobs(self, job_type=None):
        return list(self.jobs)

    async def run_job_now(self, job_id):
        self.ran.append(job_id)

    async def delete_job(self, job_id):
        self.deleted.append(job_id)
        self.jobs = [job for job in self.jobs if job.job_id != job_id]


class FakeConversationManager:
    def __init__(self) -> None:
        self.cid: str | None = None
        self.rows: list[str] = []
        self.total = 0

    async def get_curr_conversation_id(self, umo):
        return self.cid

    async def get_human_readable_context(
        self, umo, conversation_id, page=1, page_size=10
    ):
        return self.rows[:page_size], self.total


class FakeContext:
    """记录注册动作的假 Context。"""

    def __init__(self) -> None:
        self.web_apis: list[str] = []
        self.tools: list = []
        self.calls: list[tuple[str, str]] = []
        self.outgoing: list[str] = []
        self.manager = types.SimpleNamespace(func_list=[])
        self.cron_manager = FakeCronManager()
        self.conversation_manager = FakeConversationManager()

    def register_web_api(self, route, handler, methods, desc):
        self.web_apis.append(route)

    def add_llm_tools(self, *tools):
        self.tools.extend(tools)

    def get_llm_tool_manager(self):
        return self.manager

    async def activate_llm_tool_async(self, name):
        self.calls.append(("activate", name))
        return True

    async def deactivate_llm_tool_async(self, name):
        self.calls.append(("deactivate", name))
        return True

    async def send_message(self, umo, chain):
        self.outgoing.append(umo)
        return True


class FakeSp:
    """替代 astrbot.api.sp 的内存实现。"""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], object] = {}

    async def session_put(self, umo, key, value):
        self.data[(umo, key)] = value

    async def session_get(self, umo, key, default=None):
        return self.data.get((umo, key), default)

    async def session_remove(self, umo, key):
        self.data.pop((umo, key), None)


class FakeEvent:
    def __init__(self, text: str = "", umo: str = "test:private:m1") -> None:
        self._text = text
        self.unified_msg_origin = umo
        self.message_str = text
        self.reacted: list[str] = []
        self.typing: list[str] = []
        self.llm_flags: list[bool] = []
        self.extras: dict[str, object] = {}
        self.sent: list[str] = []
        self.streamed: list = []
        self.request_kwargs: dict = {}
        self.message_obj = types.SimpleNamespace(message_id=12345)
        self._result = types.SimpleNamespace(chain=[])

    def get_message_str(self) -> str:
        return self._text

    def get_platform_name(self) -> str:
        return "test-platform"

    def plain_result(self, text):
        return text

    def set_extra(self, key, value):
        self.extras[key] = value

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def get_result(self):
        return self._result

    def request_llm(self, **kwargs):
        self.request_kwargs = kwargs
        return "REQUEST_SENTINEL"

    async def react(self, emoji):
        self.reacted.append(emoji)

    async def send_typing(self):
        self.typing.append("start")

    async def stop_typing(self):
        self.typing.append("stop")

    def should_call_llm(self, flag):
        self.llm_flags.append(flag)

    async def send(self, chain):
        self.sent.append(str(chain))

    async def send_streaming(self, generator, use_fallback=False):
        self.streamed = [chunk async for chunk in generator]


def build(features=None, **overrides):
    """按给定特性开关实例化插件，并把 KV 换成内存实现。"""
    config = AstrBotConfig(
        config_path=str(Path(tempfile.mkdtemp()) / "cfg.json"), schema=SCHEMA
    )
    config["enabled_features"] = list(
        features if features is not None else ALL_FEATURES
    )
    for key, value in overrides.items():
        config[key] = value
    context = FakeContext()
    plugin = MODULE.ShowcasePlugin(context=context, config=config)
    star_map[MODULE_NAME].star_cls = plugin
    star_map[MODULE_NAME].name = PLUGIN_ROOT.name

    kv: dict[str, object] = {}

    async def put(key, value):
        kv[key] = value

    async def get(key, default=None):
        return kv.get(key, default)

    async def delete(key):
        kv.pop(key, None)

    plugin.put_kv_data, plugin.get_kv_data, plugin.delete_kv_data = put, get, delete
    return plugin, context


def collect(handler):
    """把指令 handler 的产出收集成列表（兼容 async generator 与 coroutine）。"""
    if hasattr(handler, "__anext__"):

        async def run():
            return [item async for item in handler]

    else:

        async def run():
            return [await handler]

    return asyncio.run(run())


# ---------------- 注册面 ----------------


def test_web_api_路由已注册():
    _, context = build()
    assert context.web_apis == [
        f"/{PLUGIN_ROOT.name}/ping",
        f"/{PLUGIN_ROOT.name}/state",
        f"/{PLUGIN_ROOT.name}/commands",
        f"/{PLUGIN_ROOT.name}/kv",
    ]


def test_勾选agent时注册类式工具():
    _, context = build()
    assert [tool.name for tool in context.tools] == [
        "showcase_status",
        "showcase_slow_report",
    ]


def test_后台任务型工具的声明():
    plugin, _ = build()
    assert plugin.slow_tool.is_background_task is True
    assert plugin.status_tool.is_background_task is False


def test_未勾选agent时不注册类式工具():
    _, context = build(["hooks"])
    assert context.tools == []


def test_所有handler都在主模块注册():
    names = {
        md.handler_name
        for md in star_handlers_registry
        if md.handler_module_path == MODULE_NAME
    }
    for expected in (
        "showcase_hello",
        "showcase_wizard",
        "showcase_push_on",
        "showcase_recall",
        "showcase_cron_add",
        "showcase_pipeline",
        "showcase_history",
    ):
        assert expected in names
    # 子模块里不允许出现被装饰的 handler（star_map 索引会找不到）
    others = [
        md.handler_name
        for md in star_handlers_registry
        if md.handler_module_path != MODULE_NAME
        and md.handler_module_path.startswith(PLUGIN_ROOT.name)
    ]
    assert others == []


# ---------------- 配置与 i18n ----------------


def test_读取配置与默认值():
    plugin, _ = build()
    assert plugin.enabled is True
    assert plugin.cooldown_seconds == 5
    assert plugin.session_timeout_seconds == 30
    assert plugin.push_interval == 60
    assert plugin.max_lines == 20
    assert plugin.cron_expression == "*/30 * * * *"
    assert plugin.reply_prefix == ""
    assert plugin.inject_context is False


def test_配置摘要行数与截断():
    plugin, _ = build()
    plugin.config["advanced"]["max_lines"] = 20
    plugin.max_lines = 20
    full = str(collect(plugin.showcase_config(FakeEvent()))[0])
    assert "已截断" not in full
    assert "advanced.rule_limit" in full
    assert "cron_expression" in full

    plugin, _ = build()
    plugin.config["advanced"]["max_lines"] = 5
    plugin.max_lines = 5
    short = str(collect(plugin.showcase_config(FakeEvent()))[0])
    assert "已截断" in short
    assert len(short.splitlines()) == 6  # 5 行正文 + 1 行截断提示


@pytest.mark.parametrize("locale", ["zh-CN", "en-US", "ja-JP"])
def test_i18n取词(locale):
    plugin, _ = build()
    assert plugin._t("metadata.display_name", locale, "缺") != "缺"
    assert plugin._t("pages.showcase.title", locale, "缺") != "缺"


def test_i18n缺失时回退():
    plugin, _ = build()
    assert plugin._t("metadata.display_name", "xx-XX", "回退值") == "回退值"


# ---------------- 指令行为 ----------------


def test_小交互API():
    plugin, _ = build()
    event = FakeEvent()
    collect(plugin.showcase_react(event))
    assert event.reacted == ["🫡"]

    event = FakeEvent()
    collect(plugin.showcase_silent(event, "只回这一句"))
    assert event.llm_flags == [False]


def test_会话级状态与插件级状态隔离():
    plugin, _ = build()
    MODULE.sp = FakeSp()
    try:
        collect(plugin.showcase_memo_set(FakeEvent("买牛奶", umo="u1"), "买牛奶"))
        assert MODULE.sp.data[("u1", "memo")] == "买牛奶"
        other = str(collect(plugin.showcase_memo_get(FakeEvent(umo="u2")))[0])
        assert "None" in other
        collect(plugin.showcase_memo_del(FakeEvent(umo="u1")))
        assert ("u1", "memo") not in MODULE.sp.data
    finally:
        MODULE.sp = importlib.import_module("astrbot.api").sp


def test_工具运行时开关():
    plugin, context = build()
    context.manager.func_list = [plugin.status_tool]
    collect(plugin.showcase_tools(FakeEvent(), "off"))
    assert context.calls == [("deactivate", "showcase_status")]


def test_推送订阅与退订():
    async def flow():
        plugin, _ = build(push_interval_seconds=30)
        event = FakeEvent(umo="test:private:P")
        await plugin.showcase_push_on(event).__anext__()
        targets = await plugin.push.targets()
        running = plugin.push.running
        await plugin.push.stop()
        return targets, running

    targets, running = asyncio.run(flow())
    assert targets == ["test:private:P"]
    assert running is True


def test_向导状态机():
    plugin, _ = build(session_timeout_seconds=15)
    controller = types.SimpleNamespace(kept=[], stopped=False)
    controller.keep = lambda timeout=0, reset_timeout=False: controller.kept.append(
        (timeout, reset_timeout)
    )
    controller.stop = lambda error=None: setattr(controller, "stopped", True)

    asyncio.run(plugin.wizard.handle(controller, FakeEvent("第一句", umo="u1")))
    assert controller.kept == [(15, True)]
    assert controller.stopped is False

    asyncio.run(plugin.wizard.handle(controller, FakeEvent("第二句", umo="u1")))
    assert controller.stopped is True


def test_agent未配置模型时给出提示():
    plugin, _ = build()
    out = str(collect(plugin.showcase_agent(FakeEvent(), "查询状态"))[0])
    assert "chat_provider_id" in out


def test_模糊过滤器对指令本身放行():
    plugin, _ = build()
    filter_instance = MODULE.FuzzyKeywordFilter()
    assert filter_instance.filter(FakeEvent("/showcase-fuzzy"), None) is True
    assert filter_instance.filter(FakeEvent("hello world"), None) is False


def test_消息规则命中与未命中():
    plugin, _ = build(
        rules=[{"__template_key": "keyword", "pattern": "报时", "reply": "现在是整点"}]
    )
    assert plugin._match_rules("帮我报时") == "现在是整点"
    assert plugin._match_rules("随便说说") is None


def test_pipeline交给会话管线():
    plugin, _ = build()
    event = FakeEvent()
    assert collect(plugin.showcase_pipeline(event, "你好")) == ["REQUEST_SENTINEL"]
    assert event.request_kwargs["prompt"] == "你好"


def test_history读取对话上下文():
    plugin, context = build()
    context.conversation_manager.cid = "cid-12345678"
    context.conversation_manager.rows = ["User: 你好", "Assistant: 你好呀"]
    context.conversation_manager.total = 2
    out = str(collect(plugin.showcase_history(FakeEvent()))[0])
    assert "User: 你好" in out
    assert "共 2 条" in out


def test_history无会话时给出提示():
    plugin, _ = build()
    out = str(collect(plugin.showcase_history(FakeEvent()))[0])
    assert "还没有对话记录" in out


def test_extras与钩子改写消息链():
    from astrbot.api.message_components import Plain

    plugin, _ = build(reply_prefix="【前缀】")
    event = FakeEvent()
    collect(plugin.showcase_extras(event, "附加说明"))
    assert event.get_extra("showcase_note") == "附加说明"

    event.get_result().chain.append(Plain("正文"))
    asyncio.run(plugin.on_decorating_result(event))
    texts = [getattr(component, "text", "") for component in event.get_result().chain]
    assert texts[0] == "【前缀】"
    assert any("附加说明" in text for text in texts)


def test_按需注入临时上下文():
    plugin, _ = build(inject_context=True)
    req = types.SimpleNamespace(prompt="hi", contexts=[], extra_user_content_parts=[])
    asyncio.run(plugin.on_llm_request(FakeEvent(), req))
    assert len(req.extra_user_content_parts) == 1

    plugin, _ = build()
    req2 = types.SimpleNamespace(prompt="hi", contexts=[], extra_user_content_parts=[])
    asyncio.run(plugin.on_llm_request(FakeEvent(), req2))
    assert req2.extra_user_content_parts == []


def test_cron注册执行与删除():
    async def flow():
        plugin, context = build()
        job_id = await plugin.cron.add("test:private:C", "*/5 * * * *")
        listing = await plugin.cron.describe()
        ran = await plugin.cron.run_now()
        deleted = await plugin.cron.delete()
        return job_id, listing, ran, deleted, context

    job_id, listing, ran, deleted, context = asyncio.run(flow())
    manager = context.cron_manager
    assert manager.added[0]["cron_expression"] == "*/5 * * * *"
    assert manager.added[0]["payload"] == {"umo": "test:private:C"}
    assert "showcase-test:private:C" in listing
    assert ran is True and manager.ran == [job_id]
    assert deleted is True and manager.deleted == [job_id]


def test_cron回调按payload推送():
    async def flow():
        plugin, context = build()
        await plugin.cron.add("test:private:C", "*/5 * * * *")
        handler = context.cron_manager.added[0]["handler"]
        # CronJobManager 的调用约定是 handler(**payload)
        await handler(**context.cron_manager.added[0]["payload"])
        return context

    context = asyncio.run(flow())
    assert context.outgoing == ["test:private:C"]


def test_流式发送():
    plugin, _ = build()
    event = FakeEvent()
    collect(plugin.showcase_stream(event))
    assert len(event.streamed) == 3
