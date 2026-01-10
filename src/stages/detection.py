import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
from loguru import logger

from src.core.pipeline import PipelineStage, FrameContext
from src.data.models import Point2D


class BlobDetectionStage(PipelineStage):
    """
    Модуль детекции с учетом физической дистанции между маркерами.
    """

    def __init__(self):
        super().__init__(name="blob_detector")
        self.min_area = 15
        self.max_blobs = 50

        # Настройка минимальной дистанции
        self.min_dist_cm = 5.0  # 5 сантиметров
        self.default_scale = 10.0  # Пикселей в см (если нет калибровки)

        logger.debug(f"👁️ {self.name} ready. MinArea={self.min_area}, MinDist={self.min_dist_cm}cm")

    def process(self, ctx: FrameContext):
        if ctx.frame is None:
            return

        # 1. Получаем настройки
        thresh_val = ctx.config.threshold if ctx.config.threshold is not None else 200

        # Пытаемся получить масштаб из калибровки (CalibrationWorldStage обычно кладет это в ctx)
        # Ожидаем, что в ctx.data_snapshot["calibration"]["scale"] лежит float (px/cm)
        world_data = ctx.get_data("calibration", "world_data", {})
        px_per_cm = world_data.get("scale", self.default_scale)

        # Вычисляем минимальную дистанцию в пикселях
        min_dist_px = self.min_dist_cm * px_per_cm

        try:
            # 2. Обработка изображения
            if len(ctx.frame.shape) == 3:
                gray = cv2.cvtColor(ctx.frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = ctx.frame

            _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)

            # Используем RETR_EXTERNAL, чтобы не ловить "бублики" (вложенные контуры)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 3. Сбор кандидатов
            candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self.min_area:
                    continue

                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    # Сохраняем кандидата: (Area, Point2D)
                    p = Point2D(x=cX, y=cY, confidence=1.0, label="blob")
                    candidates.append({"p": p, "area": area, "cnt": cnt})

            # 4. Фильтрация по дистанции (Spatial NMS)
            # Сортируем по площади: самые жирные пятна главнее
            candidates.sort(key=lambda x: x["area"], reverse=True)

            accepted_points: List[Point2D] = []

            for cand in candidates:
                pt = cand["p"]
                is_too_close = False

                # Проверяем дистанцию до уже принятых точек
                for existing in accepted_points:
                    dist = np.sqrt((pt.x - existing.x) ** 2 + (pt.y - existing.y) ** 2)
                    if dist < min_dist_px:
                        is_too_close = True
                        break

                if not is_too_close:
                    accepted_points.append(pt)
                    if len(accepted_points) >= self.max_blobs:
                        break

            # 5. Публикация
            ctx.set_data("vision", "keypoints", accepted_points)

            # UI Update (Throttle)
            if ctx.frame_id % 15 == 0:
                status = "success" if 0 < len(accepted_points) < self.max_blobs else "warning"
                if len(accepted_points) == 0: status = "neutral"

                ctx.ui.update_widget(
                    widget_id="blobs_found",
                    title="Markers",
                    data={"value": len(accepted_points), "status": status},
                    w_type="status_indicator"
                )

        except Exception as e:
            logger.error(f"CV Error in {self.name}: {e}")
            ctx.add_error(self.name, f"CV Crash: {str(e)}")

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        if cmd == "set_min_area":
            val = args.get("value")
            if isinstance(val, (int, float)):
                self.min_area = int(val)
        elif cmd == "set_min_dist_cm":
            val = args.get("value")
            if isinstance(val, (int, float)):
                self.min_dist_cm = float(val)