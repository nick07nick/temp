# src/core/stages/vision.py
import cv2
import numpy as np
from typing import Dict, List, Tuple
from collections import OrderedDict
from scipy.spatial import distance as dist  # Используем scipy для быстрого расчета расстояний

from src.core.pipeline import PipelineStage
from src.core.pipeline import FrameContext
from src.data.models import Point2D


class VisionTrackingStage(PipelineStage):
    def __init__(self):
        super().__init__(name="vision")

        # --- НАСТРОЙКИ ТРЕКЕРА ---
        self.max_disappeared = 10  # Сколько кадров помним точку, если она исчезла
        self.max_distance = 100  # Макс. расстояние (пиксели), на которое точка может сместиться за кадр

        # --- СОСТОЯНИЕ ---
        self.next_object_id = 1  # Начинаем ID с 1
        self.objects: Dict[int, Tuple[int, int]] = OrderedDict()  # ID -> (x, y)
        self.disappeared: Dict[int, int] = OrderedDict()  # ID -> кол-во кадров пропуска

        # Для сглаживания мерцания (память)
        self.last_valid_points = []

    def register(self, centroid):
        """Регистрирует новый объект с новым ID"""
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def deregister(self, object_id):
        """Удаляет объект из отслеживания"""
        del self.objects[object_id]
        del self.disappeared[object_id]

    def update_tracker(self, input_centroids: List[Tuple[int, int]]):
        """
        Магия трекинга: сопоставляем новые координаты со старыми ID.
        """
        # 1. Если вообще нет новых точек
        if len(input_centroids) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return

        # 2. Если трекер пуст, просто регистрируем всё, что нашли
        if len(self.objects) == 0:
            for i in range(0, len(input_centroids)):
                self.register(input_centroids[i])
            return

        # 3. Сопоставление (Matching)
        # Берем текущие ID и их последние координаты
        object_ids = list(self.objects.keys())
        object_centroids = list(self.objects.values())

        # Считаем матрицу расстояний между ВСЕМИ старыми и ВСЕМИ новыми точками
        # D[i, j] = расстояние между старой точкой i и новой j
        D = dist.cdist(np.array(object_centroids), input_centroids)

        # Находим минимальные расстояния
        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows = set()
        used_cols = set()

        for (row, col) in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue

            # Если расстояние слишком большое, считаем, что это не та точка
            if D[row, col] > self.max_distance:
                continue

            # Обновляем координаты старого ID
            object_id = object_ids[row]
            self.objects[object_id] = input_centroids[col]
            self.disappeared[object_id] = 0  # Сбрасываем счетчик исчезновений

            used_rows.add(row)
            used_cols.add(col)

        # 4. Обработка исчезнувших и новых

        # Те, кого мы не обновили (исчезли)
        unused_rows = set(range(0, D.shape[0])).difference(used_rows)
        for row in unused_rows:
            object_id = object_ids[row]
            self.disappeared[object_id] += 1
            if self.disappeared[object_id] > self.max_disappeared:
                self.deregister(object_id)

        # Те, кого мы не использовали (новые)
        unused_cols = set(range(0, D.shape[1])).difference(used_cols)
        for col in unused_cols:
            self.register(input_centroids[col])

    def process(self, ctx: FrameContext):
        frame = ctx.frame
        if frame is None: return

        # --- 1. DETECT (CV2) ---
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Берем threshold из конфига
        thresh_val = getattr(ctx.config, 'threshold', 200)
        if thresh_val is None: thresh_val = 200

        _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        input_centroids = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 10: continue  # Шум
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                input_centroids.append((cX, cY))

        # --- 2. TRACK (Update IDs) ---
        self.update_tracker(input_centroids)

        # --- 3. EXPORT ---
        # Превращаем внутренний словарь трекера в список Point2D
        final_points = []
        for obj_id, (x, y) in self.objects.items():
            # Показываем только те точки, которые НЕ считаются исчезнувшими прямо сейчас
            if self.disappeared[obj_id] == 0:
                final_points.append(Point2D(x=x, y=y, id=obj_id, label=f"M{obj_id}"))

        # Память для анти-мерцания (если вдруг на кадре вообще пусто)
        if final_points:
            self.last_valid_points = final_points

        ctx.set_data("vision", "keypoints", final_points)
        ctx.set_data("vision", "count", len(final_points))