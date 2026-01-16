# src/core/security.py
import logging
from src.core import ICryptoProvider

logger = logging.getLogger("BikeFit.Security")

class DevCryptoProvider(ICryptoProvider):
    """
    DEVELOPMENT ONLY.
    Заглушка криптопровайдера. Эмулирует поведение USB-ключа.
    В продакшене будет заменена на SentinelCryptoProvider.
    """

    def __init__(self, simulation_mode: bool = True):
        self._is_active = simulation_mode
        if simulation_mode:
            logger.warning("!!! RUNNING WITH DEV CRYPTO PROVIDER. NOT SECURE !!!")

    def initialize(self) -> None:
        logger.info("DevCryptoProvider initialized.")

    def verify_license(self) -> bool:
        return self._is_active

    def get_math_salt(self) -> float:
        # В реальном ключе это значение вычисляется внутри MCU ключа
        return 1.0 if self._is_active else 0.0001  # 0.0001 сломает триангуляцию

    def sign_data(self, data: bytes) -> bytes:
        # Эмуляция подписи (просто XOR для теста)
        return bytes([b ^ 0x42 for b in data])

class SecurityContext:
    """Контейнер для проброса зависимостей безопасности."""
    def __init__(self, provider: ICryptoProvider):
        self.provider = provider

    def validate_environment(self) -> None:
        if not self.provider.verify_license():
            raise PermissionError("License verification failed. System halted.")