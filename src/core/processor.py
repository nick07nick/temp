# src/core/processor.py
import time
from typing import List, Dict, Optional, Any

import numpy as np
from loguru import logger

from src.core.event_bus import EventBus
from src.core.pipeline import PipelineStage, FrameContext
# Не забудь импорты
from src.data.schemas import SystemState, PluginStatus, CameraConfig, PluginCommand
from src.core.config import CORE_PIPELINE
from src.core.loader import load_stage_by_path, scan_plugins


class Processor:
    """
    Движок обработки кадров (работает внутри CameraWorker).
    Запускает стадии последовательно, защищает от сбоев, собирает метрики.
    Оптимизирован для снижения нагрузки на CPU (Manual Dict Assembly).
    """

    def __init__(self, bus: EventBus, camera_id: int = 0):
        self.bus = bus
        self.camera_id = camera_id

        # Списки стадий
        self.stages: List[PipelineStage] = []
        self._stage_map: Dict[str, PipelineStage] = {}

        # Состояние здоровья плагинов
        # { "stage_name": {"errors": 0, "active": True, "perf_ms": 0.0} }
        self._health_map: Dict[str, Dict] = {}

        self._load_pipeline()

    def _load_pipeline(self):
        """Загрузка ядра и плагинов"""
        # 1. Загружаем Core (Detection, Tracking...)
        for stage_path in CORE_PIPELINE:
            stage = load_stage_by_path(stage_path)
            if stage:
                self._register_stage(stage, is_core=True)

        # 2. Загружаем Плагины (из папки plugins)
        plugins = scan_plugins()
        for stage in plugins:
            # Некоторые плагины могут требовать доступ к шине
            if hasattr(stage, "bus"):
                stage.bus = self.bus
            self._register_stage(stage, is_core=False)

        logger.info(f"🧩 Processor initialized with {len(self.stages)} stages.")

    def _register_stage(self, stage: PipelineStage, is_core: bool):
        """Регистрация стадии во внутренних структурах"""
        self.stages.append(stage)
        self._stage_map[stage.name] = stage
        self._health_map[stage.name] = {
            "active": True,
            "errors": 0,
            "is_core": is_core,
            "perf_ms": 0.0
        }

    # === COMMAND ROUTING ===

    def handle_command(self, cmd: PluginCommand):
        """
        Маршрутизация команд с подробным логированием.
        """
        target = cmd.target
        command_name = cmd.cmd

        # [FIX] Удалил дублирующийся блок кода, который вызывал двойное срабатывание

        # 1. Broadcast (всем)
        if target == "broadcast" or target == "all":
            logger.info("📢 Broadcasting command...")
            for stage in self.stages:
                try:
                    if hasattr(stage, "handle_command"):
                        stage.handle_command(command_name, cmd.args)
                except Exception as e:
                    logger.error(f"💥 Stage '{stage.name}' failed broadcast: {e}")
            return

        # 2. Unicast (конкретной стадии)
        # ЛОГ 2: Есть ли такой плагин в карте?
        if target in self._stage_map:
            stage = self._stage_map[target]
            # logger.info(f"✅ Target '{target}' FOUND. Dispatching to {stage.__class__.__name__}")

            if hasattr(stage, "handle_command"):
                try:
                    stage.handle_command(command_name, cmd.args)
                except Exception as e:
                    logger.error(f"❌ Error inside stage '{target}': {e}")

            # Fallback: set_params
            elif command_name == "set_params":
                logger.info(f"⚙️ Applying set_params directly to {target}")
                for k, v in cmd.args.items():
                    if hasattr(stage, k):
                        setattr(stage, k, v)
        else:
            # ЛОГ 3: Если цель не найдена (самая частая ошибка)
            available_plugins = list(self._stage_map.keys())
            # logger.warning(f"🚫 Target '{target}' NOT FOUND in pipeline. Available: {available_plugins}")

    # === PROCESSING LOOP ===

    def process_frame(self, frame: np.ndarray, frame_id: int, current_config: CameraConfig):
        """
        Запуск пайплайна для одного кадра.
        """
        # 1. Создаем контекст
        # [FIX] Передаем bus и camera_id СРАЗУ в конструктор.
        # Это критически важно, чтобы UIContext внутри сразу получил ID.
        ctx = FrameContext(
            frame_ref=frame,
            frame_id=frame_id,
            config=current_config,
            bus=self.bus,  # <-- Передаем
            camera_id=self.camera_id  # <-- Передаем
        )

        # Собираем активные плагины (сразу в dict, чтобы не создавать лишние объекты)
        active_plugins_data = []

        # 2. Прогон по стадиям
        for stage in self.stages:
            meta = self._health_map[stage.name]

            # Пропускаем отключенные
            if not meta["active"]:
                active_plugins_data.append({
                    "id": stage.name,
                    "is_active": False,
                    "performance_ms": 0
                })
                continue

            t0 = time.perf_counter()
            try:
                # Запуск обработки
                # PipelineStage теперь сам обновит свой internal camera_id, если нужно
                stage.run(ctx)

                if meta["errors"] > 0: meta["errors"] = 0

            except Exception as e:
                meta["errors"] += 1
                if hasattr(ctx, "add_error"):
                    ctx.add_error(stage.name, str(e))

                logger.error(f"Stage '{stage.name}' failed: {e}")

                if meta["errors"] >= 20:  # Порог 20 ошибок
                    meta["active"] = False
                    logger.critical(f"🔌 Stage '{stage.name}' DISABLED.")

            dt = (time.perf_counter() - t0) * 1000
            meta["perf_ms"] = dt

            # Добавляем в список
            active_plugins_data.append({
                "id": stage.name,
                "is_active": meta["active"],
                "performance_ms": dt
            })

        # 3. Сборка результатов (ОПТИМИЗИРОВАННАЯ ЧАСТЬ)

        ui_updates = {"notifications": [], "widgets": []}
        if hasattr(ctx, "ui") and hasattr(ctx.ui, "get_updates"):
            ui_updates = ctx.ui.get_updates()

        # Получаем сырые данные из контекста
        raw_results = ctx.data_snapshot if hasattr(ctx, "data_snapshot") else {}

        clean_results = {}
        # Аккуратная конвертация данных для JSON
        for k, v in raw_results.items():
            if isinstance(v, list):
                clean_list = []
                for item in v:
                    if hasattr(item, "model_dump"):
                        clean_list.append(item.model_dump())
                    elif hasattr(item, "dict"):
                        clean_list.append(item.dict())
                    elif hasattr(item, "__dict__"):
                        clean_list.append(item.__dict__)
                    else:
                        clean_list.append(item)
                clean_results[k] = clean_list

            elif isinstance(v, (np.integer, np.floating)):
                clean_results[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif isinstance(v, np.ndarray):
                clean_results[k] = v.tolist()
            else:
                clean_results[k] = v

        # [PERFORMANCE] Троттлинг конфига: шлем полный конфиг только раз в 60 кадров
        config_payload = {}
        if frame_id % 60 == 0:
            config_payload = current_config.dict() if hasattr(current_config, "dict") else current_config.model_dump()

        # Конвертация ошибок
        errors_list = []
        for e in getattr(ctx, "errors", []):
            if hasattr(e, "dict"):
                errors_list.append(e.dict())
            elif hasattr(e, "model_dump"):
                errors_list.append(e.model_dump())
            else:
                errors_list.append(str(e))

        # Собираем payload вручную как DICT
        state_payload = {
            "frame_id": frame_id,
            "fps": 0.0,
            "errors": errors_list,
            "active_plugins": active_plugins_data,
            "camera_config": config_payload,
            "notifications": ui_updates["notifications"],
            "widgets": ui_updates["widgets"],  # Здесь уже будут виджеты с camera_id
            "results": clean_results,
            "camera_id": self.camera_id
        }

        # 4. Отправка в шину
        self.bus.publish_stream(state_payload)