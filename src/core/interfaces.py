# src/core/interfaces.py
from abc import ABC, abstractmethod
from typing import Tuple


class ICamera(ABC):
    """
    Абстрактный интерфейс камеры.
    Любая реализация (Webcam, Mock, RealSense) должна наследовать этот класс.
    """

    @abstractmethod
    def connect(self) -> None:
        """Инициализация соединения с устройством."""
        pass

    @abstractmethod
    def release(self) -> None:
        """Освобождение ресурсов."""
        pass

    @abstractmethod
    def get_resolution(self) -> Tuple[int, int]:
        """Возвращает (width, height)."""
        pass

    @abstractmethod
    def capture_to_buffer(self, shm_buffer: memoryview) -> bool:
        """
        Записывает кадр в переданный буфер памяти.
        Возвращает True, если кадр успешно записан.
        """
        pass

    @abstractmethod
    def set_exposure(self, value: int) -> bool:
        """
        Устанавливает абсолютное время выдержки (Exposure Time Absolute).
        :param value: Значение выдержки (зависит от камеры, например 10-5000)
        :return: True если успешно
        """
        pass


class ICryptoProvider(ABC):
    """
    Интерфейс для работы с ключом защиты (Dongle).
    """

    @abstractmethod
    def verify_license(self) -> bool:
        pass

    @abstractmethod
    def get_math_salt(self) -> float:
        """Возвращает коэффициент для формул (Poisoned Math)."""
        pass