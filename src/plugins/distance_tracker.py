# src/plugins/distance_tracker.py
import cv2
import math
import json
import os
import time
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext
from src.core.config import ROOT_DIR


class DistanceTrackerPlugin(PipelineStage):
    def __init__(self):
        super().__init__("distance_tracker")
        self.is_tracking = False
        self.target_id = None  # ID точки, которую трекаем (int)

        # Начальная позиция (Origin)
        self.start_wx = None
        self.start_wy = None
        self.start_screen_pos = None  # (x, y) для отрисовки линии

        # Метаданные качества (загрузим из конфигов)
        self.lens_error = 0.0
        self.scale_factor = 0.0  # px_per_cm
        self._load_metadata()

        self.current_distance = 0.0

    def _load_metadata(self):
        """Пытаемся достать данные о точности из конфигов"""
        try:
            # 1. Читаем Lens config (ищем RMS если он там сохранен)
            lens_path = ROOT_DIR / "config" / "calibration_cam_0.json"
            if os.path.exists(lens_path):
                with open(lens_path, 'r') as f:
                    d = json.load(f)
                    # В будущем надо дописать в lens.py сохранение поля 'rms'
                    self.lens_error = d.get("rms", 0.0)

            # 2. Читаем World config (ищем масштаб)
            world_path = ROOT_DIR / "config" / "world_cam_0.json"
            if os.path.exists(world_path):
                with open(world_path, 'r') as f:
                    d = json.load(f)
                    self.scale_factor = d.get("px_per_cm", 0.0)

        except Exception as e:
            logger.warning(f"DistanceTracker meta load error: {e}")

    def handle_command(self, cmd: str, args: dict):
        if cmd == "start_tracking":
            try:
                # Фронт присылает ID как строку, но в Point2D id может быть int (ArUco) или str (Mediapipe)
                # Попробуем привести к int, если это число
                raw_id = args.get("point_id")
                if str(raw_id).isdigit():
                    self.target_id = int(raw_id)
                else:
                    self.target_id = raw_id

                self.is_tracking = True
                self.start_wx = None  # Сброс, захватим в process()
                logger.info(f"📏 Start tracking point {self.target_id}")
            except Exception as e:
                logger.error(f"Start track error: {e}")

        elif cmd == "stop_tracking":
            self.is_tracking = False
            self.start_wx = None
            self.current_distance = 0.0
            logger.info("📏 Stop tracking")

    def process(self, ctx: FrameContext):
        # Всегда отправляем UI данные, даже если не трекаем
        if ctx.frame_id % 5 == 0:  # Оптимизация частоты отправки
            self._send_ui(ctx)

        if not self.is_tracking or self.target_id is None:
            return

        points = ctx.get_data("vision", "keypoints", [])
        target_point = None

        # Ищем нашу точку
        for p in points:
            if p.id == self.target_id:
                target_point = p
                break

        if target_point is None:
            # Точка потеряна
            return

        # Проверяем, есть ли мировые координаты (PerspectiveStage должен отработать)
        if target_point.wx is None or target_point.wy is None:
            # Если нет калибровки, дистанция будет 0 (или можно считать в пикселях)
            return

        # 1. ЗАХВАТ НАЧАЛА (в первый кадр после старта)
        if self.start_wx is None:
            self.start_wx = target_point.wx
            self.start_wy = target_point.wy
            self.start_screen_pos = (int(target_point.x), int(target_point.y))
            return

        # 2. РАСЧЕТ ДИСТАНЦИИ
        dx = target_point.wx - self.start_wx
        dy = target_point.wy - self.start_wy
        self.current_distance = math.sqrt(dx ** 2 + dy ** 2)
        # logger.info(f"dx dy current_distance : {dx} {dy} {self.current_distance}")

        # 3. ОТРИСОВКА (Визуальная связь)
        if ctx.frame is not None and self.start_screen_pos:
            # Линия от старта до текущей
            cv2.line(ctx.frame,
                     self.start_screen_pos,
                     (int(target_point.x), int(target_point.y)),
                     (0, 255, 255), 2)

            # Текст с дистанцией рядом с точкой
            label = f"{self.current_distance:.1f} cm"
            cv2.putText(ctx.frame, label,
                        (int(target_point.x) + 10, int(target_point.y) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # Отмечаем крестиком точку старта
            sx, sy = self.start_screen_pos
            cv2.drawMarker(ctx.frame, (sx, sy), (0, 0, 255), cv2.MARKER_CROSS, 15, 2)

    def _send_ui(self, ctx):
        # [NEW] Получаем список видимых точек для авто-выбора ID на фронте
        points = ctx.get_data("vision", "keypoints", [])
        available_ids = [p.id for p in points]

        payload = {
            "is_tracking": self.is_tracking,
            "distance": round(self.current_distance, 2),
            "target_id": str(self.target_id) if self.target_id is not None else "",
            # Метаданные (ошибка и масштаб)
            "lens_rms": self.lens_error,
            "scale": round(self.scale_factor, 2),
            "available_ids": available_ids  # Отправляем список ID
        }
        ctx.ui.update_widget("distance_tracker", "Distance", payload)