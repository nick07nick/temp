from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.models import Point2D


@dataclass
class ProcessingContext:
    frame: np.ndarray  # Исходный цветной кадр
    frame_gray: np.ndarray  # ЧБ кадр
    frame_id: int
    timestamp: float
    camera_id: int

    # Список точек, который модифицируется стадиями
    points: List[Point2D] = field(default_factory=list)

    # Флаг: были ли точки откалиброваны (undistorted)
    is_calibrated: bool = False

    # Метаданные для обмена между стадиями
    meta: Dict[str, Any] = field(default_factory=dict)