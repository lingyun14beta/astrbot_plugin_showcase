"""类式函数工具：手写 JSON Schema 的 ``FunctionTool`` 子类。

与 main.py 里的 ``@filter.llm_tool`` 形成对照：

- 装饰器方式：参数类型写在 docstring 的 ``Args:`` 里，声明成本低，适合快速实现；
- 类式方式：直接给出 JSON Schema，可以精确描述 ``enum``、必填项、嵌套对象，
  并且能把工具做成带状态的实例（这里把插件实例存进 ``plugin`` 字段）。

两种工具注册后都会出现在模型可用的工具列表里：装饰器方式进
``astrbot.core.provider.register.llm_tools``，类式方式进 ``context.add_llm_tools()`` 维护的列表。
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class ShowcaseStatusTool(FunctionTool[AstrAgentContext]):
    """供模型查询本插件自身状态的工具。

    Attributes:
        plugin: 插件实例，由 main.py 在构造时注入，用于读取运行状态。
    """

    name: str = "showcase_status"
    description: str = (
        "查询 AstrBot Showcase 插件的运行状态：启用了哪些演示项、加载了多少条消息规则、"
        "以及各扩展点被触发的次数。当用户询问这个插件自身的情况时调用。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "要查询的部分：features 查演示项，counters 查触发次数",
                    "enum": ["features", "counters"],
                }
            },
            "required": [],
        }
    )
    plugin: Any = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs: Any
    ) -> ToolExecResult:
        """执行工具。

        Args:
            context: Agent 运行上下文，由 AstrBot 传入。
            **kwargs: 模型按 parameters 给出的参数，这里只用到 section。

        Returns:
            一段供模型继续总结的文本。
        """
        if self.plugin is None:
            return "插件实例不可用，无法查询状态。"
        section = str(kwargs.get("section") or "features")
        if section == "counters":
            return f"扩展点触发次数：{self.plugin.hook_counters_text()}"
        return (
            f"已启用的演示项：{sorted(self.plugin.features)}；"
            f"已加载消息规则：{len(self.plugin.rules)} 条。"
        )


@dataclass
class ShowcaseSlowReportTool(FunctionTool[AstrAgentContext]):
    """后台任务型工具：耗时工作丢到后台，立刻把任务号还给模型。

    ``is_background_task=True`` 时 AstrBot 不会等工具跑完（见
    ``core/astr_agent_tool_exec.py`` 的 ``_execute_background``）：它立刻把
    ``Background task submitted. task_id=...`` 返回给模型，真正的执行在后台任务里进行，
    完成后 AstrBot 会带着结果重新唤醒主 agent。唤醒时的提示语可以用
    ``event.set_extra("background_note", ...)`` 自定义 —— 这里就这么做了。
    """

    name: str = "showcase_slow_report"
    description: str = (
        "生成一份需要等待若干秒的报告，用于演示耗时的后台任务：调用后立即返回任务号，"
        "完成后结果会回到对话里。当用户要求生成报告或明确要求演示后台任务时调用。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "模拟的工作耗时（秒），默认 5，范围 1~60",
                }
            },
            "required": [],
        }
    )
    is_background_task: bool = True
    plugin: Any = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs: Any
    ) -> ToolExecResult:
        """执行工具（运行在后台任务里）。

        Args:
            context: Agent 运行上下文，由 AstrBot 传入；``context.context.event``
                是触发这次对话的事件。
            **kwargs: 模型给出的参数，这里只用到 seconds。

        Returns:
            完成后的报告文本，会被回填给被重新唤醒的主 agent。
        """
        seconds = max(1, min(60, int(kwargs.get("seconds") or 5)))
        # 自定义后台任务完成时的唤醒提示（AstrBot 会读这个 extra）
        try:
            context.context.event.set_extra(
                "background_note", f"后台报告已生成（耗时 {seconds} 秒）"
            )
        except Exception:  # 拿不到 event 时不影响任务本身
            pass
        await asyncio.sleep(seconds)
        return f"报告生成完成：等待了 {seconds} 秒，当前 {self.plugin.hook_counters_text()}。"
