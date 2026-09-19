"""AstrBot Showcase 的辅助模块。

为什么装饰器全留在 main.py：AstrBot 在若干处直接索引 ``star_map[handler.handler_module_path]``
（``astrbot/core/star/star_manager.py`` 的 ``on_plugin_loaded`` 日志、``core/pipeline/waking_check/stage.py``
的过滤器异常分支），而 ``star_map`` 只为「定义了 Star 子类的模块」建条目 —— 也就是插件主模块。
把 ``@filter.*`` 装饰器放到子模块里会让钩子静默不触发，因此这里只放**不带装饰器**的逻辑。
"""
