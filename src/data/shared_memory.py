import struct
import time
import numpy as np
from multiprocessing import shared_memory
from typing import Tuple, Optional
from loguru import logger

# Импортируем модели
from src.data.models import SharedMemoryConfig
# [FIX] Импортируем глобальные настройки
from src.core.config import settings


class VideoFrameLayout:
    """
    Управляет форматом ОДНОГО слота кадра (Secure Protocol v2.1).
    Structure:
    [ Header (24 bytes) | Pixels (...) ]

    Header Format ('qdfBH'):
      - q: frame_id   (int64, 8 bytes)
      - d: timestamp  (double, 8 bytes)
      - f: math_salt  (float, 4 bytes)
      - B: flags      (uint8, 1 byte)
      - H: reserved   (uint16, 2 bytes)
    """
    _HEADER_FORMAT = 'qdfBH'
    HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)

    @classmethod
    def get_slot_size(cls, shape: Tuple[int, ...], dtype='uint8') -> int:
        pixel_bytes = np.prod(shape) * np.dtype(dtype).itemsize
        return cls.HEADER_SIZE + int(pixel_bytes)

    @classmethod
    def write_to_buf(cls, buffer_view: memoryview,
                     frame: np.ndarray,
                     frame_id: int,
                     timestamp: float,
                     math_salt: float = 1.0,
                     flags: int = 0):
        """
        Записывает кадр и метаданные безопасности.
        """
        # 1. Пишем заголовок
        struct.pack_into(cls._HEADER_FORMAT, buffer_view, 0,
                         frame_id, timestamp, math_salt, flags, 0)

        # 2. Пишем пиксели
        body_view = buffer_view[cls.HEADER_SIZE:]
        dst_arr = np.ndarray(frame.shape, dtype=frame.dtype, buffer=body_view)
        dst_arr[:] = frame[:]

    @classmethod
    def parse_from_buf(cls, buffer_view: memoryview, shape: Tuple[int, ...], dtype='uint8'):
        """
        Читает кадр и возвращает расширенный кортеж данных.
        """
        frame_id, ts, salt, flags, _ = struct.unpack_from(cls._HEADER_FORMAT, buffer_view, 0)
        image_view = np.ndarray(shape, dtype=dtype, buffer=buffer_view[cls.HEADER_SIZE:])

        return frame_id, ts, salt, flags, image_view


class RingBufferLayout:
    """
    Управляет заголовком ВСЕГО кольца.
    Structure: [ WriteIndex (4b) | Capacity (4b) | ... Slots ... ]
    """
    _GLOBAL_HEADER_FMT = 'II'
    GLOBAL_HEADER_SIZE = struct.calcsize(_GLOBAL_HEADER_FMT)

    @classmethod
    def calc_total_size(cls, shape: Tuple[int, ...], dtype='uint8', capacity: int = 3) -> int:
        slot_size = VideoFrameLayout.get_slot_size(shape, dtype)
        return cls.GLOBAL_HEADER_SIZE + (slot_size * capacity)

    @classmethod
    def init_header(cls, shm_buf: memoryview, capacity: int):
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, 0, capacity)

    @classmethod
    def get_write_index(cls, shm_buf: memoryview) -> int:
        idx, _ = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        return idx

    @classmethod
    def update_write_index(cls, shm_buf: memoryview, new_index: int):
        _, cap = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, new_index, cap)

    @classmethod
    def get_slot_view(cls, shm_buf: memoryview, slot_index: int, slot_size: int) -> memoryview:
        offset = cls.GLOBAL_HEADER_SIZE + (slot_index * slot_size)
        return shm_buf[offset: offset + slot_size]


class SharedMemoryManager:
    def __init__(
            self,
            config: SharedMemoryConfig,
            create: bool = True
    ):
        self.name = config.name
        self.shape = config.shape
        self.dtype = config.dtype

        # [FIX] Берем значение из глобального конфига, а не из объекта модели
        self.capacity = settings.SHM_BUFFER_COUNT

        self.is_owner = create

        # Рассчитываем размер на основе 6 слотов (или сколько в конфиге)
        self.size = RingBufferLayout.calc_total_size(self.shape, self.dtype, self.capacity)
        self.shm: Optional[shared_memory.SharedMemory] = None
        self.slot_size = VideoFrameLayout.get_slot_size(self.shape, self.dtype)

        if self.is_owner:
            self._allocate()
        else:
            self._attach()

    def _allocate(self):
        # Очистка мусора
        try:
            temp = shared_memory.SharedMemory(name=self.name)
            temp.unlink()
            temp.close()
        except FileNotFoundError:
            pass

        try:
            self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=self.size)
            RingBufferLayout.init_header(self.shm.buf, self.capacity)
            logger.info(f"💾 SecureSHM Created: {self.name} | {self.size / 1024 / 1024:.2f} MB | {self.capacity} slots")
        except Exception as e:
            logger.critical(f"Failed to create SHM {self.name}: {e}")
            raise

    def _attach(self):
        try:
            self.shm = shared_memory.SharedMemory(name=self.name, create=False)
            _, real_cap = struct.unpack_from(RingBufferLayout._GLOBAL_HEADER_FMT, self.shm.buf, 0)
            self.capacity = real_cap
        except FileNotFoundError:
            logger.error(f"❌ SHM {self.name} not found.")
            raise

    def close(self):
        if self.shm:
            try:
                self.shm.close()
            except:
                pass
            if self.is_owner:
                try:
                    self.shm.unlink()
                    logger.info(f"🗑️ SHM Unlinked: {self.name}")
                except:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()