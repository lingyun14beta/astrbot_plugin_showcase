# 更新日志

> 这个文件本身也是本插件演示的仓库约定之一：AstrBot 会在插件详情页读取插件目录下的更新日志，
> 依次尝试 `CHANGELOG.md` → `changelog.md` → `CHANGELOG` → `changelog`（见 `astrbot/dashboard/services/plugin_service.py`
> 的 `get_plugin_changelog`），读取后按 Markdown 渲染。没有这个文件时，插件页会提示「暂无更新日志」。
>
> 约定：发版时让 `metadata.yaml` 的 `version` 与本文档最新一节的标题一致。

## v1.4.0

把 4.29 新增的「配置页能力」也补齐：样式按钮、`subtitles`、`_special: umo` / `sender_id`、`collapsed`。

### 新增

- **四种按钮样式**：`/showcase button` 改成两排——第一排 `default` / `primary` / `success` / `danger` 各一个
  （共用 `@filter.button_action()` 通配处理器，按 `showcase:style:` 前缀过滤），第二排是原来的「确认 / 文档」
- **`subtitles`**（WebUI 4.29.1+）：`log_level` 的四个下拉选项各带一句副标题
- **`_special: umo`**（4.29.4+）：`demo_umo`，配置页弹「选择会话来源」，保存完整 UMO 字符串
- **`_special: sender_id`**（4.29.4+）：`demo_sender`，配置页弹「选择用户」，保存用户 ID 列表
- **`collapsed: true`**（4.30 线，PR #11067）：`advanced` 分组默认收起；4.29.4 上会被忽略
- `/showcase config` 回显这三个新字段（`demo_umo` / `demo_sender` / `advanced.collapsed`），摘要从 18 行变成 21 行
- 文档：按钮小节补「四种样式 × 各平台映射」表、通配处理器与 ID 唯一性说明；配置表、4.29 能力表同步

### 说明

- 新增的三个 Schema 能力都是**只演示、不参与逻辑**，值只在 `/showcase config` 回显
- `collapsed` 属于未发版的 4.30 线，写进 Schema 不会影响 4.29.4 的渲染（该键被忽略）
- 版本下限仍是 `>=4.29.4`（交互按钮），`dev` 分支继续维持 `>=4.27.3`

## v1.3.0

新增「交互按钮」演示（`feat/buttons` 分支）：`/showcase button` 发一排按钮，`@filter.button_action` 收点击。

### 新增

- **指令**：`/showcase button` —— 一个回调按钮（`showcase:confirm`）+ 一个链接按钮（文档），带 `action_timeout=120`
  与 `fallback_text`
- **回调**：`@filter.button_action("showcase:confirm")` handler，回复里回显 `action_id` / `data` / `source_message_id`，
  演示 `event.get_button_interaction()` 的用法
- **文档**：README 新增「交互按钮」小节（组件用法、过期语义、各平台支持度、QQ 官方的 5×5 与 1024 字节限制）
- **测试**：消息链里确实是 `ActionRow` + 两个 `Button`（含超时与回退文案）、回调 handler 的输出内容

### 说明

- **本分支 `astrbot_version` 从 `>=4.27.3` 抬到 `>=4.29.4`**：交互按钮是 4.29.4 才加的能力，4.27/4.28 上无法加载
- `dev` 分支保持 `>=4.27.3` 且不含按钮演示，两条线功能其余部分一致
- 平台支持度：QQ 官方机器人 / Telegram / 飞书 / 钉钉 / Discord / Slack / LINE / KOOK / Satori / 企业微信 / WebChat 支持回调；
  OneBot v11、Misskey、公众号、微信个人号只做文字回退

## v1.2.0

对齐 AstrBot **4.29.4**（master 上已含未发版的 4.30 线改动）核对一遍文档结论：代码不用改，改的是过期的说法。

### 修正

