# src/core/plugin_manager.py
import os
import importlib.util
from typing import Dict, List, Any
from loguru import logger  # <--- ИСПОЛЬЗУЕМ LOGURU

from src.core import BaseStage, ProcessingContext


class PluginManager:
    def __init__(self, plugin_dir: str = "src/plugins"):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, BaseStage] = {}
        self.execution_order: List[BaseStage] = []

        # Получаем абсолютный путь, чтобы не зависеть от точки запуска
        # Это важно, так как worker может запускаться из разных мест
        base_path = os.getcwd()
        self.abs_plugin_dir = os.path.join(base_path, plugin_dir)

        self._load_plugins()

    def inject_dependencies(self, bus):
        """Внедряет EventBus во все плагины, у которых есть метод set_bus"""
        for plugin in self.plugins.values():
            if hasattr(plugin, "set_bus"):
                plugin.set_bus(bus)

    def _load_plugins(self):
        """Динамическая загрузка плагинов из папки"""
        if not os.path.exists(self.abs_plugin_dir):
            try:
                os.makedirs(self.abs_plugin_dir)
                # Создаем пустой __init__.py
                open(os.path.join(self.abs_plugin_dir, "__init__.py"), "a").close()
                logger.info(f"Created plugins directory: {self.abs_plugin_dir}")
            except Exception as e:
                logger.error(f"Could not create plugins dir: {e}")
                return

        logger.info(f"Scanning plugins in {self.abs_plugin_dir}...")

        for filename in os.listdir(self.abs_plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                self._load_single_plugin(filename)

    def _load_single_plugin(self, filename: str):
        plugin_name = filename[:-3]
        path = os.path.join(self.abs_plugin_dir, filename)

        try:
            spec = importlib.util.spec_from_file_location(plugin_name, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                found_class = False
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # Проверяем, что это класс-наследник BaseStage
                    if isinstance(attr, type) and issubclass(attr, BaseStage) and attr is not BaseStage:
                        instance = attr()
                        p_id = getattr(instance, "PLUGIN_ID", plugin_name)

                        self.plugins[p_id] = instance
                        self.execution_order.append(instance)
                        logger.success(f"🔌 Loaded Plugin: {p_id} ({attr_name})")
                        found_class = True

                if not found_class:
                    logger.warning(f"File {filename} loaded, but no BaseStage subclass found.")

        except Exception as e:
            logger.error(f"Failed to load plugin {filename}: {e}")

    def process_all(self, ctx: ProcessingContext):
        for plugin in self.execution_order:
            try:
                plugin.process(ctx)
            except Exception as e:
                # Логируем ошибку, но не роняем весь пайплайн
                logger.error(f"Plugin error: {e}")

    def dispatch_command(self, target_id: str, cmd: str, args: Any):
        if target_id in self.plugins:
            plugin = self.plugins[target_id]
            if hasattr(plugin, "on_command"):
                try:
                    plugin.on_command(cmd, args)
                except Exception as e:
                    logger.error(f"Plugin {target_id} command error: {e}")
            else:
                logger.warning(f"Plugin {target_id} does not handle commands")
        else:
            logger.warning(f"Plugin target '{target_id}' not found")