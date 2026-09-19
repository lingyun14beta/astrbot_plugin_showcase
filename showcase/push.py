"""主动推送 + 后台任务示例。

AstrBot 的插件可以自己起后台任务，并用 ``context.send_message(umo, chain)`` 主动往指定会话发消息，
这是「插件主动说话」的标准做法（定时提醒、告警转发、订阅推送都属于这一类）。两个要点：

1. **任务句柄必须自己保存并在 ``terminate()`` 里取消**，否则插件热重载会留下重复的推送循环；
2. **目标会话用 umo（unified_msg_origin）标识并持久化到 KV**，这样重启后订阅关系还在。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain

LOG = "[showcase][push]"
KV_KEY = "push_targets"


class PushService:
    """按固定间隔向所有已订阅会话推送一条消息。

    Attributes:
        plugin: 插件实例，用于读取配置、读写 KV、调用 context.send_message。
        sent: 本次运行累计成功推送的条数。
    """

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.task: asyncio.Task | None = None
        self.sent = 0

    @property
    def running(self) -> bool:
        """推送循环是否正在运行。"""
        return self.task is not None and not self.task.done()

    def start(self) -> bool:
        """启动推送循环，已在运行时返回 False。

        Returns:
            本次是否真的启动了新循环。
        """
        if self.running:
            return False
        self.task = asyncio.create_task(self._loop())
        return True

    async def stop(self) -> None:
        """取消推送循环并等待它退出（插件停用、热重载都会走到这里）。"""
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def subscribe(self, umo: str) -> list[str]:
        """把一个会话加入订阅列表。

        Args:
            umo: 会话的统一消息来源标识。

        Returns:
            去重后的当前订阅列表。
        """
        targets = [t for t in await self.targets() if t != umo]
        targets.append(umo)
        await self.plugin.put_kv_data(KV_KEY, targets)
        return targets

    async def unsubscribe(self, umo: str) -> list[str]:
        """把一个会话移出订阅列表。

        Args:
            umo: 会话的统一消息来源标识。

        Returns:
            移除后的当前订阅列表。
        """
        targets = [t for t in await self.targets() if t != umo]
        await self.plugin.put_kv_data(KV_KEY, targets)
        return targets

    async def targets(self) -> list[str]:
        """读取当前订阅列表。"""
        return list(await self.plugin.get_kv_data(KV_KEY, []) or [])

    async def _loop(self) -> None:
        """推送循环本体，只在被 cancel 时退出。"""
        interval = max(5, int(self.plugin.push_interval))
        try:
            while True:
                await asyncio.sleep(interval)
                for umo in await self.targets():
                    chain = MessageChain().message(
                        f"【showcase 推送】第 {self.sent + 1} 条 · 间隔 {interval}s · "
                        f"{time.strftime('%H:%M:%S')}\n"
                        "发送 /showcase push off 可退订。"
                    )
                    try:
                        if await self.plugin.context.send_message(umo, chain):
                            self.sent += 1
                        else:
                            logger.warning(f"{LOG} 找不到会话，推送失败：{umo}")
                    except Exception as exc:  # 单个会话失败不影响其它会话
                        logger.error(f"{LOG} 推送异常 {umo}: {exc}")
        except asyncio.CancelledError:
            logger.info(f"{LOG} 循环已停止，累计推送 {self.sent} 条")
            raise