- **`pages` → `views`**（4.29.0，PR #10307）：`views/` 目录与 `window.AstrBotPluginView` 是首选名，
  `pages/`、`window.AstrBotPluginPage`、`pages.<名字>.*` 文案、`/plugins/pages` 路由都保留为别名；
  `metadata.yaml` 的 `views:`/`pages:` 会被解析进 `StarMetadata.views`，但页面发现仍靠目录扫描。
  本插件继续用 `pages/` + 旧 bridge 名，以兼容 4.27/4.28（README 里写明了迁移方法）
- **star_map 约束的论据更新**：4.29 起通用钩子派发改用 `star_map.get(...)`（`context_utils.py:105-106`），
  子模块里的钩子不再必然静默失效；但 `on_decorating_result`、`on_platform_loaded`、`on_astrbot_loaded`、
  唤醒检查与工具启用校验仍直接索引 `star_map[...]`，结论（装饰器放主模块）不变，措辞改为按钩子区分
- **`register_agent` 结论反转**：4.29.4 里 core 自己就在用（`follow_up.py`、`active_event_registry.py` 与单测），
  不再是"只有定义没人用"；未发版的 4.30 线新增 `astrbot.api.agents` 与 `context.agent`，
  `context.subagent_orchestrator` 已被移除
- **配置页修饰键**：`full_width` 插件配置页也支持了（插件配置页已走共享的 `ConfigItemRenderer.vue`）；
  `collapsed` 从 4.30 线起支持；只有 `items_type` 仍然没人读
- **行号与版本号**：`Star.html_render` 实现移到 `core/star/base.py:104`（另可用 `context.html_renderer`）；
  `serialize_plugin_base` 637→634、`create_bot` 1432→1442、平台实例化 218→237、
  `AddNewPlatform.vue` 965→891、`context.get_platform` 778→824 等引用全部重挂
- **新增参考表**：4.29/4.30 新增的扩展点（交互按钮、`subtitles`、`_special: umo`/`sender_id`、
  `context.agent`、`context.conversations`、`collapsed`、`run_end_reason`）列进 README 第九节，
  标注了引入版本与"未发版"状态，方便按需取用

### 说明

- 版本下限仍是 `>=4.27.3`；只有真要演示交互按钮时才需要抬到 `>=4.29.4`
- 在 AstrBot 4.29.4（master，含 4.30 线改动）上跑过：`ruff check` / `ruff format --check` 通过，
  `pytest` 55 项全过

## v1.1.0

新增「插件注册平台适配器」演示：一个不连接外部服务的假平台 `showcase_fake`。

### 新增

- **平台适配器**（`platform_demo.py`）：`@register_platform_adapter` 注册新平台类型，配置里演示
  `default_config_tmpl` / `config_metadata`（表单字段）/ `i18n_resources`（表单文案多语言）/ `logo_path`
  （插件目录内的图标）/ `support_streaming_message`；实现 `Platform` 的 `__init__` / `run` / `meta`
  与消息事件子类 `AstrMessageEvent.send()`
- **指令**：`/showcase adapter status`（注册与实例状态 + WebUI 创建步骤）、
  `/showcase adapter inject <文本>`（造一条假私聊消息走完整管线）、`/showcase adapter log`（查看假平台"发出"的内容）
- **测试**：注册表内容、`type`/`enable`/`id` 自动补齐、注入与 send 回环、`terminate()` 让 `run()` 正常退出、
  实例缺失/存在两种状态下的指令输出

### 说明

- 只要插件被加载，WebUI「创建机器人 → 消息平台类别」里就会出现 `Showcase Fake Platform`；
  注册发生在 `import` 期，**没有配置开关能关掉它**，插件重载/卸载时随模块注销（README「已知边界」有说明）
- 假平台实例默认 `enable: False`：在 WebUI 里建好后还要打开「启用」才真正 `run()`
- 这个 API 本身不需要抬高版本下限（`register_platform_adapter` 自 v3.4.0 就有，`logo_path` 4.3.0、
  `config_metadata` / `i18n_resources` 4.16.0），`astrbot_version` 仍是 `>=4.27.3`

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
