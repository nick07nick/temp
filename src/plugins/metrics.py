# src/core/metrics.py
import math
from src.data.models import Point2D


def calculate_angle(a: Point2D, b: Point2D, c: Point2D) -> float:
    """
    Вычисляет угол между тремя точками (в градусах).
    b - центральная точка (вершина угла).
    """
    # Вектор BA
    ba_x = a.x - b.x
    ba_y = a.y - b.y

    # Вектор BC
    bc_x = c.x - b.x
    bc_y = c.y - b.y

    dot_product = ba_x * bc_x + ba_y * bc_y
    magnitude_ba = math.sqrt(ba_x ** 2 + ba_y ** 2)
    magnitude_bc = math.sqrt(bc_x ** 2 + bc_y ** 2)

    if magnitude_ba * magnitude_bc == 0:
        return 0.0

    cosine_angle = dot_product / (magnitude_ba * magnitude_bc)
    # Корректировка для float точности
    cosine_angle = max(-1.0, min(1.0, cosine_angle))

    angle = math.acos(cosine_angle)
    return math.degrees(angle)