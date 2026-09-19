"""类式函数工具：手写 JSON Schema 的 ``FunctionTool`` 子类。

与 main.py 里的 ``@filter.llm_tool`` 形成对照：

- 装饰器方式：参数类型写在 docstring 的 ``Args:`` 里，声明成本低，适合快速实现；
- 类式方式：直接给出 JSON Schema，可以精确描述 ``enum``、必填项、嵌套对象，
  并且能把工具做成带状态的实例（这里把插件实例存进 ``plugin`` 字段）。

两种工具注册后都会出现在模型可用的工具列表里：装饰器方式进
``astrbot.core.provider.register.llm_tools``，类式方式进 ``context.add_llm_tools()`` 维护的列表。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


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
