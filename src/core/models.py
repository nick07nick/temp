# src/core/models.py
import time
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field
import numpy as np

# === 1. Базовые примитивы ===

class Point2D(BaseModel):
    """
    Точка на изображении.
    id: Уникальный идентификатор (например, 0, 1, 2...).
        Важно для трекинга: ID должен сохраняться между кадрами.
    """
    x: float
    y: float
    confidence: float = 1.0
    id: Optional[int] = None
    label: Optional[str] = None
    is_predicted: bool = False
# === 2. Конфигурации ===

class SharedMemoryConfig(BaseModel):
    """
    Единая конфигурация памяти.
    """
    name: str
    size: int
    shape: Tuple[int, int, int] = (0, 0, 0)
    dtype: str = "uint8"
    width: int = 0
    height: int = 0
    enable_video_stream: bool = False

class CameraIntrinsics(BaseModel):
    name: str
    camera_id: int
    camera_matrix: List[List[float]]
    dist_coeffs: List[float]

    def get_matrix_np(self) -> np.ndarray:
        return np.array(self.camera_matrix, dtype=np.float64)

    def get_dist_np(self) -> np.ndarray:
        return np.array(self.dist_coeffs, dtype=np.float64)

class WorkspaceProfile(BaseModel):
    name: str
    camera_mapping: Dict[int, str]
    scale_factor: float = 1.0
    distance_to_subject_mm: Optional[float] = None

# === 3. События и Пакеты данных ===

class FrameMetadata(BaseModel):
    frame_id: int
    timestamp: float = Field(default_factory=time.time)
    camera_id: int
    valid: bool = True

class SyncEvent(BaseModel):
    camera_id: int
    frame_idx: int
    timestamp: float

class FrameData(BaseModel):
    """
    Пакет данных, который улетает в EventBus -> WebSocket.
    """
    camera_index: int
    frame_id: int
    timestamp: float
    points: List[Point2D]
    calibrated: bool = False
    mode: str = "IDLE" # TRACK / DETECT