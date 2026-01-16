import numpy as np
from scipy.spatial import distance as dist
from collections import OrderedDict
import time
from typing import List, Dict, Any
from loguru import logger

from src.core.pipeline import PipelineStage, FrameContext
from src.data.models import Point2D


class CentroidTrackerStage(PipelineStage):
    """
    Модуль трекинга с учетом вектора скорости (Inertia Tracking).
    Помогает не терять ID при быстром движении.
    """

    def __init__(self):
        super().__init__(name="tracker")

        self.next_id = 1
        self.objects: OrderedDict[int, Point2D] = OrderedDict()
        self.disappeared: OrderedDict[int, int] = OrderedDict()

        # Настройки
        self.max_disappeared = 45  # 0.5 сек при 90 FPS
        self.max_distance = 150  # Макс смещение в пикселях (можно увеличить, т.к. есть предсказание)

        # Метрики FPS
        self._last_ts = time.time()
        self._fps = 0.0

    def register(self, point: Point2D):
        """Регистрирует новый объект"""
        point.id = self.next_id
        point.label = f"ID {self.next_id}"
        point.age = 0
        point.is_stable = False

        # Инициализируем скорости нулями, если их нет
        if not hasattr(point, 'v_x') or point.v_x is None:
            point.v_x = 0.0
            point.v_y = 0.0

        self.objects[self.next_id] = point
        self.disappeared[self.next_id] = 0
        self.next_id += 1

    def deregister(self, object_id):
        del self.objects[object_id]
        del self.disappeared[object_id]

    def process(self, ctx: FrameContext):
        # 1. Входные данные (от BlobDetection)
        input_points: List[Point2D] = ctx.get_data("vision", "keypoints", [])

        # Рассчитываем dt (время с прошлого кадра) для корректного расчета скорости
        # В идеале нужно хранить timestamp предыдущего кадра, но пока берем фиксированный
        dt = 1.0 / 90.0  # Приближенно, или взять (ctx.timestamp - self._last_process_time)

        # Если трекер пуст, просто регистрируем всё
        if len(self.objects) == 0:
            for p in input_points:
                self.register(p)
            self._finalize(ctx)
            return

        # 2. Подготовка списков
        object_ids = list(self.objects.keys())

        # --- PREDICTIVE LOGIC ---
        # Вместо текущих координат берем ПРЕДСКАЗАННЫЕ: (x + v_x*dt, y + v_y*dt)
        predicted_centroids = []
        for oid in object_ids:
            obj = self.objects[oid]
            # Предсказание позиции (Линейная экстраполяция)
            pred_x = obj.x + (obj.v_x * dt if obj.v_x else 0)
            pred_y = obj.y + (obj.v_y * dt if obj.v_y else 0)
            predicted_centroids.append([pred_x, pred_y])

        predicted_centroids = np.array(predicted_centroids)

        # Если входных точек нет, увеличиваем счетчик пропажи
        if not input_points:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self.deregister(obj_id)
            self._finalize(ctx)
            return

        input_centroids = np.array([[p.x, p.y] for p in input_points])

        # 3. Расчет дистанций (между Предсказанием и Реальностью)
        D = dist.cdist(predicted_centroids, input_centroids)

        # Находим соответствия (Greedy approach)
        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows = set()
        used_cols = set()

        for (row, col) in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue

            # Проверяем дистанцию (если предсказание ошиблось слишком сильно - это не тот маркер)
            if D[row, col] > self.max_distance:
                continue

            object_id = object_ids[row]
            new_observation = input_points[col]
            existing_object = self.objects[object_id]

            # === ОБНОВЛЕНИЕ ОБЪЕКТА ===

            # 1. Расчет мгновенной скорости
            # v_x = (new_x - old_x) / dt
            # Используем update_speed из модели Point2D (если он есть) или считаем вручную
            inst_v_x = (new_observation.x - existing_object.x) / dt
            inst_v_y = (new_observation.y - existing_object.y) / dt

            # Сглаживание скорости (Exponential Moving Average), чтобы не дергалось от шума
            alpha = 0.5  # Коэффициент сглаживания
            prev_v_x = existing_object.v_x if existing_object.v_x else 0.0
            prev_v_y = existing_object.v_y if existing_object.v_y else 0.0

            existing_object.v_x = prev_v_x * alpha + inst_v_x * (1 - alpha)
            existing_object.v_y = prev_v_y * alpha + inst_v_y * (1 - alpha)

            # 2. Обновляем координаты
            existing_object.x = new_observation.x
            existing_object.y = new_observation.y
            existing_object.confidence = new_observation.confidence

            # Сброс счетчика исчезновения
            existing_object.age += 1
            self.disappeared[object_id] = 0

            # Важно: сбрасываем undistorted координаты, их должен пересчитать следующий стейдж
            existing_object.ux = None
            existing_object.uy = None

            used_rows.add(row)
            used_cols.add(col)

        # 4. Обработка "пропавших" (тех, кого не нашли)
        unused_rows = set(range(0, D.shape[0])).difference(used_rows)
        for row in unused_rows:
            obj_id = object_ids[row]
            # Если объект потерялся, можно обнулить скорость или оставить старую (инерция)
            # Пока оставим как есть, но увеличим счетчик пропажи
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > self.max_disappeared:
                self.deregister(obj_id)

        # 5. Регистрация новых (тех, кого не сматчили)
        unused_cols = set(range(0, D.shape[1])).difference(used_cols)
        for col in unused_cols:
            self.register(input_points[col])

        self._finalize(ctx)

    def _finalize(self, ctx: FrameContext):
        # Отправляем только живые объекты
        tracked_list = []
        for obj_id, obj in self.objects.items():
            if self.disappeared[obj_id] == 0:
                tracked_list.append(obj)

        ctx.set_data("vision", "keypoints", tracked_list)

        # UI Throttling
        if ctx.frame_id % 15 == 0:
            self._update_fps()
            ctx.ui.update_widget(
                "tracker_stat",
                "Tracking",
                {"active": len(tracked_list), "total": self.next_id - 1},
                "text"
            )

    def _update_fps(self):
        now = time.time()
        delta = now - self._last_ts
        if delta > 0:
            self._fps = 0.9 * self._fps + 0.1 * (1.0 / delta)
        self._last_ts = now

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        if cmd == "reset_tracker":
            self.objects.clear()
            self.disappeared.clear()
            self.next_id = 1
            logger.info("♻️ Tracker reset")