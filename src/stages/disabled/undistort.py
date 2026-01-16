# src/stages/undistort.py
import cv2
import numpy as np
import json
import os
from src.core.pipeline import PipelineStage, FrameContext
from loguru import logger
from src.data.models import Point2D
from src.core.config import ROOT_DIR


class UndistortStage(PipelineStage):
    """
    Geometry Engine:
    1. Lens Undistort: x,y -> ux,uy (Исправление дисторсии)
    2. World Project: ux,uy -> wx,wy (Перевод в сантиметры)
    """

    def __init__(self):
        super().__init__(name="undistort")

        self.lens_file = ROOT_DIR / "config" / "calibration_cam_0.json"
        self.world_file = ROOT_DIR / "config" / "world_cam_0.json"

        # Lens Params
        self.camera_matrix = None
        self.dist_coeffs = None
        self.has_lens = False

        # World Params
        self.perspective_matrix = None
        self.px_per_cm = 1.0
        self.has_world = False

        self._load_configs()

    def _load_configs(self):
        # 1. Load Lens
        if os.path.exists(self.lens_file):
            try:
                with open(self.lens_file, 'r') as f:
                    d = json.load(f)
                    self.camera_matrix = np.array(d["camera_matrix"])
                    self.dist_coeffs = np.array(d["dist_coeffs"])
                    self.has_lens = True
                    logger.info("📐 Lens Calibration Loaded")
            except Exception as e:
                logger.error(f"Lens config error: {e}")

        # 2. Load World
        if os.path.exists(self.world_file):
            try:
                with open(self.world_file, 'r') as f:
                    d = json.load(f)
                    self.perspective_matrix = np.array(d["perspective_matrix"])
                    self.px_per_cm = float(d.get("px_per_cm", 1.0))
                    self.has_world = True
                    logger.info(f"🌍 World Calibration Loaded (Scale: {self.px_per_cm:.2f} px/cm)")
            except Exception as e:
                logger.error(f"World config error: {e}")

    def process(self, ctx: FrameContext):
        points: list[Point2D] = ctx.get_data("vision", "keypoints", [])
        if not points:
            self._update_ui(ctx)
            return

        # --- STEP 1: LENS UNDISTORT (x,y -> ux,uy) ---
        if self.has_lens:
            try:
                # Вход: (N, 1, 2)
                src_pts = np.array([[[p.x, p.y]] for p in points], dtype=np.float64)

                # Undistort
                # P=self.camera_matrix сохраняет масштаб картинки
                dst_pts = cv2.undistortPoints(
                    src_pts,
                    self.camera_matrix,
                    self.dist_coeffs,
                    P=self.camera_matrix
                )

                for i, p in enumerate(points):
                    p.ux = float(dst_pts[i][0][0])
                    p.uy = float(dst_pts[i][0][1])
            except Exception as e:
                logger.error(f"Lens Undistort Fail: {e}")
                # Fallback
                for p in points: p.ux, p.uy = p.x, p.y
        else:
            # Passthrough
            for p in points: p.ux, p.uy = p.x, p.y

        # --- STEP 2: WORLD PROJECT (ux,uy -> wx,wy) ---
        if self.has_world:
            try:
                # Берем UX, UY как источник
                src_world = np.array([[[p.ux, p.uy]] for p in points], dtype=np.float32)

                # Perspective Transform
                dst_world = cv2.perspectiveTransform(src_world, self.perspective_matrix)

                for i, p in enumerate(points):
                    # Результат в миллиметрах или сантиметрах (зависит от калибровки)
                    # Обычно мы калибровали в метрах, но допустим тут "единицы доски"
                    # Если нужно просто px -> cm через скейл:
                    # p.wx = p.ux / self.px_per_cm

                    # Если через матрицу (точнее):
                    p.wx = float(dst_world[i][0][0])
                    p.wy = float(dst_world[i][0][1])
            except Exception as e:
                logger.error(f"World Project Fail: {e}")
        else:
            # Fallback (просто делим на масштаб если есть, или 1)
            scale = self.px_per_cm if self.px_per_cm > 0 else 1.0
            for p in points:
                p.wx = p.ux / scale
                p.wy = p.uy / scale

        self._update_ui(ctx)

    def _update_ui(self, ctx: FrameContext):
        status = "success" if (self.has_lens and self.has_world) else "warning"
        if not self.has_lens: status = "neutral"

        ctx.ui.update_widget(
            "geo_status",
            "Geometry",
            {"value": "Active" if self.has_lens else "No Lens", "status": status},
            "status_indicator"
        )

    def handle_command(self, cmd, args):
        if cmd == "reload_calibration":
            self._load_configs()
            logger.info("🔄 Configs reloaded")