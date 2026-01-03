# src/core/processor.py
import time
import cv2
import numpy as np
from typing import List, Optional, Any
from loguru import logger

from src.core.event_bus import EventBus
from src.core.config import settings

# Импорт пайплайна
from src.core.pipeline.base import BaseStage
from src.core.pipeline.context import ProcessingContext
# Core Stages (Всегда включены)
from src.core.pipeline.vision import VisionTrackingStage
from src.core.pipeline.calibration import CalibrationStage
from src.core.pipeline.filtering import SmoothingStage
# NEW: Plugin Manager
from src.core.plugin_manager import PluginManager


class Processor:
    def __init__(
            self,
            bus: EventBus,
            shm_config: Any,
            calibration_manager: Any  # Optional[CalibrationManager]
    ):
        self.bus = bus
        self.camera_id = settings.CAMERA_INDEX

        # === 1. CORE PIPELINE (Жесткий фундамент) ===
        self.core_pipeline: List[BaseStage] = []

        self.core_pipeline.append(VisionTrackingStage())
        if calibration_manager:
            self.core_pipeline.append(CalibrationStage(calibration_manager))
        self.core_pipeline.append(SmoothingStage())

        # === 2. PLUGIN MANAGER (Гибкая надстройка) ===
        # Загружает плагины из папки src/plugins
        self.plugin_manager = PluginManager("src/plugins")

        logger.info(f"Processor initialized. Core stages: {len(self.core_pipeline)}")

    def process_frame(self, frame: np.ndarray, frame_id: int):
        current_time = time.time()

        # Подготовка Gray (один раз для всех)
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Создаем контекст
        ctx = ProcessingContext(
            frame=frame,
            frame_gray=gray,
            frame_id=frame_id,
            timestamp=current_time,
            camera_id=self.camera_id
        )

        # A. Запускаем CORE Stages
        for stage in self.core_pipeline:
            try:
                stage.process(ctx)
            except Exception as e:
                logger.error(f"Core Stage {type(stage).__name__} error: {e}")

        # B. Запускаем PLUGINS
        # (Они получают уже отфильтрованные точки)
        self.plugin_manager.process_all(ctx)

        # C. Отправка данных
        self._publish_results(ctx)

        # D. Обработка входящих команд (в конце кадра)
        self._handle_commands()

    def _handle_commands(self):
        """Читает очередь команд и маршрутизирует их"""
        while True:
            cmd_data = self.bus.get_command()
            if not cmd_data:
                break

            # Проверяем, кому адресовано
            msg_type = cmd_data.get("type", "core")  # По дефолту core

            if msg_type == "plugin_command":
                # Маршрутизация в плагин
                target = cmd_data.get("target")
                cmd = cmd_data.get("cmd")
                args = cmd_data.get("args")
                self.plugin_manager.dispatch_command(target, cmd, args)
            else:
                # Старая логика для ядра (если нужна)
                pass

    def _publish_results(self, ctx: ProcessingContext):
        export_points = []
        for p in ctx.points:
            export_points.append({
                "id": p.id,
                "x": round(p.x, 2),
                "y": round(p.y, 2),
                "c": p.confidence,
                "label": p.label,
                "predicted": p.is_predicted
            })

        packet = {
            "timestamp": ctx.timestamp,
            "cameras": {f"cam_{ctx.camera_id}": export_points},
            "frame_id": ctx.frame_id,
            "camera_id": ctx.camera_id,
            # ВАЖНО: Добавляем данные от плагинов в пакет!
            # Предполагаем, что плагины пишут в ctx.meta["plugins"]
            "plugins": ctx.meta.get("plugins", {})
        }

        if hasattr(self.bus, 'publish_stream_data'):
            self.bus.publish_stream_data(packet)
        else:
            self.bus.publish("stream_data", packet)