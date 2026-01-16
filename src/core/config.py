# src/core/config.py
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Literal
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, BaseModel

# === 1. ГЛОБАЛЬНЫЕ ПУТИ ===
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR = ROOT_DIR / "data"
CONFIG_FILE = ROOT_DIR / "bikefit_db.json"  # <-- JSON Профиль

LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# === 2. ПОИСК UVC-UTIL ===
_local_uvc = ROOT_DIR / "uvc-util" / "src" / "uvc-util"
if not _local_uvc.exists():
    _local_uvc = ROOT_DIR / "uvc-util" / "uvc-util"
UVC_BIN_PATH = _local_uvc


# === 3. МОДЕЛИ ПРОФИЛЯ (JSON Structure) ===
class CameraProfile(BaseModel):
    """Описание конкретной камеры в JSON"""
    role_id: int  # 0, 1, 2... (как передает Orchestrator)
    role_name: str  # "side", "front"
    serial_number: str  # "0x01120000" или SN
    resolution: List[int] = [1920, 1200]
    calibration_file: str  # "calibration_side.json"
    enabled: bool = True


class SystemProfile(BaseModel):
    """Корневой объект bikefit_db.json"""
    math_salt_interval: float = 10.0
    security_level: str = "high"
    # Ключ словаря = role_name (для удобства доступа), но внутри есть role_id
    cameras: Dict[str, CameraProfile] = {}


# === 4. КЛАСС КОНФИГУРАЦИИ (Runtime Settings) ===
class SystemSettings(BaseSettings):
    """
    Гибридная конфигурация:
    - Инфраструктура (IP, Ports, Memory) -> из .env или дефолты
    - Бизнес-логика (Камеры, Калибровки) -> из bikefit_db.json
    """

    # --- Debug & Logs ---
    DEBUG_MODE: bool = Field(default=True, description="Включить подробный вывод логов")

    # --- System State (Loaded from JSON) ---
    PROFILE: SystemProfile = Field(default_factory=SystemProfile)

    # --- Global Defaults (Fallback) ---
    CAMERA_WIDTH: int = 1920
    CAMERA_HEIGHT: int = 1200
    CAMERA_FPS: int = 90

    # --- Shared Memory ---
    SHM_BUFFER_COUNT: int = 10
    SHARED_MEMORY_SIZE: int = 500_000_000

    # --- Network ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def load_profile(self):
        """Загрузка конфигурации оборудования из JSON"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.PROFILE = SystemProfile(**data)
                    logger.info(f"✅ Loaded Profile: {len(self.PROFILE.cameras)} cameras.")
            except Exception as e:
                logger.error(f"❌ Failed to load bikefit_db.json: {e}")
        else:
            logger.warning(f"⚠️ {CONFIG_FILE} not found. Using empty profile.")

    def get_calibration_path(self, filename: str) -> Path:
        return DATA_DIR / filename


# === 5. ПАЙПЛАЙН ===
CORE_PIPELINE = [
    "src.stages.detection.BlobDetectionStage",
    "src.stages.tracking.CentroidTrackerStage",
    "src.stages.undistort.UndistortStage",
    "src.stages.perspective.PerspectiveStage",
]

# === 6. ИНИЦИАЛИЗАЦИЯ ===
settings = SystemSettings()
settings.load_profile()  # Грузим JSON при старте

# === 7. НАСТРОЙКА ЛОГГЕРА ===
logger.remove()
_log_fmt = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
_console_level = "DEBUG" if settings.DEBUG_MODE else "INFO"
logger.add(sys.stderr, format=_log_fmt, level=_console_level)
logger.add(LOG_DIR / "bikefit_{time}.log", rotation="10 MB", retention="5 days", level="DEBUG", format=_log_fmt)

log = logger