# src/hardware/webcam.py
import cv2
import numpy as np
import subprocess
import struct
import time
from typing import Optional, Tuple
from multiprocessing import shared_memory

# Импортируем новые Layout-ы
from src.core.shared_memory import VideoFrameLayout, RingBufferLayout

# Импорт настроек и логгера
from src.core.config import settings, log, UVC_BIN_PATH


class Webcam:
    def __init__(
            self,
            device_id: int = settings.CAMERA_INDEX,
            width: int = settings.CAMERA_WIDTH,
            height: int = settings.CAMERA_HEIGHT,
            fps: int = settings.CAMERA_FPS,
            shm_name: Optional[str] = None
    ):
        """
        Драйвер камеры с поддержкой Ring Buffer.
        """
        self._id = device_id
        self._target_width = width
        self._target_height = height
        self._target_fps = fps
        self._shm_name = shm_name

        self._cap: Optional[cv2.VideoCapture] = None
        self._is_connected = False

        self._shm: Optional[shared_memory.SharedMemory] = None

    def connect(self) -> bool:
        """Явное открытие соединения с камерой."""
        log.info(f"🔌 Connecting to Camera #{self._id}...")

        # 1. Открытие потока
        self._cap = cv2.VideoCapture(self._id)
        if not self._cap.isOpened():
            log.critical(f"❌ Failed to open camera index {self._id}")
            self._is_connected = False
            return False

        # 2. Настройка MJPG
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_height)
        self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # 3. Проверка
        real_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        real_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        real_fps = self._cap.get(cv2.CAP_PROP_FPS)

        log.info(f"✅ Camera #{self._id} started: {real_w}x{real_h} @ {real_fps:.1f} FPS")

        # 4. Подключение к общей памяти
        if self._shm_name:
            try:
                self._shm = shared_memory.SharedMemory(name=self._shm_name)
                log.debug(f"🔗 Attached to SharedMemory: {self._shm_name}")
            except FileNotFoundError:
                log.error(f"❌ SharedMemory '{self._shm_name}' not found.")
                self._shm = None

        self._is_connected = True
        return True

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Обычное чтение (для локальной обработки без SHM)."""
        if not self._is_connected or self._cap is None:
            return False, None
        return self._cap.read()

    def capture_to_shm(self, frame_id: int) -> bool:
        """
        Читает кадр и пишет его в СЛЕДУЮЩИЙ слот кольцевого буфера.
        """
        if not self._is_connected or self._cap is None: return False

        # 1. Читаем физический кадр
        ret, frame = self._cap.read()
        if not ret: return False

        # Если SHM нет, просто возвращаем True (работаем локально)
        if self._shm is None: return True

        try:
            # --- RING BUFFER LOGIC ---

            # 2. Читаем заголовок кольца: (current_index, capacity)
            # Формат 'II' = 2 unsigned int
            current_idx, capacity = struct.unpack_from(RingBufferLayout._GLOBAL_HEADER_FMT, self._shm.buf, 0)

            # 3. Вычисляем индекс следующего слота
            next_idx = (current_idx + 1) % capacity

            # 4. Рассчитываем размер слота (Header + Pixels)
            # Берем shape из реального кадра для надежности
            slot_size = VideoFrameLayout.get_slot_size(frame.shape, frame.dtype.name)

            # Проверка выхода за границы (на всякий случай)
            required_offset = RingBufferLayout.GLOBAL_HEADER_SIZE + (next_idx * slot_size) + slot_size
            if required_offset > self._shm.size:
                log.error(f"❌ SHM overflow! Need offset {required_offset}, have {self._shm.size}")
                return False

            # 5. Получаем "окно" (view) для записи конкретно в этот слот
            slot_view = RingBufferLayout.get_slot_view(self._shm.buf, next_idx, slot_size)

            # 6. Пишем кадр (Zero-Copy) внутрь этого слота
            VideoFrameLayout.write_to_buf(slot_view, frame, frame_id)

            # 7. Фиксируем изменение: обновляем индекс в глобальном заголовке
            # Теперь читатели увидят, что head переместился на next_idx
            RingBufferLayout.update_write_index(self._shm.buf, next_idx)

            return True

        except Exception as e:
            log.error(f"❌ Write error: {e}")
            return False

    def release(self):
        self._is_connected = False
        if self._cap:
            self._cap.release()
        if self._shm:
            self._shm.close()
            self._shm = None
        log.info(f"Camera #{self._id} released.")

    # ==========================================
    # UVC CONTROL SECTION
    # ==========================================
    # (Без изменений, оставляем методы настройки камеры)

    def _set_uvc_param(self, control: str, value: str) -> bool:
        if not UVC_BIN_PATH.exists():
            return False
        cmd = [str(UVC_BIN_PATH), "-I", str(self._id), "-s", control, str(value)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            return res.returncode == 0
        except Exception:
            return False

    def set_exposure(self, value: int) -> bool:
        self._set_uvc_param("auto-exposure-mode", "1")
        return self._set_uvc_param("exposure-time-abs", str(value))

    def set_auto_exposure(self) -> bool:
        return self._set_uvc_param("auto-exposure-mode", "8")

    def set_gain(self, value: int) -> bool:
        return self._set_uvc_param("gain", str(value))

    def set_focus(self, value: int) -> bool:
        self._set_uvc_param("auto-focus", "0")
        return self._set_uvc_param("focus-abs", str(value))

    def set_auto_focus(self) -> bool:
        return self._set_uvc_param("auto-focus", "1")