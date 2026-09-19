"""WebUI Page 的后端接口。

页面（``pages/showcase/``）通过 ``window.AstrBotPluginPage`` bridge 调用这里的接口。
与 ``@filter.*`` 不同，**Web API 不经过 star_handlers_registry**：它只是登记在
``Context.registered_web_apis`` 这个普通列表里（见 ``astrbot/core/star/context.py``），
所以可以放在子模块里 —— 这也是 ``astrbot_plugin_journal`` 等插件的做法。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from astrbot.api.web import error_response, json_response, request
from astrbot.core.star.star_handler import star_handlers_registry

PLUGIN_NAME = "astrbot_plugin_showcase"
"""与 metadata.yaml 的 name 保持一致；路由要带上它，页面里调用时不带。"""

I18N_DIR = Path(__file__).resolve().parent.parent / ".astrbot-plugin" / "i18n"

WEB_API_DISABLED = "插件未启用，或 enabled_features 未勾选 web_api"


class ShowcaseWebAPI:
    """Page 用到的 4 个接口：连通性、运行状态、注册清单、KV 读写。

    Attributes:
        plugin: 插件实例，用于读配置/状态与读写 KV。
    """

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    @property
    def plugin_name(self) -> str:
        """路由前缀用的插件名：优先取加载器注入的 name，测试等场景回退到常量。"""
        return getattr(self.plugin, "name", None) or PLUGIN_NAME

    def register(self) -> None:
        """把接口注册到 Context 上（幂等：相同路由会覆盖）。"""
        context = self.plugin.context
        prefix = f"/{self.plugin_name}"
        context.register_web_api(f"{prefix}/ping", self.api_ping, ["GET"], "连通性测试")
        context.register_web_api(
            f"{prefix}/state", self.api_state, ["GET"], "插件运行状态"
        )
        context.register_web_api(
            f"{prefix}/commands", self.api_commands, ["GET"], "本插件注册的指令与钩子"
        )
        context.register_web_api(
            f"{prefix}/kv", self.api_kv, ["POST"], "写入一条 KV 记录"
        )

    async def api_ping(self):
        """GET /ping：最小连通性示例。"""
        if not self._available():
            return error_response(WEB_API_DISABLED, status_code=403)
        return json_response({"message": "pong", "plugin": self.plugin_name})

    async def api_state(self):
        """GET /state：插件运行状态，供 Page 展示。"""
        if not self._available():
            return error_response(WEB_API_DISABLED, status_code=403)
        plugin = self.plugin
        return json_response(
            {
                "plugin_id": getattr(plugin, "plugin_id", ""),
                "enabled": plugin.enabled,
                "features": sorted(plugin.features),
                "keywords": plugin.keywords,
                "rules": len(plugin.rules),
                "greeting_preview": plugin.greeting[:60],
                "hook_counts": plugin.hook_counts,
                "sent_count": plugin.sent_count,
                "locales": sorted(p.stem for p in I18N_DIR.glob("*.json")),
                "data_dir": str(plugin.data_dir),
                "kv_last": await plugin.get_kv_data("last_kv", None),
                "secret_configured": bool(plugin.config.get("api_token")),
                "operator": request.username,
            }
        )

    async def api_commands(self):
        """GET /commands：列出本插件注册的指令与钩子。"""
        if not self._available():
            return error_response(WEB_API_DISABLED, status_code=403)
        # 插件主模块路径 = 定义插件类的模块；钩子/指令都注册在它名下
        module_path = self.plugin.__class__.__module__
        items = [
            {
                "handler": md.handler_name,
                "event_type": getattr(md.event_type, "name", str(md.event_type)),
                "desc": (md.desc or "").splitlines()[0] if md.desc else "",
            }
            for md in star_handlers_registry
            if md.handler_module_path == module_path
        ]
        return json_response({"count": len(items), "handlers": items})

    async def api_kv(self):
        """POST /kv：写入一条 KV 记录并回读，演示 bridge.apiPost。"""
        if not self._available():
            return error_response(WEB_API_DISABLED, status_code=403)
        if "storage" not in self.plugin.features:
            return error_response("enabled_features 未勾选 storage", status_code=403)
        payload = await request.json(default={}) or {}
        record = {
            "value": str(payload.get("value", ""))[:200],
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        await self.plugin.put_kv_data("last_kv", record)
        return json_response({"stored": await self.plugin.get_kv_data("last_kv", None)})

    def _available(self) -> bool:
        """插件启用且勾选了 web_api 时才对外提供服务。

        Returns:
            是否可用。
        """
        return self.plugin.enabled and "web_api" in self.plugin.features
