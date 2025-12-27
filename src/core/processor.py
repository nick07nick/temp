# src/core/processor.py
import cv2
import numpy as np
import logging
from typing import List, Optional, Deque
from collections import deque
from src.core.models import Point2D

logger = logging.getLogger("BikeFit.Processor")


class MarkerDetector:
    """
    Отвечает за поиск ярких пятен (Thresholding).
    """

    def __init__(self, threshold: int = 150):
        self.threshold_val = threshold

    def process_frame(self, frame: np.ndarray) -> List[Point2D]:
        # Используем красный канал (или Grayscale)
        if frame.ndim == 3:
            gray = frame[:, :, 2]
        else:
            gray = frame

        _, mask = cv2.threshold(gray, self.threshold_val, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        points = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 5: continue  # Фильтр шума

            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cX = M["m10"] / M["m00"]
                cY = M["m01"] / M["m00"]
                points.append(Point2D(x=cX, y=cY, confidence=1.0))

        return points


class PointTracker:
    """
    Модуль трекинга и интерполяции.
    Помогает, если маркер пропал на 1-3 кадра.
    """

    def __init__(self, history_size: int = 5, max_gap: int = 3):
        self.history: Deque[Optional[Point2D]] = deque(maxlen=history_size)
        self.max_gap = max_gap
        self.missing_counter = 0

    def update(self, detected_points: List[Point2D]) -> List[Point2D]:
        """
        Принимает "сырые" точки от детектора.
        Возвращает стабилизированную точку (или предсказанную).
        Пока поддерживаем только 1 маркер (Single Point Tracking).
        """
        current_point = None

        # 1. Если детектор нашел точку - берем её
        if detected_points:
            # Если найдено несколько, берем самую близкую к предыдущей (Nearest Neighbor)
            # Для простоты пока берем первую (0)
            current_point = detected_points[0]
            self.missing_counter = 0
            self.history.append(current_point)
            return [current_point]

        # 2. Если точки нет - пытаемся интерполировать/экстраполировать
        self.missing_counter += 1

        if self.missing_counter <= self.max_gap and len(self.history) >= 2:
            # Линейная экстраполяция: P_new = P_last + (P_last - P_prev)
            p_last = self.history[-1]
            p_prev = self.history[-2]

            if p_last and p_prev:
                dx = p_last.x - p_prev.x
                dy = p_last.y - p_prev.y

                predicted_x = p_last.x + dx
                predicted_y = p_last.y + dy

                # Создаем "фантомную" точку с низким confidence
                phantom_point = Point2D(x=predicted_x, y=predicted_y, confidence=0.5)
                self.history.append(phantom_point)  # Добавляем в историю, чтобы следующая экстраполяция шла от неё

                # logger.debug(f"Interpolated point at {predicted_x:.1f}, {predicted_y:.1f}")
                return [phantom_point]

        # Если пропуск слишком долгий - сбрасываемся
        if self.missing_counter > self.max_gap:
            self.history.clear()

        return []