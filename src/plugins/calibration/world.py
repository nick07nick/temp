# src/plugins/calibration/world.py
import cv2
import numpy as np
import json
import os
from loguru import logger
from src.core.config import ROOT_DIR  # [FIX]


class WorldAligner:
    def __init__(self, board_def):
        self.board = board_def
        self.perspective_matrix = None
        self.px_per_cm = 0.0
        self.aligning_mode = False

        # [FIX] Абсолютный путь
        self.config_dir = ROOT_DIR / "config"
        self.file_name_tpl = "world_cam_{id}.json"

        os.makedirs(self.config_dir, exist_ok=True)

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
        raw_obj_pts = self.board.getChessboardCorners()
        all_obj_pts = np.array(raw_obj_pts).reshape(-1, 3)

        obj_points = []
        img_points = []
        ids_flat = charuco_ids.flatten()

        for i, id_val in enumerate(ids_flat):
            id_val = int(id_val)
            if id_val < len(all_obj_pts):
                pt3d = all_obj_pts[id_val]
                obj_points.append([pt3d[0], pt3d[1]])
                img_points.append(charuco_corners[i][0])

        if len(obj_points) < 4:
            return False

        obj_pts_np = np.array(obj_points, dtype=np.float32).reshape(-1, 1, 2)
        img_pts_np = np.array(img_points, dtype=np.float32).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(img_pts_np, obj_pts_np, cv2.RANSAC, 5.0)

        if H is not None:
            self.perspective_matrix = H
            try:
                H_inv = np.linalg.inv(H)
                p0 = np.array([[[0, 0]]], dtype=np.float32)
                p1 = np.array([[[0.04, 0]]], dtype=np.float32)
                px0 = cv2.perspectiveTransform(p0, H_inv)
                px1 = cv2.perspectiveTransform(p1, H_inv)
                dist_px = np.linalg.norm(px1 - px0)
                if dist_px > 1e-5:
                    self.px_per_cm = dist_px / 4.0
                    return True
            except Exception:
                self.px_per_cm = 0.0
            return True

        return False

    def save_config(self, cam_id):
        os.makedirs(self.config_dir, exist_ok=True)
        if self.perspective_matrix is None: return
        data = {
            "perspective_matrix": self.perspective_matrix.tolist(),
            "px_per_cm": float(self.px_per_cm)
        }
        full_path = self.config_dir / self.file_name_tpl.format(id=cam_id)
        with open(full_path, 'w') as f: json.dump(data, f)

    def load_config(self, cam_id):
        full_path = self.config_dir / self.file_name_tpl.format(id=cam_id)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                d = json.load(f)
                self.perspective_matrix = np.array(d["perspective_matrix"])
                self.px_per_cm = float(d.get("px_per_cm", 0.0))
            return True
        return False