# 更新日志

> 这个文件本身也是本插件演示的仓库约定之一：AstrBot 会在插件详情页读取插件目录下的更新日志，
> 依次尝试 `CHANGELOG.md` → `changelog.md` → `CHANGELOG` → `changelog`（见 `astrbot/dashboard/services/plugin_service.py`
> 的 `get_plugin_changelog`），读取后按 Markdown 渲染。没有这个文件时，插件页会提示「暂无更新日志」。
>
> 约定：发版时让 `metadata.yaml` 的 `version` 与本文档最新一节的标题一致。

## v1.0.0

由 [helloworld 模板](https://github.com/Soulter/helloworld) 改写为「AstrBot 插件能力全景示例」：一个插件把所有扩展点各演示一遍。

### 新增

- **指令**：`/showcase` 指令组（25 个子指令，覆盖配置读取、规则解析、KV、i18n、平台信息、LLM 调用、
  T2I 卡片、消息链、多轮会话、会话历史、主动推送、定时任务、工具管理），以及 `permission_type` /
  `platform_adapter_type` / `regex` / `custom_filter` 四个顶层过滤器示例；保留模板原指令 `/helloworld`
- **配置**：`_conf_schema.json` 覆盖 `bool` / `text` / `string`(+`options`/`labels`/`secret`) / `int` / `float`(+`slider`) /
  `list`(+`render_type: checkbox`) / `dict`(+`template_schema`) / `file`(+`file_types`) / `object`(+`condition`/`invisible`) /
  `template_list`(+`templates`/`display_item`/`hide_hint_in_list`)，以及 `_special: select_provider`、
  `editor_mode` + `editor_language`
- **钩子**：注册全部 14 个事件钩子（`on_astrbot_loaded`、`on_platform_loaded`、`on_plugin_loaded`、`on_plugin_unloaded`、
  `on_plugin_error`、`on_waiting_llm_request`、`on_llm_request`、`on_llm_response`、`on_agent_begin`、`on_agent_done`、
  `on_using_llm_tool`、`on_llm_tool_respond`、`on_decorating_result`、`after_message_sent`），其中
  `on_llm_request` 可按配置注入临时上下文（`extra_user_content_parts` + `mark_as_temp`）、
  `on_decorating_result` 可按配置改写消息链
- **LLM**：`@filter.llm_tool` 函数工具（`showcase_echo`）、类式 `FunctionTool`（`showcase_status`）+
  `context.add_llm_tools()`、后台任务型工具（`is_background_task`，完成后唤醒主 agent）、
  `context.llm_generate` 直调模型、`event.request_llm` 走会话管线、`context.tool_loop_agent` 工具循环、
  `activate/deactivate_llm_tool_async` 运行时启停
- **多轮会话**：`@session_waiter` + `SessionController.keep()/stop()`（`/showcase wizard`，超时可配、`/cancel` 可中止）
- **定时任务**：`context.cron_manager.add_basic_job()` 注册作业并按 cron 表达式推送
  （`/showcase cron add|list|run|del`，演示 `handler(**payload)` 调用约定）
- **主动推送**：`initialize()` 起后台任务 + `context.send_message()` 推送，`terminate()` 里取消
  （`/showcase push on|off|status`，订阅关系存 KV）
- **状态作用域**：`sp.session_*` 会话级 vs 插件 KV vs 全局的对照（`/showcase memo`，嵌套指令组）；
  `event.set_extra/get_extra` 跨 handler 传值（`/showcase extras` + 钩子）
- **会话数据**：`ConversationManager.get_human_readable_context()` 读取当前会话历史（`/showcase history`）
- **其它小 API**：`event.react()`、`event.send_typing()/stop_typing()`、`event.should_call_llm(False)`、
  `event.send_streaming()`（`/showcase stream`）、平台原生调用 `event.bot.api.call_action`
  （`/showcase-recall`，仅 QQ/aiocqhttp）
- **消息**：`At` + `Plain` 消息链构造、`Star.html_render` 渲染 HTML 卡片（T2I）
- **WebUI Page**：`pages/showcase/`（`index.html` + `app.js` + `style.css`），配 4 个 `context.register_web_api` 接口，
  演示 bridge 的 `ready` / `getContext` / `onContext` / `t` / `apiGet` / `apiPost`
- **i18n**：`.astrbot-plugin/i18n/{zh-CN,en-US,ja-JP}.json`，覆盖插件信息、全部配置项文案与页面文案
- **持久化**：KV 存储、插件数据目录、读取配置页上传的文件
- **插件自带 Skill**：`skills/showcase-guide/SKILL.md`，在 WebUI 里作为只读技能来源展示
- **工程结构**：`showcase/` 子包承载实现（规则匹配 / 钩子 / Web API / 定时任务 / 推送 / 向导 / 类式工具），
  `main.py` 只保留被装饰的函数与一行委托 —— 因为 AstrBot 会按 `handler_module_path` 直接索引
  `star_map`，装饰器不能放进子模块（README 有完整说明）
- **测试与 CI**：`tests/test_rules.py`（纯逻辑，不需要 AstrBot）、`tests/test_plugin.py`（集成，环境不具备时自动跳过）、
  `.github/workflows/ci.yml`（ruff + pytest）、`logo.png`、`metadata.yaml` 的市场标签
- **文档**：README（含 core 与 WebUI 两条版本线的能力对照表、进阶扩展点说明、不建议使用的 API 清单）、本更新日志

### 说明

- 支持的 AstrBot 版本为 `>=4.27.3`（`metadata.yaml` 的 `astrbot_version`；下限由运行时启停工具的
  `activate_llm_tool_async` 决定，逐 API 的引入版本依据写在该文件注释里）
- `api_token`、`advanced.rule_limit`、`advanced.debug_dump` 是 Schema 修饰键（`secret` / `condition` / `invisible`）的演示字段，
  不参与插件逻辑，hint 中已注明
- 日志统一走 `astrbot.api.logger`（AstrBot >= 4.26.8 会路由到插件专属 logger，更低版本回退全局 logger）
- 配置页的渲染能力由 WebUI 资产版本决定，可能与 core 版本不一致，对照 README 的版本表
