# src/core/config.py
import sys
from pathlib import Path
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# === 1. ГЛОБАЛЬНЫЕ ПУТИ (Static constants) ===
# Вычисляем корень проекта.
# __file__ = src/core/config.py -> parent=core -> parent=src -> parent=BikeFit
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# === 2. ПОИСК UVC-UTIL (Infrastructure) ===
# Это не совсем настройка, это проверка окружения. Делаем её до загрузки конфига.
_local_uvc = ROOT_DIR / "uvc-util" / "src" / "uvc-util"
if not _local_uvc.exists():
    _local_uvc = ROOT_DIR / "uvc-util" / "uvc-util"

UVC_BIN_PATH = _local_uvc


# === 3. КЛАСС КОНФИГУРАЦИИ (Domain Logic) ===
class SystemSettings(BaseSettings):
    """
    Единый источник правды о настройках системы.
    Читает переменные из .env, если они там есть.
    """

    # --- Debug & Logs ---
    DEBUG_MODE: bool = Field(default=True, description="Включить подробный вывод логов")

    # --- Camera Settings ---
    CAMERA_WIDTH: int = Field(default=1920)
    CAMERA_HEIGHT: int = Field(default=1200)  # Твои 16:10
    CAMERA_FPS: int = Field(default=90)
    CAMERA_INDEX: int = Field(default=0)

    # --- Shared Memory ---
    SHM_BUFFER_COUNT: int = 10
    SHM_CAMERA_BUFFER_NAME: str = "camera_0_buffer"

    # --- Network ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Настройки Pydantic (откуда читать .env)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Игнорировать лишние переменные в .env
    )

    @property
    def frame_size_bytes(self) -> int:
        """Расчет размера одного кадра в байтах (width * height * 3 канала)"""
        return self.CAMERA_WIDTH * self.CAMERA_HEIGHT * 3

    SHARED_MEMORY_SIZE: int = 500_000_000


class Config:
    env_file = ".env"


CORE_PIPELINE = [
    # 1. Сначала ищем пятна (Detection)
    "src.stages.detection.BlobDetectionStage",
    # 2. Потом присваиваем ID (Tracking)
    "src.stages.tracking.CentroidTrackerStage",
    # 3. Корректировка искажений
    "src.stages.undistort.UndistortStage",
    "src.stages.perspective.PerspectiveStage",
    # 3. (В будущем) Фильтрация и реконструкция
    # "src.stages.filtering.KalmanFilterStage",
]
# === 4. ИНИЦИАЛИЗАЦИЯ ===
# Создаем единственный экземпляр настроек
settings = SystemSettings()

# === 5. НАСТРОЙКА ЛОГГЕРА ===
# Логгер настраивается ПОСЛЕ загрузки settings, так как ему нужно знать DEBUG_MODE
logger.remove()

_log_fmt = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# Уровень логирования зависит от конфига
_console_level = "DEBUG" if settings.DEBUG_MODE else "INFO"

logger.add(sys.stderr, format=_log_fmt, level=_console_level)
logger.add(
    LOG_DIR / "bikefit_{time}.log",
    rotation="10 MB",
    retention="5 days",
    level="DEBUG",  # В файл пишем всё, даже если в консоли тихо
    format=_log_fmt
)

# Экспортируем log для удобства импорта (from config import log)
log = logger
# === PIPELINE CONFIGURATION ===
# Строгий порядок выполнения стадий ядра

# Проверка окружения при старте
if not UVC_BIN_PATH.exists():
    log.warning(f"⚠️ UVC Utility не найдена по пути: {UVC_BIN_PATH}. Управление камерой будет ограничено.")
else:
    log.debug(f"⚙️ Config loaded. UVC util found: {UVC_BIN_PATH}")




