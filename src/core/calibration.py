# src/core/calibration.py
import cv2
import numpy as np
import logging
from typing import List, Dict, Optional
from src.core.models import Point2D, CameraIntrinsics, WorkspaceProfile
from src.core.storage import CalibrationStorage

logger = logging.getLogger("BikeFit.Calibration")


class CalibrationManager:
    """
    Управляет активной конфигурацией.
    Связывает фронтенд (выбор профиля) и математику (undistort).
    """

    def __init__(self, storage: CalibrationStorage):
        self.storage = storage
        # Активные параметры для каждой камеры (ID -> Intrinsic)
        self._active_intrinsics: Dict[int, CameraIntrinsics] = {}
        self._active_scale: float = 1.0
        self._current_workspace: str = "Default"

    def set_workspace(self, workspace_name: str):
        ws = self.storage.get_workspace(workspace_name)
        if not ws:
            logger.error(f"Workspace '{workspace_name}' not found!")
            return

        self._current_workspace = ws.name
        self._active_scale = ws.scale_factor
        self._active_intrinsics.clear()

        # Загружаем линзы для каждой камеры согласно профилю
        for cam_id, profile_name in ws.camera_mapping.items():
            intr = self.storage.get_intrinsic(profile_name)
            if intr:
                self._active_intrinsics[cam_id] = intr
            else:
                logger.warning(f"Intrinsic profile '{profile_name}' missing for Cam {cam_id}")

        logger.info(f"Switched to Workspace: '{workspace_name}' (Scale: {self._active_scale})")

    def undistort_points(self, camera_id: int, points: List[Point2D]) -> List[Point2D]:
        """
        Исправляет дисторсию согласно текущему активному профилю.
        """
        if not points: return []

        # Если для камеры нет профиля - возвращаем как есть (или применяем дефолт)
        if camera_id not in self._active_intrinsics:
            return points

        profile = self._active_intrinsics[camera_id]
        mtx = profile.get_matrix_np()
        dist = profile.get_dist_np()

        pts_src = np.array([[[p.x, p.y]] for p in points], dtype=np.float64)
        pts_dst = cv2.undistortPoints(pts_src, mtx, dist, P=mtx)

        corrected = []
        for i, _ in enumerate(points):
            x_new, y_new = pts_dst[i][0]
            # Пример примитивной коррекции масштаба (перспективы)
            # В реальности тут будет умножение на матрицу гомографии
            # x_final = x_new * self._active_scale
            # y_final = y_new * self._active_scale

            corrected.append(Point2D(x=x_new, y=y_new, confidence=points[i].confidence))

        return corrected