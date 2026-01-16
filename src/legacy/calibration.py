# src/core/calibration.py
import cv2
import numpy as np
import logging
from typing import List, Dict, Optional
from src.core import Point2D, CameraIntrinsics
from src.core import CalibrationStorage

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
                logger.info(f"Loaded intrinsic '{profile_name}' for Cam {cam_id}")
            else:
                logger.warning(f"Intrinsic profile '{profile_name}' missing for Cam {cam_id}")

        logger.info(f"Switched to Workspace: '{workspace_name}' (Scale: {self._active_scale})")

    def undistort_points(self, camera_id: int, points: List[Point2D]) -> List[Point2D]:
        """
        Исправляет дисторсию согласно текущему активному профилю.
        Возвращает скорректированные точки.
        """
        if not points:
            return []

        # Если для камеры нет профиля - возвращаем как есть
        if camera_id not in self._active_intrinsics:
            # logger.debug(f"No calibration for camera {camera_id}, returning raw points")
            return points

        try:
            profile = self._active_intrinsics[camera_id]
            mtx = profile.get_matrix_np()
            dist = profile.get_dist_np()

            # Преобразуем точки в формат для OpenCV
            pts_src = np.array([[[p.x, p.y]] for p in points], dtype=np.float64)

            # Применяем коррекцию дисторсии
            pts_dst = cv2.undistortPoints(pts_src, mtx, dist, P=mtx)

            # Создаем новые скорректированные точки
            corrected = []
            for i, point in enumerate(points):
                x_new, y_new = pts_dst[i][0]

                # Применяем масштабный коэффициент (если нужен)
                x_final = x_new * self._active_scale
                y_final = y_new * self._active_scale

                new_point = point.model_copy(update={
                    "x": float(x_final),
                    "y": float(y_final)
                })
                corrected.append(new_point)

            # logger.debug(f"Undistorted {len(points)} points for camera {camera_id}")
            return corrected

        except Exception as e:
            logger.error(f"Undistort error for camera {camera_id}: {e}")
            return points  # В случае ошибки возвращаем исходные точки

    def get_camera_resolution(self, camera_id: int) -> Optional[tuple]:
        """
        Возвращает разрешение камеры из калибровки.
        """
        if camera_id in self._active_intrinsics:
            # Предполагаем, что калибровка сделана для определенного разрешения
            return (1920, 1200)
        return None

    def is_calibrated(self, camera_id: int) -> bool:
        """Проверяет, есть ли калибровка для камеры"""
        return camera_id in self._active_intrinsics