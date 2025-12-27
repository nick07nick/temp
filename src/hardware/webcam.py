# src/hardware/webcam.py
import cv2
import time
import logging
import numpy as np
import subprocess
import os
from typing import Tuple, Optional
from src.core.interfaces import ICamera

logger = logging.getLogger("BikeFit.Hardware.Webcam")


class Webcam(ICamera):
    """
    Драйвер для работы с USB-камерами.
    - Видеопоток: OpenCV (Video4Linux2 / AVFoundation / MSMF)
    - Управление (Выдержка): Внешняя утилита uvc-util (через subprocess)
    """

    def __init__(self, camera_id: int = 0, width: int = 1280, height: int = 720, fps: int = 30):
        self._id = camera_id
        self._width = width
        self._height = height
        self._target_fps = fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_connected = False

        # --- UVC Configuration ---
        # Путь к скомпилированной утилите (Hardcoded path from user config)
        # В будущем можно вынести в конфиг файл или ENV переменную
        self._uvc_util_path = "/Users/nikfrants/Documents/it/BikeFit/uvc-util/src/uvc-util"
        self._exposure_param = "exposure-time-abs"

    def connect(self) -> None:
        logger.info(f"Connecting to USB Camera #{self._id} via OpenCV...")

        # cv2.CAP_ANY автоматически выберет лучший backend (AVFoundation на Mac)
        self._cap = cv2.VideoCapture(self._id, cv2.CAP_ANY)

        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open camera #{self._id}")

        # --- Настройка потока (MJPG для скорости) ---
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
        # Отключаем буферизацию, чтобы получать только свежие кадры (Low Latency)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Проверяем, что применилось
        real_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        real_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        real_fps = self._cap.get(cv2.CAP_PROP_FPS)

        logger.info(f"Camera #{self._id} initialized. Stream: {real_w}x{real_h} @ {real_fps} FPS")
        self._is_connected = True

        # Применяем дефолтную выдержку при старте (например, 100)
        # Это важно, чтобы камера не стартовала в Auto Exposure
        self.set_exposure(100)

    def release(self) -> None:
        if self._cap:
            self._cap.release()
        self._is_connected = False
        logger.info(f"Camera #{self._id} released.")

    def get_resolution(self) -> Tuple[int, int]:
        if self._cap:
            return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return self._width, self._height

    def capture_to_buffer(self, shm_buffer: memoryview) -> bool:
        """
        Захват кадра и копирование в SharedMemory.
        """
        if not self._is_connected or self._cap is None:
            return False

        ret, frame = self._cap.read()

        if not ret:
            # logger.warning(f"Camera #{self._id} dropped frame!")
            return False

        # Проверка размера буфера на переполнение
        expected_size = frame.nbytes
        if len(shm_buffer) < expected_size:
            logger.error(f"Buffer overflow! Frame: {expected_size}, Buffer: {len(shm_buffer)}")
            return False

        # Копируем данные (Python memoryview slice assignment)
        # Создаем numpy обертку над буфером разделяемой памяти
        dst_arr = np.ndarray(frame.shape, dtype=frame.dtype, buffer=shm_buffer)
        dst_arr[:] = frame  # Копирование содержимого

        return True

    def set_exposure(self, value: int) -> bool:
        """
        Управляет выдержкой через вызов внешней утилиты uvc-util.
        """
        if not os.path.exists(self._uvc_util_path):
            logger.warning(f"UVC util not found at {self._uvc_util_path}. Exposure update skipped.")
            return False

        try:
            # Формируем команду: uvc-util -I <id> -s exposure-time-abs=<value>
            # Обрати внимание: self._id это int, uvc-util ждет строку
            cmd = [
                self._uvc_util_path,
                "-I", str(self._id),
                "-s", f"{self._exposure_param}={value}"
            ]

            # Запускаем без вывода в консоль (stdout=DEVNULL)
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Cam {self._id}: Exposure set to {value} (UVC)")
            return True

        except subprocess.CalledProcessError:
            logger.error(f"Cam {self._id}: Failed to set exposure (UVC utility error). Check device connection.")
            return False
        except Exception as e:
            logger.error(f"Cam {self._id}: Unexpected error setting exposure: {e}")
            return False