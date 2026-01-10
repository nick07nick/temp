# src/data/models.py
import time
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field
import numpy as np


# === 0. CONSTANTS & FLAGS ===

class FrameFlags:
    """
    Битовые флаги для заголовка кадра (Binary Protocol v2.1).
    """
    NONE = 0
    SYNC_FLASH = 1 << 0  # 0x01: Обнаружена резкая вспышка
    LOW_LIGHT = 1 << 1  # 0x02: Слишком темно
    MOVEMENT_DETECTED = 1 << 2  # 0x04: Детектор движения
    SECURITY_ALERT = 1 << 7  # 0x80: Нарушение безопасности


# === 1. Базовые примитивы ===

class Point2D(BaseModel):
    """
    Единая модель точки для всего пайплайна.
    Хранит состояние в трех системах координат:
    1. Экранная (x, y) - для визуализации.
    2. Исправленная (ux, uy) - для точной геометрии.
    3. Мировая (wx, wy) - для биомеханики.
    """
    # --- 1. Сырые экранные координаты (Raw Pixels) ---
    x: float
    y: float

    # Метаданные
    confidence: float = 1.0
    id: Optional[int] = None
    label: Optional[str] = None

    # Физика (заполняется в TrackingStage)
    v_x: float = 0.0
    v_y: float = 0.0
    speed: float = 0.0
    age: int = 0
    is_stable: bool = False

    # --- 2. Исправленные координаты (Undistorted Pixels) ---
    # Заполняется в UndistortStage.
    # Если калибровки нет -> равны x, y.
    ux: Optional[float] = None
    uy: Optional[float] = None

    # --- 3. Мировые координаты (World Metrics - cm/mm) ---
    # Заполняется в PerspectiveStage / CalibrationStage.
    wx: Optional[float] = None
    wy: Optional[float] = None

    def update_speed(self, new_x: float, new_y: float, dt: float):
        """
        Утилита для расчета мгновенной скорости.
        Используется в TrackingStage при обновлении точки.
        """
        if dt > 0:
            self.v_x = (new_x - self.x) / dt
            self.v_y = (new_y - self.y) / dt
            self.speed = (self.v_x ** 2 + self.v_y ** 2) ** 0.5


# === 2. Конфигурации Памяти ===

class SharedMemoryConfig(BaseModel):
    name: str
    size: int
    shape: Tuple[int, int, int] = (0, 0, 0)
    dtype: str = "uint8"


# === 3. Пакет данных кадра ===

class FrameData(BaseModel):
    camera_id: int
    frame_id: int
    timestamp: float
    points: List[Point2D]
    math_salt: float = 1.0
    flags: int = 0