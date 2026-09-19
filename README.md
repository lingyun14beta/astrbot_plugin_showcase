# astrbot_plugin_showcase

AstrBot 插件能力全景示例：**一个插件，把所有扩展点各演示一遍**。

它由官方 [helloworld 模板](https://github.com/Soulter/helloworld) 改造而来，除了保留原来的 `/helloworld` 指令，
其余内容全部用来演示「AstrBot 插件到底能做什么」——配置页、钩子、国际化、WebUI Page、LLM 工具、持久化存储。

> 适用版本：AstrBot `>=4.27.3`（`metadata.yaml` 的 `astrbot_version`，下限由 `/showcase tools on|off`
> 用到的 `activate_llm_tool_async` 决定；注释里列了每个 API 的引入版本）。

## 适合谁

给**写 AstrBot 插件的人**看的参考实现，不是给终端用户用的功能插件。

- 看官方文档嫌慢、看 helloworld 模板嫌少，想直接抄一份能跑的全量示例的插件开发者；
- 已经被 AstrBot 插件 API 坑过一次、想先摸清「哪些能拆、哪些不能」（见下文）再动手的人；
- 打算用 AI 写 AstrBot 插件、需要给模型喂一份准确 API 参照的人。

反过来，两种人不用装：只想要一个能干活的功能插件的人（本插件没有业务功能，只会多出一整棵 `/showcase`
指令树和一套配置项），以及 AstrBot `<4.27.3` 的用户（`metadata.yaml` 的 `astrbot_version` 会直接拦住加载）。

最省时间的用法：别整仓库读。`/showcase` 打一遍指令树 → 挑中你想做的那类功能 → 只翻 `showcase/` 下对应的
那一个文件（每个 70~150 行）。

## 安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/lingyun14beta/astrbot_plugin_showcase
```

在 WebUI 的「插件」页重载本插件即可。插件无第三方依赖，不需要 `requirements.txt`。

## 目录结构

```
astrbot_plugin_showcase/
├── main.py                        # 注册面：全部 @filter.* 装饰器（一行委托）+ 指令 + 装配
├── showcase/                      # 子包
│   ├── rules.py                   #   规则匹配与模糊匹配（不依赖 astrbot，可单测）
│   ├── hooks.py                   #   14 个钩子的实现
│   ├── web_api.py                 #   Page 的 4 个后端接口
│   ├── cron.py                    #   定时任务
│   ├── push.py                    #   主动推送后台任务
│   ├── wizard.py                  #   多轮会话状态机
│   └── tools.py                   #   类式 FunctionTool（含后台任务型工具）
├── skills/showcase-guide/         # 插件自带的 Skill（WebUI 里作为只读来源展示）
├── tests/                         # pytest：纯逻辑单测 + 需要 AstrBot 的集成测试
├── .github/workflows/ci.yml       # CI：ruff + pytest
├── metadata.yaml                  # 插件元数据（名称、版本、支持平台、版本约束、市场标签与链接）
├── _conf_schema.json              # WebUI 配置页的 Schema
├── .astrbot-plugin/i18n/          # 国际化文案（zh-CN / en-US / ja-JP）
├── pages/showcase/                # WebUI Page（index.html + app.js + style.css）
├── logo.png                       # 插件卡片图标（256×256 占位图，可自行替换）
├── CHANGELOG.md                   # 更新日志（AstrBot 在插件详情页按 Markdown 渲染）
├── pytest.ini
├── README.md
└── LICENSE
```

### 哪些能拆、哪些不能

`main.py` 里保留的是**被 `@filter.*` 装饰的函数本体**，实现一律放子包。这不是风格选择，而是
AstrBot 的实现约定：它在 **10 处**直接索引 `star_map[handler.handler_module_path]`
（通用钩子派发 `core/pipeline/context_utils.py:99`、`core/core_lifecycle.py:373`、
`core/star/star_manager.py:1430/1972`、`core/pipeline/result_decorate/stage.py:166-186`、
`core/platform/manager.py:234`、`core/pipeline/waking_check/stage.py:205/225` 等），
而 `star_map` 只为「定义了 Star 子类的模块」建条目 —— 也就是插件主模块。

把被装饰的函数放进子模块的后果不是「少一条日志」：

- `context_utils.py` 里那行日志在 `try` 内、但「事件被 stop」的日志在 `try` 外，
  所以钩子既不会执行（异常被 `except BaseException` 吞掉，只留一条 traceback），
  还可能让 KeyError 冒泡进管线；
- 插件加载/卸载、`on_decorating_result`、`on_platform_loaded` 等钩子的日志同样会炸。

所以本插件的做法是：**main.py 只写「装饰器 + 一行委托」**（和官方内置插件把指令实现放进
`commands/` 同一个套路），逻辑放 `showcase/hooks.py`。

**可以随便拆的**：Web API handler（只登记在 `Context.registered_web_apis` 这个普通列表里，
不经过 `star_handlers_registry`，见 `showcase/web_api.py`）、类式 LLM 工具
（`_resolve_tool_handler_module_path` 会把子模块路径归一化到插件主模块，工具归属仍然正确）、
以及所有纯逻辑与状态机。

其中 `CHANGELOG.md` 也是 AstrBot 认的约定：插件详情页会读插件目录下的更新日志文件
（依次尝试 `CHANGELOG.md` → `changelog.md` → `CHANGELOG` → `changelog`，见
`astrbot/dashboard/services/plugin_service.py` 的 `get_plugin_changelog`），读取不到就显示「暂无更新日志」。

## 一、指令（聊天里试）

| 指令 | 演示的扩展点 |
| --- | --- |
| `/showcase hello` | 指令组 + 子指令 + 读取配置 |
| `/showcase ping` | 基于配置的会话级冷却 |
| `/showcase config` | `object` 嵌套配置读取、输出限长（`max_lines` 截断） |
| `/showcase rules` | `template_list` 规则解析（`__template_key`） |
| `/showcase say <别名>` | `dict` 类型配置读取 |
| `/showcase notes` | `file` 类型配置 + 插件数据目录 |
| `/showcase ask <问题>` | `context.llm_generate` 直接调用模型 |
| `/showcase pipeline <问题>` | `event.request_llm`：走正常会话管线（带人设/工具/历史） |
| `/showcase agent <任务>` | `context.tool_loop_agent` 工具循环（模型自行调用工具） |
| `/showcase tools [on\|off]` | 类式 `FunctionTool` 列表 + 运行时启用/停用 |
| `/showcase history [n]` | `ConversationManager`：读取当前会话的历史消息 |
| `/showcase card` | `Star.html_render` 渲染 HTML 为图片 |
| `/showcase chain` | `At` / `Plain` 消息组件与消息链 |
| `/showcase react` | `event.react()` 表情回应 |
| `/showcase typing` | `event.send_typing()` / `stop_typing()` |
| `/showcase silent <文本>` | `event.should_call_llm(False)` 拦截 LLM |
| `/showcase wizard` | `@session_waiter` 多轮会话（`/cancel` 可中止） |
| `/showcase memo set\|get\|del` | 嵌套指令组 + `sp.session_*` 会话级状态（与插件 KV 对照） |
| `/showcase push on\|off\|status` | 后台任务 + `context.send_message` 主动推送 |
| `/showcase cron add\|list\|run\|del` | `context.cron_manager` 定时任务（cron 表达式排程） |
| `/showcase extras <内容>` | `event.set_extra/get_extra`：挂在事件上，由钩子读出来 |
| `/showcase stream` | `event.send_streaming` 分块发送（仅部分平台支持） |
| `/showcase state` | KV 存储读写 + 钩子调用计数 |
| `/showcase i18n [locale]` | 读取 `.astrbot-plugin/i18n` 文案 |
| `/showcase-admin` | `permission_type(ADMIN)` 权限过滤 |
| `/showcase-platform` | `platform_adapter_type` 平台过滤 |
| `/showcase-recall` | 平台原生 API（`event.bot.api.call_action`，仅 QQ/aiocqhttp） |
| `showcase-regex <词>` | `filter.regex` 正则监听（不需要唤醒前缀） |
| `/showcase-fuzzy` | `custom_filter` 自定义过滤器 |
| `/helloworld` | 模板原指令，最小可用示例 |

`/showcase` 后面不带子指令时，AstrBot 会把整棵指令树连同每个子指令的参数类型打印出来，可以直接当帮助用。

需要真机手测的几条：`/showcase agent`（要先配「演示用模型」，且模型得愿意调工具）、
`/showcase push`（真的会往会话里推消息，记得 `push off`）、`/showcase cron`（真的会按表达式推送）、
`/showcase-recall`（仅 QQ 生效）、`/showcase stream`（仅 Telegram / QQ 官方私聊，aiocqhttp 走 fallback）、
`/showcase react` / `/showcase typing`（平台支持度不一，不支持时插件会回一句提示而不是报错）。

## 二、配置页（WebUI 里试）

`_conf_schema.json` 覆盖了插件配置支持的全部字段类型与常用修饰键：

| 字段 | 类型 | 顺带演示的键 |
| --- | --- | --- |
| `enabled` | `bool` | 用 `custom_filter` 做整组指令总开关 |
| `greeting` | `text` | 多行文本 |
| `log_level` | `string` | `options` + `labels`（下拉框） |
| `cooldown_seconds` | `int` | `slider` |
| `push_interval_seconds` | `int` | `slider`（主动推送间隔） |
| `session_timeout_seconds` | `int` | `slider`（多轮会话每步超时） |
| `similarity_threshold` | `float` | `slider`（小数步长；关键词被消息覆盖的比例达到该值才触发） |
| `enabled_features` | `list` | `options` + `render_type: checkbox`，逐项控制 hooks / message / llm_tool / web_api / storage / agent / push |
| `keywords` | `list` | 自由列表（不设 `options`） |
| `chat_provider_id` | `string` | `_special: select_provider`（Provider 选择器） |
| `agent_instruction` | `text` | `editor_mode` + `editor_language`（Monaco 代码编辑器） |
| `cron_expression` | `string` | 供 `/showcase cron add` 使用的默认表达式 |
| `reply_prefix` | `string` | 非空时 `on_decorating_result` 真的改写消息链 |
| `inject_context` | `bool` | 开启后 `on_llm_request` 注入临时上下文 |
| `api_token` | `string` | `secret`（掩码显示）※ 纯演示，插件只回显「已配置／未配置」 |
| `aliases` | `dict` | `template_schema` 预设键 |
| `manual_files` | `file` | `file_types` 上传类型限制 |
| `advanced` | `object` | 嵌套 `items`、`condition` 条件显示、`invisible` 隐藏项 |
| `rules` | `template_list` | `templates`、`display_item`、`hide_hint_in_list`、模板内多种字段 |

其中两个字段**只用于演示 Schema 修饰键、不参与任何逻辑**，hint 里已写明：

- `api_token` —— 演示 `secret`；
- `advanced.rule_limit` —— 演示 `condition`（只在「严格模式」打开时显示），值仅由 `/showcase config` 回显；
- `advanced.debug_dump` —— 演示 `invisible`（WebUI 不显示），打开后 `/showcase config` 多打印一行。

保存配置会触发热重载，插件会用新配置重新实例化，可以直接在聊天里用 `/showcase config` 观察变化。

### 版本要求：core 与 WebUI 是两条线

插件在 `metadata.yaml` 里声明了 **core 侧**的下限（`astrbot_version: ">=4.27.3"`，依据见该文件注释）。
但**配置页的渲染由 WebUI 资产决定，跟 core 版本可以不一致**——WebUI 旧了不会报错，只是某些修饰键被忽略、字段降级渲染。
下表是 `_conf_schema.json` 里每个能力的前端引入版本与降级表现：

| 能力 | 用于哪些字段 | WebUI 引入版本 | 缺失时的表现 |
| --- | --- | --- | --- |
| `secret`（掩码 + 眼睛） | `api_token` | **4.28.0** | 普通文本框、无眼睛图标，值为明文 |
| `display_item` / `hide_hint_in_list` | `rules` | 4.25.3 | 折叠条目不显示 `pattern: xxx` 标题 |
| `file_types` | `manual_files` | 4.13.0 | 上传不限制后缀 |
| `template_list` / `template_schema` | `rules` / `aliases` | 4.10.4 | `rules` 掉到兜底文本框，基本无法编辑；`aliases` 只剩键值对编辑器 |
| `render_type: checkbox` | `enabled_features` | 4.0.0 | 变成多选下拉 |
| `_special: select_provider` | `chat_provider_id` | 4.0.0 | 变成文本框，需手填 provider id |
| `condition` | `advanced.rule_limit` | 4.0.0 | 一直显示，不再跟随 `strict_mode` |
| `slider` | 3 个数值字段 | 3.5.9 | 只剩数字输入框 |
| `labels` | `log_level` | 3.4.27 | 下拉显示英文原值 |
| `invisible` | `advanced.debug_dump` | 3.4.2 | 隐藏项会显示出来 |

凡是「缺失会明显影响使用」的（≥ 4.10 的那几项），对应字段的 `hint` 里也写了「需 WebUI ≥ x.y.z」，
这样在旧 WebUI 上打开配置页时能直接看到原因。更新 WebUI 到与 core 同版本即可全部恢复
（WebUI 更新入口，或从源码 `cd dashboard && pnpm build`）。

## 三、WebUI Page

插件自带的页面位于 `pages/showcase/index.html`，在 WebUI 的插件详情页里打开。页面完全由插件目录下的静态文件渲染，
运行在受限 iframe 中，只能用 `window.AstrBotPluginPage`（bridge）与外界通信：

| bridge 方法 | 说明 |
| --- | --- |
| `ready()` / `getContext()` | 获取运行上下文（插件名、页面名、语言、主题） |
| `onContext(fn)` | 主题或语言切换时重绘 |
| `t(key, fallback)` | 读取 `pages.<页面名>.*` 文案，自动回退 `zh-CN` / `en-US` |
| `apiGet(endpoint, params)` | 调用插件后端接口（`params` 会拼成查询串） |
| `apiPost(endpoint, body)` | 同上，JSON 请求体 |
| `upload` / `download` / `subscribeSSE` | 上传、下载、SSE 订阅（本页未使用，接口同样可用） |

后端接口在 `main.py` 中用 `context.register_web_api` 注册，路由必须带插件名前缀，前端调用时只写相对路径：

| 路由 | 方法 | 用途 |
| --- | --- | --- |
| `/{plugin}/ping` | GET | 连通性测试 |
| `/{plugin}/state` | GET | 插件运行状态、钩子计数、KV 内容 |
| `/{plugin}/commands` | GET | 本插件注册的全部 handler |
| `/{plugin}/kv` | POST | 写入一条 KV 记录并回读 |

页面样式通过 `:root` / `[data-theme="dark"]` 两组 CSS 变量跟随 Dashboard 深浅色，不需要额外判断。

## 四、事件钩子

`main.py` 注册了全部可用钩子，各自只做观察与计数（不改变机器人行为），可在「插件配置 → 参与演示的扩展点」里
勾选 `hooks` 后通过日志观察触发顺序：

`on_astrbot_loaded`、`on_platform_loaded`、`on_plugin_loaded`、`on_plugin_unloaded`、`on_plugin_error`、
`on_waiting_llm_request`、`on_llm_request`、`on_llm_response`、`on_agent_begin`、`on_agent_done`、
`on_using_llm_tool`、`on_llm_tool_respond`、`on_decorating_result`、`after_message_sent`。

每个钩子函数上方都写了「可以在这里改什么」，例如 `on_decorating_result` 里改 `event.get_result().chain` 就能
给所有回复加前缀。此外还注册了一个 LLM 工具 `showcase_echo`，让模型在需要时自主调用。

## 五、国际化

```
.astrbot-plugin/i18n/zh-CN.json   # metadata.* / config.* / pages.*
.astrbot-plugin/i18n/en-US.json
.astrbot-plugin/i18n/ja-JP.json
```

- 插件信息：`metadata.display_name` / `metadata.desc` / `metadata.short_desc`
- 配置项：`config.<字段路径>.description|hint|labels`（`object` 与 `template_list` 的 `items` 段要省略）
- 页面：`pages.showcase.title|description` 以及页面内任意自定义键

需要注意：**AstrBot 目前只把 i18n 交给 WebUI 使用，没有提供聊天侧的取词 API**，也没有全局的聊天语言设置。
插件若想在聊天里输出多语言文案，只能自己读取这些 JSON —— `/showcase i18n <locale>` 与 `main.py` 里的
`_t()` 就是这种做法的最小示例。

## 六、持久化

- KV 存储：`put_kv_data` / `get_kv_data` / `delete_kv_data`，无需建表，命名空间是 `plugin_id`。
  写入只在用户主动执行 `/showcase state` 或页面点按钮时发生，不会按消息频率写库；
  `enabled_features` 未勾选 `storage` 时连这些主动写入也会跳过。
- 插件数据目录：`StarTools.get_data_dir(插件名)` → `data/plugin_data/astrbot_plugin_showcase/`，
  配置页上传的文件也存放在这里（`files/<字段名>/<文件名>`）

## 七、已知边界

- `metadata.yaml` 里的 `pages:` 字段目前不会被 Dashboard 读取，页面完全由 `pages/<页面名>/index.html`
  目录扫描发现，因此本插件没有声明它。
- `social_link` 是**市场侧字段**，AstrBot 本体（4.28.1）完全不解析它：`StarMetadata` 没有这个字段
  （`astrbot/core/star/star.py:24-76`），插件详情接口也只序列化 `StarMetadata` 上有的字段
  （`astrbot/dashboard/services/plugin_service.py:637-659`）。详情页那个「作者网站」读的是
  `plugin.social_link || marketPlugin.social_link || plugin.author_url || ... || homepage`
  （`dashboard/src/views/ExtensionPage.vue:216-240` 用 repo 把已安装插件匹配到市场条目，
  再传给 `PluginDetailPage.vue:169-181`），所以只有**上架插件市场后**才会显示；
  本地手装（`git clone` 到 `data/plugins`）时这一行写了也不显示。`author_url`、`homepage`
  同理，它们不是 `metadata.yaml` 的字段，只有市场接口会返回。
- 页面 iframe 的沙箱不允许访问 Dashboard 的 cookie / localStorage；资源必须写**相对路径**，
  绝对路径（如 `/app.js`）不会被重写、会 404。
- `secret` 字段只是显示层掩码（且需 WebUI ≥ 4.28.0），值始终明文存储，不要填真实凭据。
- `file` 字段存的是相对插件数据目录的路径，读取时要拼 `data_dir`。
- **WebUI 版本可能落后于 core**：`astrbot_version` 只能约束 core，配置页能不能渲染出滑条、勾选框、
  模板列表取决于 WebUI 资产版本。对照上面的版本表，或直接看 AstrBot 启动日志里
  `Some dashboard features may not work until matching assets are available.` 这类告警。
- Schema 里另有几个键**只对 Dashboard 内置配置页生效**，插件配置页不读，本插件没有使用它们
  （记录在此避免误用）：`full_width`、`collapsed`（仅核心配置渲染器）、`items_type`（任何地方都不读）。
- 插件自己声明的 `enabled`/`enabled_features` 是**插件逻辑**的开关，与 AstrBot 插件列表里的启用/停用无关；
  后者由 AstrBot 管理（`metadata.star_cls` 会被置空），此时指令组会静默不唤醒。
- **本版本不建议插件使用、因此本插件没有演示的 API**（记录在此避免后来人踩坑）：
  `register_agent` / handoff 子 agent —— 全仓库只有 `star_handler.py` 自身定义，没有任何内置插件、
  文档或测试用过，触发链路不明，照抄很可能跑不起来；`context.get_db()`、`subagent_orchestrator`、
  `kb_manager` 属于内部管理器，示例插件直接依赖会耦合内部实现（`get_db()` 还会把库表结构暴露给读者）；
  `sp.global_*` 是跨插件全局键，容易鼓励滥用（README 说明用途即可）；已废弃的 `@register` 装饰器、
  `load_config/put_config/update_config`、`context.register_task` 也不适合作为示例。
- **`event.send_streaming` 的平台支持有限**（官方仅 Telegram 与 QQ 官方私聊，`use_fallback=True` 时
  aiocqhttp 可用），其他平台调用不会报错但也不会有流式效果。

## 八、进阶扩展点

前面几节偏「声明式」的扩展点，这一节是几个需要自己管状态的：

### 三种调用 LLM 的方式

| 方式 | 入口 | 特点 |
| --- | --- | --- |
| `context.llm_generate` | `/showcase ask` | 直接调用指定 Provider，插件完全控制提示词与上下文 |
| `event.request_llm` | `/showcase pipeline` | 交给 AstrBot 正常管线：带人设、工具、会话历史 |
| `context.tool_loop_agent` | `/showcase agent` | 多步工具循环，模型自己决定调用哪些工具 |

### 子 agent 与 LLM 工具（`showcase/tools.py` + `/showcase agent`）

- `ShowcaseStatusTool` 是**类式** `FunctionTool`：手写 JSON Schema，可以精确描述 `enum`、必填项，
  还能把插件实例存进字段里。它和 `@filter.llm_tool` 声明的 `showcase_echo` 一起出现在模型的工具列表里
  （`/showcase tools` 可以列出来看）。
- `ShowcaseSlowReportTool` 声明了 `is_background_task=True`：AstrBot 立刻把任务号还给模型，
  真正的工作在后台跑，完成后带着结果重新唤醒主 agent；唤醒提示语用
  `event.set_extra("background_note", ...)` 自定义。
- `/showcase tools on|off` 演示运行时启停工具（`activate/deactivate_llm_tool_async`），
  这是本插件版本下限（4.27.3）的来源。

### 多轮会话（`showcase/wizard.py` + `/showcase wizard`）

`@session_waiter(timeout=...)` 装饰的处理函数会在会话期间接管后续消息：AstrBot 内置插件里
优先级最高的 `handle_session_control_agent` 会把命中会话的消息转给它并 `event.stop_event()`，
所以向导进行中不会有别的插件或 LLM 插话。处理器用 `controller.keep()` 续下一轮、
`controller.stop()` 结束，超时会抛 `TimeoutError`。本插件按配置动态创建 waiter，所以超时时间可调。

### 定时任务（`showcase/cron.py` + `/showcase cron`）

用 `context.cron_manager.add_basic_job(cron_expression=..., handler=..., payload=...)` 注册作业，
到点推送到指定会话。两个约定要注意：**handler 是以 `handler(**payload)` 调用的**，所以参数名要和
payload 的 key 对上；**handler 只在内存里**，`persistent=True` 的作业重启后还在数据库里但处理函数没了，
需要在插件加载时重新注册（本示例用非持久化作业，避免这种空转）。

### 主动推送（`showcase/push.py` + `/showcase push`）

`initialize()` 里 `asyncio.create_task` 起一个循环，`/showcase push on` 把当前会话的 umo 写进 KV，
循环到点用 `context.send_message(umo, chain)` 主动发消息。**`terminate()` 里必须取消任务**，
否则插件热重载会留下重复的推送循环 —— 这是后台任务类插件最容易踩的坑。
如果只是"按固定时间点做事"，优先用上面的 cron，而不是自己写 sleep 循环。

### 事件钩子不只是记日志

`enabled_features` 勾选 `hooks` 后，大部分钩子只写日志（观察触发顺序用），但有两个按配置真的干活：

- `on_llm_request`：设置 `inject_context` 后往每次请求追加一条**临时上下文**
  （`extra_user_content_parts` + `mark_as_temp()`）—— 不写入历史、不破坏 system prompt 的缓存前缀，
  比直接拼 `system_prompt` 更好。
- `on_decorating_result`：设置 `reply_prefix` 后给所有回复加前缀；`/showcase extras <内容>`
  挂在事件上的内容也会在这里被读出来追加（演示 `set_extra`/`get_extra` 跨 handler 传值）。

### 插件自带的 Skill（`skills/showcase-guide/`）

插件可以在自己目录下放 `skills/<名字>/SKILL.md`（或直接 `skills/SKILL.md`，名字取插件目录名），
AstrBot 会把它纳入 Skill Manager，在 WebUI 的「插件 → 技能」里作为**只读来源**展示：可以启用/停用，
但不能从本地 Skills 页编辑或删除，插件卸载/更新时随插件文件变化。本插件的 SKILL.md 写的是
"这个插件有哪些能力、某个扩展点在哪实现"，用来演示插件如何把领域知识交给模型。

### 测试与 CI（`tests/` + `.github/workflows/ci.yml`）

- `tests/test_rules.py`：**纯逻辑单测**，只 import `showcase/rules.py`，不依赖 AstrBot，
  所以在 CI 上直接跑（相似度口径、正则优先级、大小写敏感、无效正则这些最容易写错的地方都在这里回归）。
- `tests/test_plugin.py`：**集成测试**，需要本机装好 AstrBot；没装（或装坏了）时整份文件跳过，
  覆盖注册面、配置读取、i18n、各条指令的核心行为、向导状态机、cron 调用约定等。
- CI 跑 `ruff check` + `ruff format --check` + `pytest`；集成测试在 CI 上自动跳过。

本地跑：

```bash
ruff check . && ruff format --check .
pytest                      # 纯逻辑测试必跑；集成测试视环境自动跳过
```

### 状态作用域怎么选（`/showcase memo`）

| 存法 | 作用域 | 适合 |
| --- | --- | --- |
| `sp.session_put/get/remove(umo, ...)` | 单个会话 | 跟人/群走的状态，如向导进度、临时开关 |
| `put_kv_data/get_kv_data(key, ...)` | 整个插件共享 | 跨会话的配置性数据，如推送订阅列表 |
| `sp.global_*` | AstrBot 全局 | 多个插件之间共享 |

`/showcase memo set|get|del` 会把同名的会话级值与插件级值一起打印出来，方便直观对比。

### 其它小 API

`/showcase react`（`event.react`）、`/showcase typing`（`send_typing` / `stop_typing`）、
`/showcase silent`（`should_call_llm(False)` 拦下后续 LLM 处理）、
`/showcase-recall`（`@filter.platform_adapter_type(AIOCQHTTP)` + `event.bot.api.call_action`，平台原生调用）。
这四条都做了「平台不支持时回一句提示」的兜底，不会因为适配器差异直接报错。

## 鸣谢

- 模板来源：[Soulter/helloworld](https://github.com/Soulter/helloworld)（AGPL-3.0）
- 开发文档：[AstrBot 插件开发](https://docs.astrbot.app/dev/star/plugin-new.html)

本仓库基于上述模板改造，遵循原仓库的 AGPL-3.0 许可。
