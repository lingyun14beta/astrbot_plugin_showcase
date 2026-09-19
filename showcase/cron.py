"""AstrBot 自带的定时任务（cron）示例。

比"自己起 ``asyncio`` 循环"更适合做周期性工作：cron 表达式表达力更强、任务能在 WebUI 里看到、
还能立即手动执行一次。三个要点：

1. **handler 的调用方式是 ``handler(**payload)```**（见 ``core/cron/manager.py``），
   所以处理函数的参数名必须和 payload 的 key 对上；
2. **handler 只存在内存里**：``persistent=True`` 的作业重启后仍在数据库里，但 handler 需要重新注册；
   本示例用默认的非持久化作业，避免出现"任务还在、处理函数没了"的空转；
3. **job_id 建议自己存一份**（这里存 KV），方便列出与删除。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain

LOG = "[showcase][cron]"
KV_KEY = "cron_job_id"


class CronDemo:
    """演示插件注册 cron 作业：添加 / 列出 / 立即执行 / 删除。

    Attributes:
        plugin: 插件实例，用于拿 context.cron_manager、读写 KV。
        fired: 本次运行中作业被触发的次数。
    """

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.fired = 0

    async def add(self, umo: str, expression: str) -> str:
        """注册一个作业：到点后往指定会话推送一条消息。

        Args:
            umo: 会话标识，作业触发时推送到这里。
            expression: cron 表达式（分 时 日 月 周，或带秒的 6 段式）。

        Returns:
            新建作业的 job_id。
        """
        job = await self.plugin.context.cron_manager.add_basic_job(
            name=f"showcase-{umo}",
            cron_expression=expression,
            handler=self.on_fire,
            description="AstrBot Showcase 的 cron 示例作业",
            payload={"umo": umo},
        )
        await self.plugin.put_kv_data(KV_KEY, job.job_id)
        return job.job_id

    async def on_fire(self, umo: str = "") -> None:
        """作业到点时的回调；参数名与 payload 的 key 一致。

        Args:
            umo: 要推送到的会话。
        """
        self.fired += 1
        logger.info(f"{LOG} 作业触发第 {self.fired} 次 -> {umo}")
        if not umo:
            return
        await self.plugin.context.send_message(
            umo,
            MessageChain().message(
                f"【showcase cron】第 {self.fired} 次触发。"
                "发送 /showcase cron del 可删除这个作业。"
            ),
        )

    async def describe(self) -> str:
        """列出本插件注册的作业，供指令回显。

        Returns:
            多行文本，每行一个作业。
        """
        jobs = await self.plugin.context.cron_manager.list_jobs()
        mine = [j for j in jobs if str(getattr(j, "name", "")).startswith("showcase-")]
        if not mine:
            return "当前没有本插件注册的 cron 作业。"
        lines = []
        for job in mine:
            job_id = getattr(job, "job_id", "?")
            lines.append(
                f"- {getattr(job, 'name', '?')} | {getattr(job, 'cron_expression', '?')} "
                f"| enabled={getattr(job, 'enabled', '?')} | id={job_id[:8]}"
            )
        return "\n".join(lines)

    async def run_now(self) -> bool:
        """立即执行一次已注册的作业。

        Returns:
            是否找到了作业并触发。
        """
        job_id = await self.plugin.get_kv_data(KV_KEY, None)
        if not job_id:
            return False
        await self.plugin.context.cron_manager.run_job_now(str(job_id))
        return True

    async def delete(self) -> bool:
        """删除本插件注册的作业。

        Returns:
            是否真的删掉了一个作业。
        """
        job_id = await self.plugin.get_kv_data(KV_KEY, None)
        if not job_id:
            return False
        await self.plugin.context.cron_manager.delete_job(str(job_id))
        await self.plugin.delete_kv_data(KV_KEY)
        return True
