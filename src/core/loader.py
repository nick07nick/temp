# src/core/loader.py
import importlib
import inspect
import os
from typing import List

from fastapi import APIRouter
from loguru import logger

from src.core.pipeline import PipelineStage


def load_stage_by_path(path: str) -> PipelineStage:
    """
    Загружает класс по строке "src.core.stages.vision.VisionTrackingStage"
    """
    try:
        module_path, class_name = path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        if not issubclass(cls, PipelineStage):
            raise TypeError(f"{class_name} is not a PipelineStage")

        logger.debug(f"🧩 Loaded Core Stage: {class_name}")
        return cls()  # Создаем экземпляр
    except Exception as e:
        logger.error(f"❌ Failed to load stage '{path}': {e}")
        return None


def scan_plugins(package_path: str = "src.plugins") -> List[PipelineStage]:
    """
    Рекурсивно сканирует папку src/plugins (и подпапки) и загружает все найденные классы,
    наследуемые от PipelineStage.
    Игнорирует папки, начинающиеся с точки (например, .disabled).
    """
    plugins = []

    # 1. Получаем реальный путь к корню плагинов
    base_dir = os.path.dirname(os.path.abspath(__file__))  # src/core
    root_dir = os.path.dirname(os.path.dirname(base_dir))  # Project root
    plugins_dir = os.path.join(root_dir, package_path.replace(".", "/"))

    if not os.path.exists(plugins_dir):
        logger.warning(f"Plugins directory not found: {plugins_dir}")
        return []

    # 2. Рекурсивный обход (os.walk)
    for root, dirs, files in os.walk(plugins_dir):
        # [FILTER] Исключаем папки, начинающиеся с точки (.git, .disabled, etc.)
        # Изменяем список dirs "на лету" (in-place), чтобы os.walk туда не заходил
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file_name in files:
            # Грузим только .py файлы, игнорируем __init__.py (обычно там только экспорты)
            if file_name.endswith(".py") and not file_name.startswith("__"):

                # Строим путь к модулю относительно src/plugins
                # Пример: root=.../src/plugins/calibration, file=manager.py
                # rel_path = "calibration"
                rel_path = os.path.relpath(root, plugins_dir)

                if rel_path == ".":
                    # Файл лежит прямо в src/plugins
                    module_name = file_name[:-3]
                    full_module_path = f"{package_path}.{module_name}"
                else:
                    # Файл во вложенной папке -> превращаем слеши в точки
                    # calibration/manager -> calibration.manager
                    sub_package = rel_path.replace(os.path.sep, ".")
                    module_name = file_name[:-3]
                    full_module_path = f"{package_path}.{sub_package}.{module_name}"

                try:
                    module = importlib.import_module(full_module_path)

                    # Ищем классы внутри модуля
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # Проверяем, что это PipelineStage, но не сам базовый класс
                        if issubclass(obj, PipelineStage) and obj is not PipelineStage:
                            # [FIX] Защита от дублей: загружаем только если класс определен В ЭТОМ модуле
                            if obj.__module__ == module.__name__:
                                logger.info(f"🔌 Discovered Plugin: {name} [{full_module_path}]")
                                plugins.append(obj())  # Создаем экземпляр
                except Exception as e:
                    logger.error(f"⚠️ Error loading plugin from {full_module_path}: {e}")

    return plugins


def scan_api_routers(package_path: str = "src.plugins") -> List[APIRouter]:
    """
    Рекурсивно сканирует папку плагинов и ищет переменные 'router' (экземпляры APIRouter).
    Игнорирует папки, начинающиеся с точки.
    """
    routers = []

    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(base_dir))
    plugins_dir = os.path.join(root_dir, package_path.replace(".", "/"))

    if not os.path.exists(plugins_dir):
        return []

    for root, dirs, files in os.walk(plugins_dir):
        # [FILTER] Игнорируем скрытые папки
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file_name in files:
            if file_name.endswith(".py") and not file_name.startswith("__"):

                rel_path = os.path.relpath(root, plugins_dir)

                if rel_path == ".":
                    module_name = file_name[:-3]
                    full_module_path = f"{package_path}.{module_name}"
                else:
                    sub_package = rel_path.replace(os.path.sep, ".")
                    module_name = file_name[:-3]
                    full_module_path = f"{package_path}.{sub_package}.{module_name}"

                try:
                    module = importlib.import_module(full_module_path)

                    # Ищем переменную с именем 'router' и типом APIRouter
                    if hasattr(module, "router") and isinstance(module.router, APIRouter):
                        logger.info(f"🌐 Discovered API Router in: {full_module_path}")
                        routers.append(module.router)

                except Exception as e:
                    logger.error(f"⚠️ Error loading router from {full_module_path}: {e}")

    return routers