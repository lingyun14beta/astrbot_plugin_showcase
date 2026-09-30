"""插件自带的平台适配器示例（一个不连接任何外部服务的"假平台"）。

AstrBot 允许插件接入官方适配器之外的消息平台（见 ``docs/zh/dev/plugin-platform-adapter.md``）。
本模块演示其中的"注册"这一半，完整链路是：

1. ``@register_platform_adapter`` 把适配器写进 ``platform_registry``
   （``astrbot/core/platform/register.py:58``）；
2. Dashboard 生成配置元数据时遍历这张注册表，把 ``default_config_tmpl`` 并进
   ``platform_group.metadata.platform.config_template``
   （``astrbot/dashboard/services/config_service.py:982-998``），
   而 WebUI「创建机器人 → 消息平台类别」下拉框读的正是这个字段
   （``dashboard/src/components/platform/AddNewPlatform.vue:965-970``）；
3. 用户选中它、填完参数保存后，核心把类实例化并启动 ``run()``
   （``astrbot/core/platform/manager.py:218``）。

两个必须知道的边界：

- 注册发生在 ``import`` 期，没有配置开关能关掉它 —— 插件一旦加载，下拉框里就会出现这一项；
- 插件重载/卸载时会按模块路径前缀注销（``astrbot/core/platform/register.py:66-91``，
  调用点 ``astrbot/core/star/star_manager.py:815``），已经建好的实例会变成一条找不到适配器的悬空配置。

适配器类放在插件根目录而不是 ``showcase/`` 子包，是因为 ``logo_path`` 是相对**适配器类所在文件**
的目录解析的（``config_service.py:1057-1059``）：``logo_path="logo.png"`` 正好指向根目录的图标。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.register import platform_registry

LOG = "[showcase]"
ADAPTER_NAME = "showcase_fake"
"""适配器名，同时也是配置里的 ``type``；不能与内置适配器重名（重名会直接抛 ValueError）。"""

DEFAULT_BOT_NAME = "showcase-bot"
DEMO_USER_ID = "showcase-user"
OUTBOX_LIMIT = 20

# WebUI 生成平台配置表单用的元数据（对应 config_metadata.json 的写法）。
# 不提供的话，WebUI 会把 default_config_tmpl 渲染成裸的键值对编辑框。
CONFIG_METADATA = {
    "token": {
        "description": "任意字符串",
        "type": "string",
        "hint": "假平台不对它做任何校验，只为演示 secret 字段。",
        "secret": True,
        "show_key": True,
    },
    "bot_name": {
        "description": "机器人标识",
        "type": "string",
        "hint": "注入消息时作为 self_id，出现在 /showcase adapter log 里。",
    },
}

# 平台配置表单的多语言文案：给了 i18n_resources 之后，CONFIG_METADATA 里的
# description / hint / labels 会被替换成 platform_group.platform.<适配器名>.<字段>.<键>
# 这样的 i18n key，再由这里提供各语言的取值（见 config_service.py:1106-1129）。
I18N_RESOURCES = {
    "zh-CN": {
        "token": {
            "description": "任意字符串",
            "hint": "假平台不对它做任何校验，只为演示 secret 字段。",
        },
        "bot_name": {
            "description": "机器人标识",
            "hint": "注入消息时作为 self_id，出现在 /showcase adapter log 里。",
        },
    },
    "en-US": {
        "token": {
            "description": "Any string",
            "hint": "The fake platform never validates it; it only demonstrates the secret field.",
        },
        "bot_name": {
            "description": "Bot identity",
            "hint": "Used as self_id for injected messages and shown in /showcase adapter log.",
        },
    },
    "ja-JP": {
        "token": {
            "description": "任意の文字列",
            "hint": "フェイクプラットフォームは検証しません。secret フィールドのデモ用です。",
        },
        "bot_name": {
            "description": "ボットの識別子",
            "hint": "注入したメッセージの self_id になり、/showcase adapter log に表示されます。",
        },
    },
}

# 用户在下拉框里选中本适配器时，表单预填的默认值。
# register_platform_adapter 会自动补上 type / enable / id 三个键（register.py:35-41），
# 其中 enable 默认 False：实例建好后还要在 WebUI 里手动启用才会真正 run()。
DEFAULT_CONFIG = {
    "token": "demo-token",
    "bot_name": DEFAULT_BOT_NAME,
}


@register_platform_adapter(
    ADAPTER_NAME,
    "Showcase 假平台（插件注册的适配器示例）",
    default_config_tmpl=DEFAULT_CONFIG,
    adapter_display_name="Showcase Fake Platform",
    logo_path="logo.png",
    support_streaming_message=False,
    config_metadata=CONFIG_METADATA,
    i18n_resources=I18N_RESOURCES,
)
class ShowcaseFakePlatform(Platform):
    """假平台适配器：收不到任何外部消息，发出的消息全部记在内存里。

    演示用，所以只实现 ``Platform`` 要求的三个方法（``__init__`` / ``run`` / ``meta``），
    真实适配器还要把平台 SDK 的回调转换成 ``AstrBotMessage`` 再 ``commit_event``。
    """

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        # 注意：核心是用三个参数实例化的（manager.py:218），
        # 而 Platform 基类的 __init__ 只接收 config 与 event_queue。
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.bot_name = str(platform_config.get("bot_name") or DEFAULT_BOT_NAME)
        self.token = str(platform_config.get("token") or "")
        self.outbox: deque[str] = deque(maxlen=OUTBOX_LIMIT)
        self.injected = 0
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------
    # Platform 要求实现的方法
    # ------------------------------------------------------------------

    def meta(self) -> PlatformMetadata:
        """返回平台元数据；``id`` 必须是配置里那条实例的 id。"""
        return PlatformMetadata(
            name=ADAPTER_NAME,
            description="Showcase 假平台（插件注册的适配器示例）",
            id=str(self.config.get("id") or ADAPTER_NAME),
            adapter_display_name="Showcase Fake Platform",
            support_streaming_message=False,
        )

    async def run(self) -> None:
        """平台主循环。假平台没有外部连接，等 ``terminate()`` 把事件置位即可。"""
        logger.info(
            f"{LOG} 假平台 {self.meta().id} 已启动（不连接外部服务，等待 terminate）"
        )
        await self._stop.wait()

    async def terminate(self) -> None:
        """停止主循环；核心在停用/删除这条平台配置时会调用。"""
        self._stop.set()
        logger.info(f"{LOG} 假平台 {self.meta().id} 已停止")

    # ------------------------------------------------------------------
    # 供插件指令调用的方法（真实适配器里对应 SDK 的回调）
    # ------------------------------------------------------------------

    def inject(self, text: str) -> str:
        """造一条假的私聊消息丢进事件队列，让它走一遍完整管线。

        Args:
            text: 消息内容。

        Returns:
            这条消息的 unified_msg_origin，可用于 ``context.send_message``。
        """
        abm = AstrBotMessage()
        abm.type = MessageType.FRIEND_MESSAGE
        abm.self_id = self.bot_name
        abm.session_id = DEMO_USER_ID
        abm.message_id = uuid.uuid4().hex[:12]
        abm.sender = MessageMember(user_id=DEMO_USER_ID, nickname=DEMO_USER_ID)
        abm.message_str = text
        abm.message = [Plain(text=text)]
        abm.raw_message = {"text": text, "source": "plugin-injected"}

        event = ShowcaseFakeEvent(
            message_str=text,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            platform=self,
        )
        # commit_event 是 Platform 的公开方法：把事件交给 AstrBot 的事件队列。
        self.commit_event(event)
        self.injected += 1
        return event.unified_msg_origin

    def record_outgoing(self, text: str) -> None:
        """记录一条"发出去"的消息（真实适配器里这一步是调平台 SDK）。"""
        self.outbox.append(text)

    def outbox_text(self) -> str:
        """把 outbox 拼成可读文本，供 /showcase adapter log 输出。"""
        if not self.outbox:
            return f"假平台还没发出过消息（已注入 {self.injected} 条）。"
        lines = [f"假平台发出的最近 {len(self.outbox)} 条消息："]
        lines += [f"  {idx}. {text}" for idx, text in enumerate(self.outbox, 1)]
        return "\n".join(lines)


class ShowcaseFakeEvent(AstrMessageEvent):
    """假平台的事件对象：把回复记进 outbox，再交给父类收尾。

    真实适配器在这里调用平台 SDK 的发送接口；父类的 ``send()`` 负责埋点等公共逻辑，
    因此最后必须 ``await super().send(message)``。
    """

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        platform: ShowcaseFakePlatform,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._platform = platform

    async def send(self, message: MessageChain) -> None:
        for component in message.chain:
            if isinstance(component, Plain):
                self._platform.record_outgoing(component.text)
            else:
                self._platform.record_outgoing(f"<{type(component).__name__}>")
        await super().send(message)


def is_registered() -> bool:
    """适配器是否已在 ``platform_registry`` 里（插件加载后应为 True）。"""
    return any(meta.name == ADAPTER_NAME for meta in platform_registry)
