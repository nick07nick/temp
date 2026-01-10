# src/data/schemas.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import time
from enum import Enum  # [NEW]

# --- 0. UI Enums (Для стандартизации) [NEW] ---
class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

class WidgetType(str, Enum):
    TEXT = "text"
    CHART_LINE = "chart_line"
    CHART_BAR = "chart_bar"
    STATUS_INDICATOR = "status_indicator"

# --- 1. Ошибки и Статус ---

class ModuleError(BaseModel):
    source: str = Field(..., description="Имя модуля/плагина, где упало")
    message: str = Field(..., description="Текст ошибки")
    timestamp: float = Field(default_factory=time.perf_counter, description="Время возникновения")
    severity: str = Field("error", description="info, warning, error, critical")

class PluginStatus(BaseModel):
    id: str
    is_active: bool
    performance_ms: float = Field(0.0, description="Время обработки последнего кадра (мс)")

# --- [NEW] UI Models (Плагины шлют это на фронт) ---

class UINotification(BaseModel):
    id: str
    title: str
    message: str
    type: NotificationType = NotificationType.INFO
    duration: float = 3.0

class UIWidgetUpdate(BaseModel):
    widget_id: str
    type: WidgetType
    title: str
    data: Any  # {"value": 12.5} или {"x": [...], "y": [...]}

# --- 2. Конфигурация Камеры ---
# (Тут без изменений, просто для контекста)
class CameraConfig(BaseModel):
    """
        Полная конфигурация камеры и алгоритмов обработки.
        Передается в Processor с каждым кадром.
        """
    # Hardware (UVC)
    camera_id: Optional[int] = None
    exposure: Optional[int] = Field(None, ge=1, le=10000)
    gain: Optional[int] = Field(None, ge=0)
    auto_exposure: Optional[bool] = Field(None, description="Вкл/Выкл автоэкспозиции")
    auto_focus: Optional[bool] = Field(None)
    focus: Optional[int] = Field(None)
    white_balance: Optional[int] = Field(None)

    # Software (CV Algorithms)
    threshold: Optional[int] = Field(None, ge=0, le=255, description="Порог бинаризации")
    min_area: int = 15  # Blob Filter
    max_blobs: int = 50  # Noise Protection
    calib_threshold: int = Field(0, ge=0, le=255)

    # Global Flags
    is_calibration_mode: bool = Field(False, description="Включить поиск ChArUco доски")
    calibration_cmd: Optional[str] = None  # "CAPTURE", "CALCULATE" или None
    enable_undistort: bool = True

    class Config:
        extra = "ignore"

# --- 3. Команды ---
class PluginCommand(BaseModel):
    target: str = Field(..., description="ID получателя")
    cmd: str = Field(..., description="Имя команды")
    args: Dict[str, Any] = Field(default_factory=dict, description="Параметры")

# --- 4. Состояние Системы ---

class SystemState(BaseModel):
    frame_id: int
    fps: float
    errors: List[ModuleError] = Field(default_factory=list)
    active_plugins: List[PluginStatus] = Field(default_factory=list)
    camera_config: Optional[CameraConfig] = None

    # [NEW] Каналы связи с интерфейсом
    notifications: List[UINotification] = Field(default_factory=list)
    widgets: List[UIWidgetUpdate] = Field(default_factory=list)