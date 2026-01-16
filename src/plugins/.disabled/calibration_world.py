# src/plugins/calibration/world.py
import cv2
import numpy as np
import json
import os
from loguru import logger


class WorldAligner:
    # [FIX] Размер квадрата шахматной доски в МЕТРАХ
    # Если изменишь физическую доску, поменяй это значение здесь.
    SQUARE_SIZE_METERS = 0.04  # 4 см

    def __init__(self, board_def):
        self.board = board_def
        self.perspective_matrix = None
        self.px_per_cm = 0.0
        self.aligning_mode = False
        self.file_path = "config/world_cam_{id}.json"
        os.makedirs("config", exist_ok=True)

    def handle_command(self, cmd, args):
        if cmd == "align_world":
            self.aligning_mode = not self.aligning_mode
            logger.info(f"🌍 ALIGN MODE: {self.aligning_mode}")

    def reset(self):
        self.perspective_matrix = None
        self.px_per_cm = 0.0

    def process_align(self, ctx, corners, ids, vis):
        cv2.putText(vis, "ALIGN WORLD: SEARCHING...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        if corners is not None and len(corners) >= 4:
            try:
                if self.align(corners, ids):
                    self.aligning_mode = False
                    self.save_config(0)
                    ctx.ui.send_notification("success", f"Aligned! Scale: {self.px_per_cm:.2f} px/cm")
                    if hasattr(ctx, 'bus') and hasattr(ctx.bus, 'publish_event'):
                        ctx.bus.publish_event("command", {"target": "undistort", "cmd": "reload_config", "args": {}})
            except Exception as e:
                logger.error(f"Align Critical Error: {e}")

    def align(self, charuco_corners, charuco_ids):
        # 1. Получаем все 3D точки доски
        raw_obj_pts = self.board.getChessboardCorners()
        # Гарантируем плоский список (N, 3)
        all_obj_pts = np.array(raw_obj_pts).reshape(-1, 3)

        obj_points = []
        img_points = []
        ids_flat = charuco_ids.flatten()

        for i, id_val in enumerate(ids_flat):
            id_val = int(id_val)
            if id_val < len(all_obj_pts):
                pt3d = all_obj_pts[id_val]
                obj_points.append([pt3d[0], pt3d[1]])  # Z отбрасываем
                img_points.append(charuco_corners[i][0])  # charuco_corners shape is (N, 1, 2)

        if len(obj_points) < 4:
            return False

        # 2. Формируем массивы (N, 1, 2)
        obj_pts_np = np.array(obj_points, dtype=np.float32).reshape(-1, 1, 2)
        img_pts_np = np.array(img_points, dtype=np.float32).reshape(-1, 1, 2)

        # 3. Расчет гомографии
        H, mask = cv2.findHomography(img_pts_np, obj_pts_np, cv2.RANSAC, 5.0)

        if H is not None:
            self.perspective_matrix = H
            try:
                H_inv = np.linalg.inv(H)

                # Точка 0,0 (начало координат в метрах)
                p0 = np.array([[[0, 0]]], dtype=np.float32)

                # Точка смещенная на один квадрат вправо (в метрах)
                # [FIX] Используем константу вместо хардкода 0.04
                p1 = np.array([[[self.SQUARE_SIZE_METERS, 0]]], dtype=np.float32)

                px0 = cv2.perspectiveTransform(p0, H_inv)
                px1 = cv2.perspectiveTransform(p1, H_inv)

                # Дистанция в пикселях между этими двумя точками
                dist_px = np.linalg.norm(px1 - px0)

                # Переводим размер квадрата в сантиметры (метры * 100)
                # [FIX] Используем константу вместо хардкода 4.0
                square_size_cm = self.SQUARE_SIZE_METERS * 100.0

                if dist_px > 1e-5:
                    self.px_per_cm = dist_px / square_size_cm
                    return True
            except Exception as e:
                logger.error(f"Scale calc error: {e}")
                self.px_per_cm = 0.0
            return True

        return False

    def save_config(self, cam_id):
        path = self.file_path.format(id=cam_id)
        if self.perspective_matrix is None: return
        data = {
            "perspective_matrix": self.perspective_matrix.tolist(),
            "px_per_cm": float(self.px_per_cm)
        }
        with open(path, 'w') as f: json.dump(data, f)

    def load_config(self, cam_id):
        path = self.file_path.format(id=cam_id)
        if os.path.exists(path):
            with open(path, 'r') as f:
                d = json.load(f)
                self.perspective_matrix = np.array(d["perspective_matrix"])
                self.px_per_cm = float(d.get("px_per_cm", 0.0))
            return True
        return False