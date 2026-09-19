"""多轮会话（``@session_waiter``）示例：两轮问答，把两次输入拼成一张摘要。

流程与依赖：

1. 指令 ``/showcase wizard`` 触发 :meth:`ShowcaseWizard.entry`，发第一条提问后 ``await`` 等待会话；
2. 会话期间的后续消息由 AstrBot 内置插件接管 —— ``astrbot/builtin_stars/astrbot/main.py`` 里以最高
   优先级注册的 ``handle_session_control_agent`` 会把命中会话的消息转给 :meth:`ShowcaseWizard.handle`，
   并调用 ``event.stop_event()``，所以向导进行中不会有别的插件或 LLM 插话；
3. :meth:`ShowcaseWizard.handle` 用 ``controller.keep()`` 续下一轮、``controller.stop()`` 结束；
4. 超时由 ``session_waiter(timeout=...)`` 控制，超时后 ``await waiter(event)`` 抛 ``TimeoutError``。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.util import SessionController, session_waiter

LOG = "[showcase][wizard]"
CANCEL_WORDS = {"/cancel", "cancel", "取消", "退出"}


class ShowcaseWizard:
    """两轮问答向导，答案按会话（umo）隔离存放在内存里。

    Attributes:
        plugin: 插件实例，用于读取会话超时配置。
        answers: umo -> 已收集到的答案。
    """

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.answers: dict[str, dict[str, str]] = {}

    async def entry(self, event: Any) -> None:
        """指令入口：发送提问并等待用户输入。

        Args:
            event: 触发指令的消息事件。
        """
        umo = event.unified_msg_origin
        self.answers[umo] = {}
        # session_waiter 的 timeout 在装饰时固定，这里按配置动态创建 waiter。
        waiter = session_waiter(timeout=self.plugin.session_timeout_seconds)(
            self.handle
        )
        await event.send(
            MessageChain().message(
                "【向导】第 1/2 步：随便回一句话，我再问第二个问题。\n"
                "（发送 /cancel 可随时退出）"
            )
        )
        try:
            await waiter(event)
        except TimeoutError:
            self.answers.pop(umo, None)
            await event.send(
                MessageChain().message(
                    f"【向导】{self.plugin.session_timeout_seconds} 秒内没有收到回复，已结束。"
                )
            )

    async def handle(self, controller: SessionController, event: Any) -> None:
        """处理会话期间的每一条消息。

        Args:
            controller: 会话控制器，``keep()`` 续期、``stop()`` 结束。
            event: 用户发来的消息事件。
        """
        umo = event.unified_msg_origin
        text = event.get_message_str().strip()
        state = self.answers.setdefault(umo, {})

        if text in CANCEL_WORDS:
            self.answers.pop(umo, None)
            controller.stop()
            await event.send(MessageChain().message("【向导】已取消。"))
            return

        if "first" not in state:
            state["first"] = text
            controller.keep(
                self.plugin.session_timeout_seconds, reset_timeout=True
            )  # 每一步都重新计时
            await event.send(
                MessageChain().message(
                    "【向导】第 2/2 步：再回一句话，我就把两条拼起来。"
                )
            )
            return

        state["second"] = text
        self.answers.pop(umo, None)
        controller.stop()
        await event.send(
            MessageChain().message(
                f"【向导】收到，汇总如下：\n1. {state['first']}\n2. {state['second']}"
            )
        )
        logger.debug(f"{LOG} 会话完成：{umo}")
