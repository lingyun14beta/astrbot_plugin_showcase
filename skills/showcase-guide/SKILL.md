---
name: showcase-guide
description: AstrBot Showcase 插件的能力导览。当用户询问 AstrBot 插件能做什么、某个插件扩展点（指令、配置 Schema、事件钩子、i18n、WebUI Page、LLM 工具、多轮会话、定时任务、持久化）怎么用，或询问 /showcase 系列指令与配置项含义时使用。也可用于回答"这个插件为什么有某个字段/钩子"这类问题。
---

# AstrBot 插件能力导览

`astrbot_plugin_showcase` 是一个把 AstrBot 插件扩展点各演示一遍的示例插件。回答用户问题时，
先定位到具体的能力，再给出对应的指令或文件位置，不要泛泛而谈。

## 怎么回答"这个能做什么"

1. 先判断用户问的是**聊天侧**（指令）还是**WebUI 侧**（配置页、插件页面）；
2. 给出可以直接照做的动作，例如"发送 `/showcase wizard` 看多轮会话"；
3. 需要看实现时，指向仓库里的文件（见下面的对照表），不要凭印象描述 AstrBot 的行为。

## 能力与位置对照

| 能力 | 聊天侧入口 | 实现位置 |
| --- | --- | --- |
| 指令组 / 子指令 / 嵌套指令组 / 参数解析 | `/showcase`、`/showcase memo`、`/showcase push` | `main.py` |
| 配置页字段（全部类型与修饰键） | WebUI 插件配置页 | `_conf_schema.json` |
| 14 个事件钩子 | 看日志（配置里勾 `hooks`） | `main.py` |
| i18n（插件信息 / 配置项 / 页面） | `/showcase i18n <locale>` | `.astrbot-plugin/i18n/` |
| LLM 工具（docstring 与类式两种） | `/showcase tools` | `main.py`、`showcase/tools.py` |
| 工具循环、后台任务型工具 | `/showcase agent <任务>` | `main.py`、`showcase/tools.py` |
| 多轮会话 | `/showcase wizard` | `showcase/wizard.py` |
| 定时任务 | `/showcase cron add\|list\|run\|del` | `showcase/cron.py` |
| 主动推送（后台 asyncio 循环） | `/showcase push on\|off\|status` | `showcase/push.py` |
| 会话级状态 vs 插件级状态 | `/showcase memo set\|get\|del` | `main.py` |
| 消息规则（template_list） | `/showcase rules` | `showcase/rules.py` |
| WebUI Page 与后端接口 | 插件详情页里的「能力展示」 | `pages/showcase/`、`main.py` |
| 更新日志约定 | 插件详情页的「更新日志」 | `CHANGELOG.md` |

## 几条容易答错的点

- **配置页渲染由 WebUI 资产版本决定，与 core 版本可以不一致**：旧 WebUI 上某些修饰键会被忽略
  （例如 `secret` 需要 WebUI ≥ 4.28.0，否则字段就是普通文本框）。README 里有完整对照表。
- **`_conf_schema.json` 里 `api_token`、`advanced.rule_limit`、`advanced.debug_dump` 是纯演示字段**，
  不参与插件逻辑，不要把它们说成功能开关。
- **聊天侧文本没有官方的 i18n 取词 API**，本插件的 `/showcase i18n` 是自己读 JSON 实现的；
  回答"插件怎么做多语言"时要说明这一点，不要说 AstrBot 提供了翻译函数。
- **装饰器必须写在插件主模块**（`main.py`）：AstrBot 会用 `star_map[handler.handler_module_path]`
  直接索引元数据，放到子模块会让钩子静默失效。子包里只放不带装饰器的逻辑。
- **插件自带 Skill 放在 `skills/<名字>/SKILL.md`**，在 WebUI 里作为只读来源展示，不能从本地 Skills 页编辑。
