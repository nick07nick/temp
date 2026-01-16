import struct
import time
import numpy as np
from multiprocessing import shared_memory
from typing import Tuple, Optional, Any
from loguru import logger

# Импортируем модели и настройки
from src.data.models import SharedMemoryConfig
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
        Записывает кадр и метаданные безопасности в буфер.
        """
        # 1. Пишем заголовок
        struct.pack_into(cls._HEADER_FORMAT, buffer_view, 0,
                         frame_id, timestamp, math_salt, flags, 0)

        # 2. Пишем пиксели
        # Вычисляем смещение для тела кадра
        body_view = buffer_view[cls.HEADER_SIZE:]
        # Создаем numpy array поверх shared memory
        dst_arr = np.ndarray(frame.shape, dtype=frame.dtype, buffer=body_view)
        # Копируем данные (Zero-Copy запись в память)
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
    Управляет заголовком ВСЕГО кольца (Global Header).
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
        """Инициализация глобального заголовка при создании памяти"""
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, 0, capacity)

    @classmethod
    def get_write_index(cls, shm_buf: memoryview) -> int:
        """Получить индекс последнего записанного слота"""
        idx, _ = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        return idx

    @classmethod
    def get_capacity(cls, shm_buf: memoryview) -> int:
        """Получить емкость буфера"""
        _, cap = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        return cap

    @classmethod
    def update_write_index(cls, shm_buf: memoryview, new_index: int):
        """Обновить индекс записи"""
        _, cap = struct.unpack_from(cls._GLOBAL_HEADER_FMT, shm_buf, 0)
        struct.pack_into(cls._GLOBAL_HEADER_FMT, shm_buf, 0, new_index, cap)

    @classmethod
    def get_slot_view(cls, shm_buf: memoryview, slot_index: int, slot_size: int) -> memoryview:
        """Получить memoryview конкретного слота"""
        offset = cls.GLOBAL_HEADER_SIZE + (slot_index * slot_size)
        return shm_buf[offset: offset + slot_size]


class SharedMemoryManager:
    """
    Менеджер разделяемой памяти (RAII Wrapper).
    Отвечает за создание, подключение и очистку ресурсов.
    """

    def __init__(
            self,
            config: SharedMemoryConfig,
            create: bool = True
    ):
        self.name = config.name
        self.shape = config.shape
        self.dtype = config.dtype

        # Берем capacity из настроек, если это создание, иначе прочитаем из памяти
        self.capacity = settings.SHM_BUFFER_COUNT
        self.is_owner = create

        self.slot_size = VideoFrameLayout.get_slot_size(self.shape, self.dtype)

        # Рассчитываем общий размер
        self.size = RingBufferLayout.calc_total_size(self.shape, self.dtype, self.capacity)

        self.shm: Optional[shared_memory.SharedMemory] = None

        # Ссылки на форматы для рекордера (чтобы не дублировать)
        self.HEADER_FORMAT = VideoFrameLayout._HEADER_FORMAT
        # Для точек пока используем простой формат (в будущем Protobuf)
        self.POINT_FORMAT = 'idd'  # int id, double x, double y

        if self.is_owner:
            self._allocate()
        else:
            self._attach()

    def _allocate(self):
        # 1. Попытка очистки мусора от старых запусков
        try:
            temp = shared_memory.SharedMemory(name=self.name)
            temp.unlink()
            temp.close()
            logger.warning(f"🧹 Cleaned up stale SHM: {self.name}")
        except FileNotFoundError:
            pass

        # 2. Создание новой памяти
        try:
            self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=self.size)
            # Инициализируем заголовок (index=0, capacity=settings)
            RingBufferLayout.init_header(self.shm.buf, self.capacity)
            logger.info(f"💾 SecureSHM Created: {self.name} | {self.size / 1024 / 1024:.2f} MB | {self.capacity} slots")
        except Exception as e:
            logger.critical(f"Failed to create SHM {self.name}: {e}")
            raise

    def _attach(self):
        try:
            self.shm = shared_memory.SharedMemory(name=self.name, create=False)
            # Читаем реальную емкость из заголовка
            self.capacity = RingBufferLayout.get_capacity(self.shm.buf)
            # Пересчитываем размер слота (на случай если конфиг отличается)
            # (В продакшене тут нужна проверка версий)
            logger.debug(f"🔗 Attached to SHM: {self.name}")
        except FileNotFoundError:
            logger.error(f"❌ SHM {self.name} not found.")
            raise

    def read_frame(self) -> Optional[Tuple[int, float, list]]:
        """
        Метод для чтения последнего кадра (для Recorder/UI).
        Возвращает (frame_id, timestamp, dummy_points_placeholder).
        В будущем здесь будет чтение реальных точек.
        """
        if not self.shm: return None

        try:
            head_idx = RingBufferLayout.get_write_index(self.shm.buf)
            slot_view = RingBufferLayout.get_slot_view(self.shm.buf, head_idx, self.slot_size)

            # Парсим заголовок и картинку (картинка нам тут не нужна, только метаданные для теста)
            fid, ts, salt, flags, img = VideoFrameLayout.parse_from_buf(slot_view, self.shape, self.dtype)

            # TODO: Чтение точек пока заглушено, возвращаем пустой список
            # В реальной системе точки лежат в EventBus или отдельной SHM области
            return fid, ts, []

        except Exception as e:
            logger.warning(f"Read error: {e}")
            return None

    def close(self):
        """Корректное закрытие ресурсов"""
        if self.shm:
            try:
                self.shm.close()
            except Exception as e:
                logger.warning(f"Error closing SHM handle: {e}")

            if self.is_owner:
                try:
                    self.shm.unlink()
                    logger.info(f"🗑️ SHM Unlinked: {self.name}")
                except FileNotFoundError:
                    pass  # Уже удалена
                except Exception as e:
                    logger.error(f"Error unlinking SHM: {e}")

            self.shm = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()