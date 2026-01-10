# src/stages/perspective.py
import cv2
import numpy as np
import json
import os
from src.core.pipeline import PipelineStage, FrameContext
from loguru import logger
from src.core.config import ROOT_DIR


class PerspectiveStage(PipelineStage):
    """
    CORE STAGE.
    Применяет матрицу перспективы к точкам.
    Преобразует координаты из 'Экранных' (px) в 'Мировые' (cm).
    """

    def __init__(self):
        super().__init__(name="perspective")
        self.perspective_matrix = None
        self.px_per_cm = 1.0
        self.is_active = False
        self.is_paused = False
        self._load_config()

    def _load_config(self):
        path = ROOT_DIR / "config" / "world_cam_0.json"
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    d = json.load(f)
                    self.perspective_matrix = np.array(d["perspective_matrix"])
                    self.px_per_cm = float(d.get("px_per_cm", 1.0))
                    self.is_active = True
                    logger.info("✅ Core Perspective: Config loaded")
            except Exception as e:
                logger.error(f"Core Perspective Config Error: {e}")
                self.is_active = False
        else:
            self.is_active = False

    def handle_command(self, cmd: str, args: dict):
        if cmd == "toggle_pause":
            self.is_paused = not self.is_paused
            state = "PAUSED" if self.is_paused else "RESUMED"
            logger.info(f"⏯️ [PerspectiveStage] {state}")

        elif cmd == "reload_config":
            logger.info("🔄 [PerspectiveStage] Reloading config...")
            self._load_config()

    def process(self, ctx: FrameContext):
        points = ctx.get_data("vision", "keypoints", [])
        if not points:
            return

        # ВАРИАНТ 1: Если калибровки НЕТ (или пауза)
        # Используем линейный масштаб (fallback)
        if not self.is_active or self.is_paused:
            scale = self.px_per_cm if self.px_per_cm > 0 else 1.0
            for p in points:
                val_x = p.ux if p.ux is not None else p.x
                val_y = p.uy if p.uy is not None else p.y
                # Просто делим пиксели на масштаб
                p.wx = val_x / scale
                p.wy = val_y / scale
            return

        # ВАРИАНТ 2: Матрица ЕСТЬ
        try:
            src_pts = []
            for p in points:
                # Приоритет: UX (исправленные) -> X (сырые)
                px = p.ux if p.ux is not None else p.x
                py = p.uy if p.uy is not None else p.y
                src_pts.append([[px, py]])

            src_pts = np.array(src_pts, dtype=np.float32)

            # Применяем матрицу.
            # Т.к. доска была задана как 0.04 (метры), результат будет в МЕТРАХ.
            dst_pts = cv2.perspectiveTransform(src_pts, self.perspective_matrix)

            for i, p in enumerate(points):
                raw_wx_meters = float(dst_pts[i][0][0])
                raw_wy_meters = float(dst_pts[i][0][1])

                # [FIX] КОНВЕРТАЦИЯ: Метры -> Сантиметры
                # Мы не делим на px_per_cm, потому что матрица уже сделала всю геометрию.
                # Мы просто приводим единицы измерения к CM.
                p.wx = raw_wx_meters * 100.0
                p.wy = raw_wy_meters * 100.0

        except Exception as e:
            logger.error(f"Perspective calc error: {e}")
            # Fallback
            for p in points:
                p.wx, p.wy = 0.0, 0.0