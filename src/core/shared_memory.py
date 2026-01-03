# src/core/shared_memory.py
import struct
import time
import numpy as np
from multiprocessing import shared_memory
from typing import Tuple, Optional, Union
from loguru import logger
from src.core.models import SharedMemoryConfig


class VideoFrameLayout:
    """
    Управляет форматом ОДНОГО слота кадра.
    [ FrameHeader (16b) | Pixels (...) ]
    """
    _HEADER_FORMAT = 'qd'  # frame_id (int64), timestamp (double)
    HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)

    @classmethod
    def get_slot_size(cls, shape: Tuple[int, ...], dtype='uint8') -> int:
        """Размер одного слота в байтах (Заголовок + Пиксели)"""
        pixel_bytes = np.prod(shape) * np.dtype(dtype).itemsize
        return cls.HEADER_SIZE + int(pixel_bytes)

    @classmethod
    def write_to_buf(cls, buffer_view: memoryview, frame: np.ndarray, frame_id: int):
        """Пишет кадр в переданный буфер (view)"""
        struct.pack_into(cls._HEADER_FORMAT, buffer_view, 0, frame_id, time.time())
        # Пишем тело кадра со смещением заголовка
        body_view = buffer_view[cls.HEADER_SIZE:]
        dst_arr = np.ndarray(frame.shape, dtype=frame.dtype, buffer=body_view)
        dst_arr[:] = frame[:]

    @classmethod
    def parse_from_buf(cls, buffer_view: memoryview, shape: Tuple[int, ...], dtype='uint8'):
        """Читает кадр из переданного буфера"""
        frame_id, timestamp = struct.unpack_from(cls._HEADER_FORMAT, buffer_view, 0)
        image_view = np.ndarray(shape, dtype=dtype, buffer=buffer_view[cls.HEADER_SIZE:])
        return frame_id, timestamp, image_view


class RingBufferLayout:
    """
    Управляет структурой ВСЕГО кольцевого буфера.
    [ GlobalHeader (8b) | Slot 0 | Slot 1 | ... | Slot N-1 ]
    """
    # I = unsigned int (4 bytes). Храним: [write_index, capacity]
    _GLOBAL_HEADER_FMT = 'II'
    GLOBAL_HEADER_SIZE = struct.calcsize(_GLOBAL_HEADER_FMT)

    @classmethod
    def calc_total_shm_size(cls, shape: Tuple[int, ...], dtype='uint8', capacity: int = 3) -> int:
        slot_size = VideoFrameLayout.get_slot_size(shape, dtype)
        return cls.GLOBAL_HEADER_SIZE + (slot_size * capacity)

    @classmethod
    def init_header(cls, shm_buf: memoryview, capacity: int):
        """Сбрасывает индекс записи и устанавливает емкость"""
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, 0, capacity)

    @classmethod
    def get_write_index(cls, shm_buf: memoryview) -> int:
        """Возвращает текущий индекс, куда писал последний раз Writer"""
        idx, _ = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        return idx

    @classmethod
    def update_write_index(cls, shm_buf: memoryview, new_index: int):
        """Обновляет индекс (атомарно, насколько позволяет struct)"""
        # Считываем capacity, чтобы не затереть
        _, cap = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, new_index, cap)

    @classmethod
    def get_slot_view(cls, shm_buf: memoryview, slot_index: int, slot_size: int) -> memoryview:
        """Возвращает slice памяти, соответствующий конкретному слоту"""
        offset = cls.GLOBAL_HEADER_SIZE + (slot_index * slot_size)
        return shm_buf[offset: offset + slot_size]


class SharedMemoryManager:
    def __init__(
            self,
            name: Union[str, SharedMemoryConfig],
            shape: Optional[Tuple[int, int, int]] = None,
            dtype: str = "uint8",
            capacity: int = 3,  # <--- Теперь по умолчанию 3 буфера
            create: bool = True
    ):
        self.capacity = capacity

        if isinstance(name, SharedMemoryConfig):
            self.name = name.name
            self.shape = name.shape
            self.dtype = name.dtype
            # Если конфиг пришел извне, берем размер из конфига, но пересчитывать логику будем по Layout
            self.size = name.size
        else:
            self.name = name
            self.shape = shape
            self.dtype = dtype
            self.size = RingBufferLayout.calc_total_shm_size(shape, dtype, capacity)

        self.shm: Optional[shared_memory.SharedMemory] = None
        self.slot_size = VideoFrameLayout.get_slot_size(self.shape, self.dtype)

        if create:
            self._allocate()
        else:
            self._attach()

    def _allocate(self):
        try:
            try:
                existing = shared_memory.SharedMemory(name=self.name)
                existing.close()
                existing.unlink()
            except FileNotFoundError:
                pass

            self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=self.size)
            # Инициализируем заголовок кольца (индекс 0)
            RingBufferLayout.init_header(self.shm.buf, self.capacity)
            logger.info(
                f"✅ Allocated Ring SHM '{self.name}' | Slots: {self.capacity} | Size: {self.size / 1024 / 1024:.2f} MB")
        except Exception as e:
            logger.critical(f"Failed to allocate SHM: {e}")
            raise

    def _attach(self):
        self.shm = shared_memory.SharedMemory(name=self.name, create=False)
        # При подключении вычитываем реальный capacity из заголовка, чтобы не рассинхронизироваться
        _, real_cap = struct.unpack_from(RingBufferLayout._GLOBAL_HEADER_FMT, self.shm.buf, 0)
        self.capacity = real_cap
        self.slot_size = VideoFrameLayout.get_slot_size(self.shape, self.dtype)

    def get_config(self) -> SharedMemoryConfig:
        h, w = self.shape[0], self.shape[1]
        return SharedMemoryConfig(
            name=self.name,
            size=self.size,
            shape=self.shape,
            dtype=self.dtype,
            width=w, height=h,
            enable_video_stream=True
        )  # Можно расширить модель, добавив поле capacity, но пока оставим совместимость

    def close(self):
        """
        Корректно освобождает ресурсы worker-процесса.
        Порядок критически важен!
        """
        # 1. Сначала удаляем view/массив, который ссылается на память
        if hasattr(self, 'buffer'):
            del self.buffer  # Удаляем NumPy array или memoryview
            self.buffer = None

        if hasattr(self, 'metadata_buffer'):
            del self.metadata_buffer
            self.metadata_buffer = None

        # 2. Теперь, когда ссылок нет, можно закрыть handle
        if hasattr(self, 'shm'):
            try:
                self.shm.close()
                print(f"🔒 SharedMemory closed for {self.shm.name}")
            except Exception as e:
                print(f"⚠️ Error closing SHM: {e}")

    def unlink(self):
        """Вызывается ТОЛЬКО из главного процесса один раз"""
        if hasattr(self, 'shm'):
            try:
                self.shm.unlink()
                print(f"🗑️ SharedMemory unlinked: {self.shm.name}")
            except FileNotFoundError:
                pass  # Уже удалена
    def __enter__(self):
        if not self.shm: self._attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()