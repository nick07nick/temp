# src/hardware/mock_camera.py
import time
import math
import numpy as np
import logging
from typing import Tuple
from src.core.interfaces import ICamera

logger = logging.getLogger("BikeFit.Hardware.MockCam")


class MockCamera(ICamera):
    """
    Виртуальная камера. Теперь поддерживает фейковую "выдержку"
    (влияет на яркость рисуемой точки).
    """

    def __init__(self, width: int = 1920, height: int = 1200, fps: int = 30, camera_id: int = 0):
        self._width = width
        self._height = height
        self._fps = fps
        self._id = camera_id
        self._is_connected = False
        self._start_time = 0.0
        self._exposure_val = 100  # Дефолтное значение

    def connect(self) -> None:
        logger.info(f"Connecting MockCam #{self._id}...")
        self._is_connected = True
        self._start_time = time.time()

    def release(self) -> None:
        self._is_connected = False

    def get_resolution(self) -> Tuple[int, int]:
        return self._width, self._height

    def capture_to_buffer(self, shm_buffer: memoryview) -> bool:
        if not self._is_connected: return False

        time.sleep(1.0 / self._fps)
        elapsed = time.time() - self._start_time
        frame_idx = int(elapsed * self._fps)

        dst_array = np.ndarray((self._height, self._width, 3), dtype=np.uint8, buffer=shm_buffer)

        # Эмуляция вспышки (Sync)
        if 28 <= frame_idx <= 32:
            dst_array.fill(255)
            return True

        # Очистка фона
        dst_array.fill(0)

        # Движение точки
        cx, cy = self._width // 2, self._height // 2
        radius = 400
        angle = elapsed * 2.0

        offset_x = 0
        if self._id == 1: offset_x = 50
        if self._id == 2: offset_x = -50

        px = int(cx + math.cos(angle) * radius + offset_x)
        py = int(cy + math.sin(angle) * radius)

        # Рисуем точку
        if 0 <= px < self._width and 0 <= py < self._height:
            # Яркость зависит от "выдержки". Если exposure < 10, точка тусклая.
            brightness = min(255, max(50, self._exposure_val))
            color = [brightness, brightness, brightness]

            # Квадрат 10x10
            y1, y2 = max(0, py - 5), min(self._height, py + 5)
            x1, x2 = max(0, px - 5), min(self._width, px + 5)
            dst_array[y1:y2, x1:x2] = color

        return True

    def set_exposure(self, value: int) -> bool:
        """
        Эмуляция установки выдержки.
        """
        self._exposure_val = value
        logger.info(f"MockCam {self._id}: Simulated exposure set to {value}")
        return True