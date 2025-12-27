# src/core/models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Tuple, List, Dict, Optional
import time
import numpy as np


class SharedMemoryConfig(BaseModel):
    name: str
    size: int
    width: int
    height: int
    channels: int = 3
    dtype: str = "uint8"
    model_config = ConfigDict(frozen=True)


class FrameMetadata(BaseModel):
    """
    Метаданные кадра.
    Передаются через Queue/Pipe, пока сам кадр лежит в SharedMemory.
    """
    frame_id: int
    timestamp: float = Field(default_factory=time.time)
    shm_name: str
    camera_id: int
    valid: bool = True

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode('utf-8')


class Point2D(BaseModel):
    x: float
    y: float
    confidence: float = 1.0


class CameraIntrinsics(BaseModel):
    """
    Физические параметры линзы (не меняются при перемещении велосипеда).
    """
    name: str  # Например: "Cam0_WideLens_1080p"
    camera_id: int
    camera_matrix: List[List[float]]
    dist_coeffs: List[float]

    def get_matrix_np(self) -> np.ndarray:
        return np.array(self.camera_matrix, dtype=np.float64)

    def get_dist_np(self) -> np.ndarray:
        return np.array(self.dist_coeffs, dtype=np.float64)


class WorkspaceProfile(BaseModel):
    """
    Пресет для конкретного рабочего места (Тренажера).
    Определяет, какую калибровку использовать для каждой камеры
    и дополнительные параметры сцены (например, масштаб).
    """
    name: str  # Например: "Trainer_PRO_Left_Corner"
    # Mapping: camera_id -> intrinsic_profile_name
    camera_mapping: Dict[int, str]
    # Коэффициент масштаба для простых измерений (пиксели -> мм)
    # Если расстояние больше, scale будет другим.
    scale_factor: float = 1.0
    # Расстояние до объекта (в мм), если нужно для коррекции перспективы в 2D
    distance_to_subject_mm: Optional[float] = None


class SyncEvent(BaseModel):
    camera_id: int
    frame_idx: int
    timestamp: float