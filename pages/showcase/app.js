// 插件页前端：只通过 window.AstrBotPluginPage（bridge）与插件后端通信。
//
// 页面运行在 Dashboard 的受限 iframe 里，拿不到 Dashboard 的 cookie / localStorage，
// 因此所有请求都交给父页面以它自己的身份转发（见 README 的说明）。
// 后端接口在 main.py 里用 context.register_web_api 注册，路由带插件名前缀；
// 这里调用时只写插件内的相对路径，例如 "state" 对应 /{plugin}/state。

const bridge = window.AstrBotPluginPage;
const PAGE = "showcase";

const el = {
  heading: document.getElementById("heading"),
  subtitle: document.getElementById("subtitle"),
  contextTitle: document.getElementById("context-title"),
  actionsTitle: document.getElementById("actions-title"),
  outputTitle: document.getElementById("output-title"),
  bridgeNote: document.getElementById("bridge-note"),
  output: document.getElementById("output"),
  labels: {
    plugin: document.getElementById("l-plugin"),
    display: document.getElementById("l-display"),
    page: document.getElementById("l-page"),
    locale: document.getElementById("l-locale"),
    theme: document.getElementById("l-theme"),
  },
  values: {
    plugin: document.getElementById("v-plugin"),
    display: document.getElementById("v-display"),
    page: document.getElementById("v-page"),
    locale: document.getElementById("v-locale"),
    theme: document.getElementById("v-theme"),
  },
  buttons: {
    ping: document.getElementById("btn-ping"),
    state: document.getElementById("btn-state"),
    commands: document.getElementById("btn-commands"),
    kv: document.getElementById("btn-kv"),
  },
};

/** 取一条文案：优先当前语言，bridge 会自动回退 zh-CN / en-US。 */
function t(key, fallback) {
  return bridge.t(`pages.${PAGE}.${key}`, fallback);
}

/** 把任意对象打印到输出区。 */
function show(data) {
  el.output.textContent =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

/** 按钮请求期间统一置灰，避免重复点击。 */
async function withBusy(button, task) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = t("loading", "请求中…");
  try {
    await task();
  } catch (error) {
    show(`调用失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

/** 渲染静态文案与运行上下文；语言或主题变化时会被重新调用。 */
function render(context) {
  document.title = t("title", "Showcase");
  el.heading.textContent = t("heading", "AstrBot 插件能力展示");
  el.subtitle.textContent = t("subtitle", "");
  el.contextTitle.textContent = t("context_section", "运行上下文");
  el.actionsTitle.textContent = t("actions_section", "Bridge 调用演示");
  el.outputTitle.textContent = t("output", "返回结果");
  el.bridgeNote.textContent = t("bridge_note", "");

  el.labels.plugin.textContent = t("plugin_name", "插件名");
  el.labels.display.textContent = t("display_name", "展示名");
  el.labels.page.textContent = t("page_name", "页面名");
  el.labels.locale.textContent = t("locale", "当前语言");
  el.labels.theme.textContent = t("theme", "主题");

  el.buttons.ping.textContent = t("ping", "Ping");
  el.buttons.state.textContent = t("load_state", "读取运行状态");
  el.buttons.commands.textContent = t("load_commands", "读取注册的指令");
  el.buttons.kv.textContent = t("write_kv", "写入一条 KV 记录");

  el.values.plugin.textContent = context?.pluginName ?? "-";
  el.values.display.textContent = context?.displayName ?? "-";
  el.values.page.textContent = context?.pageName ?? "-";
  el.values.locale.textContent = bridge.getLocale();
  el.values.theme.textContent = context?.isDark
    ? t("theme_dark", "深色")
    : t("theme_light", "浅色");

  if (el.output.dataset.touched !== "1") {
    el.output.textContent = t("empty", "");
  }
}

el.buttons.ping.addEventListener("click", () =>
  withBusy(el.buttons.ping, async () => {
    el.output.dataset.touched = "1";
    show(await bridge.apiGet("ping"));
  }),
);

el.buttons.state.addEventListener("click", () =>
  withBusy(el.buttons.state, async () => {
    el.output.dataset.touched = "1";
    // apiGet 的第二个参数会变成查询串，避免把 ?a=b 直接拼进 endpoint。
    show(await bridge.apiGet("state"));
  }),
);

el.buttons.commands.addEventListener("click", () =>
  withBusy(el.buttons.commands, async () => {
    el.output.dataset.touched = "1";
    show(await bridge.apiGet("commands"));
  }),
);

el.buttons.kv.addEventListener("click", () =>
  withBusy(el.buttons.kv, async () => {
    el.output.dataset.touched = "1";
    show(
      await bridge.apiPost("kv", {
        value: `来自插件页 @ ${new Date().toLocaleString()}`,
      }),
    );
  }),
);

// ready() 在收到首个 context 后 resolve；onContext 用于跟随主题/语言切换重绘。
const context = await bridge.ready();
render(context);
bridge.onContext(render);
