# src/core/shared_memory.py
import logging
from multiprocessing.shared_memory import SharedMemory
from typing import Optional, Tuple
import numpy as np
from src.core.models import SharedMemoryConfig

logger = logging.getLogger("BikeFit.Memory")


class SharedMemoryManager:
    """
    RAII обертка над SharedMemory.
    Гарантирует очистку памяти (/dev/shm) даже при краше процесса.
    """

    def __init__(self, config: SharedMemoryConfig, create: bool = False):
        self.config = config
        self._shm: Optional[SharedMemory] = None
        self._create = create
        self.buffer: Optional[memoryview] = None

    def __enter__(self):
        try:
            if self._create:
                # Создаем новую память
                self._shm = SharedMemory(name=self.config.name, create=True, size=self.config.size)
                logger.debug(f"Allocated SharedMemory: {self.config.name} ({self.config.size} bytes)")
            else:
                # Подключаемся к существующей
                self._shm = SharedMemory(name=self.config.name)
                logger.debug(f"Attached to SharedMemory: {self.config.name}")

            self.buffer = self._shm.buf
            return self
        except FileExistsError:
            # Если память осталась от прошлого запуска - переподключаемся и чистим
            shm = SharedMemory(name=self.config.name)
            shm.unlink()
            logger.warning(f"Cleaned up stale SharedMemory: {self.config.name}")
            return self.__enter__()
        except Exception as e:
            logger.error(f"SharedMemory error: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._shm:
            self._shm.close()
            if self._create:
                self._shm.unlink()  # Важно! Удаляет файл из /dev/shm
                logger.debug(f"Unlinked SharedMemory: {self.config.name}")

    def get_numpy_array(self) -> np.ndarray:
        """Создает numpy wrapper над буфером без копирования."""
        if self._shm is None:
            raise RuntimeError("SharedMemory is not initialized")

        return np.ndarray(
            (self.config.height, self.config.width, self.config.channels),
            dtype=self.config.dtype,
            buffer=self._shm.buf
        )