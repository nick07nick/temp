# src/stages/undistort.py
import cv2
import numpy as np
import json
import os
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext
from src.core.config import ROOT_DIR  # [ВАЖНО] Используем глобальный корень


class UndistortStage(PipelineStage):
    """
    CORE STAGE.
    Применяет математику дисторсии к точкам.
    Вход: point.x, point.y
    Выход: point.ux, point.uy
    """

    def __init__(self):
        super().__init__(name="undistort")
        self.camera_matrix = None
        self.dist_coeffs = None
        self.is_active = False
        self.is_paused = False  # Флаг ручной паузы
        self._load_config()

    def _load_config(self):
        # Используем ROOT_DIR для надежности
        path = ROOT_DIR / "config" / "calibration_cam_0.json"

        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    d = json.load(f)
                    self.camera_matrix = np.array(d["camera_matrix"])
                    self.dist_coeffs = np.array(d["dist_coeffs"])
                    self.is_active = True
                    logger.success("✅ [UndistortStage] Calibration loaded successfully")
            except Exception as e:
                logger.error(f"❌ [UndistortStage] Config Error: {e}")
                self.is_active = False
        else:
            logger.warning(f"⚠️ [UndistortStage] Config not found: {path}")
            self.is_active = False

    def handle_command(self, cmd: str, args: dict):
        """Управление стадией через EventBus"""
        if cmd == "toggle_pause":
            self.is_paused = not self.is_paused
            state = "PAUSED" if self.is_paused else "RESUMED"
            logger.info(f"⏯️ [UndistortStage] {state}")

        elif cmd == "reload_config":
            logger.info("🔄 [UndistortStage] Reloading config...")
            self._load_config()

    def process(self, ctx: FrameContext):
        points = ctx.get_data("vision", "keypoints", [])
        if not points:
            return

        # Если стадия выключена, конфига нет или пауза -> просто копируем координаты
        # Это важно, чтобы следующие стадии (perspective) получали ux/uy
        if not self.is_active or self.is_paused:
            for p in points:
                p.ux = p.x
                p.uy = p.y
            return

        try:
            # Подготовка данных для OpenCV (N, 1, 2)
            src_pts = np.array([[[p.x, p.y]] for p in points], dtype=np.float64)

            # P=camera_matrix сохраняет масштаб картинки (не обрезает края)
            dst_pts = cv2.undistortPoints(
                src_pts, self.camera_matrix, self.dist_coeffs, P=self.camera_matrix
            )

            # Запись результатов
            for i, p in enumerate(points):
                p.ux = float(dst_pts[i][0][0])
                p.uy = float(dst_pts[i][0][1])

        except Exception as e:
            logger.error(f"Undistort calc error: {e}")
            # Fallback на случай сбоя математики
            for p in points:
                p.ux, p.uy = p.x, p.y