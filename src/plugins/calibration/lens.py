# src/plugins/calibration/lens.py
import cv2
import cv2.aruco as aruco
import numpy as np
import json
import os
import time
from loguru import logger
from src.core.config import ROOT_DIR  # [FIX] Используем глобальный путь


class LensCalibrator:
    def __init__(self):
        self.CHARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
        self.CHARUCO_BOARD = aruco.CharucoBoard((5, 7), 0.04, 0.02, self.CHARUCO_DICT)
        self.detector_params = aruco.DetectorParameters()
        self.detector_params.polygonalApproxAccuracyRate = 0.05
        self.detector = aruco.ArucoDetector(self.CHARUCO_DICT, self.detector_params)

        self.all_corners = []
        self.all_ids = []
        self.captured_sectors = set()
        self.img_size = None
        self.rms = 0.0

        self.camera_matrix = None
        self.dist_coeffs = None

        # [FIX] Абсолютный путь через ROOT_DIR
        self.config_dir = ROOT_DIR / "config"
        self.file_name_tpl = "calibration_cam_{id}.json"

        self.GRID_COLS = 5
        self.GRID_ROWS = 5
        self.recently_captured = {}

    def handle_command(self, cmd, args):
        if cmd == "calibrate_lens":
            ret, _ = self.calibrate()
            self.rms = float(ret)
            logger.success(f"CALCULATED LENS. RMS: {ret}")
        elif cmd == "reset_data":
            self.reset()
            self.rms = 0.0

    def detect_markers(self, gray):
        if self.img_size is None:
            h, w = gray.shape
            self.img_size = (w, h)
        try:
            corners, ids, _ = self.detector.detectMarkers(gray)
            return corners, ids
        except Exception:
            return [], None

    def interpolate(self, corners, ids, gray):
        if ids is None or len(ids) == 0: return None, None
        try:
            res = aruco.interpolateCornersCharuco(corners, ids, gray, self.CHARUCO_BOARD)
            if isinstance(res, tuple) and len(res) >= 3:
                return res[1], res[2]
            return None, None
        except Exception:
            return None, None

    def try_auto_capture(self, charuco_corners, charuco_ids, gray):
        if charuco_corners is None or len(charuco_corners) < 6:
            return

        h, w = gray.shape
        pts = np.concatenate(charuco_corners)
        cx = np.mean(pts[:, 0])
        cy = np.mean(pts[:, 1])

        col = int(cx // (w / self.GRID_COLS))
        row = int(cy // (h / self.GRID_ROWS))
        sector_id = row * self.GRID_COLS + col

        now = time.time()
        last_cap = self.recently_captured.get(sector_id, 0)

        if now - last_cap > 1.0:
            self.all_corners.append(charuco_corners)
            self.all_ids.append(charuco_ids)
            self.captured_sectors.add(sector_id)
            self.recently_captured[sector_id] = now
            # logger.info(f"📸 Captured Sector {sector_id}")

    # def draw_grid(self, img):
    #     h, w = img.shape[:2]
    #     sx, sy = w // self.GRID_COLS, h // self.GRID_ROWS
    #     for i in range(1, self.GRID_COLS): cv2.line(img, (i * sx, 0), (i * sx, h), (50, 50, 50), 1)
    #     for i in range(1, self.GRID_ROWS): cv2.line(img, (0, i * sy), (w, i * sy), (50, 50, 50), 1)
    #
    #     for sec in self.captured_sectors:
    #         r, c = sec // self.GRID_COLS, sec % self.GRID_COLS
    #         x1, y1 = c * sx, r * sy
    #         x2, y2 = (c + 1) * sx, (r + 1) * sy
    #         cv2.rectangle(img, (x1 + 2, y1 + 2), (x2 - 2, y2 - 2), (0, 150, 0), 2)
    #         cv2.putText(img, str(sec + 1), (x1 + 10, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 150, 0), 1)
    #
    #     now = time.time()
    #     for sec, t in list(self.recently_captured.items()):
    #         if now - t > 0.5: continue
    #         r, c = sec // self.GRID_COLS, sec % self.GRID_COLS
    #         x1, y1 = c * sx, r * sy
    #         x2, y2 = (c + 1) * sx, (r + 1) * sy
    #         cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), 4)

    def reset(self):
        self.all_corners = []
        self.all_ids = []
        self.captured_sectors.clear()

    def calibrate(self):
        if len(self.all_corners) < 10: return 0.0, None
        h, w = self.img_size
        f = 1.2 * w
        mtx = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=float)

        try:
            ret, mtx, dist, _, _ = aruco.calibrateCameraCharuco(
                self.all_corners, self.all_ids, self.CHARUCO_BOARD, (w, h), mtx, None
            )
            self.camera_matrix = mtx
            self.dist_coeffs = dist
            self.save_config(0)
            return float(ret), mtx
        except Exception:
            return 999.9, None

    def estimate_angle(self, c_corners, c_ids, gray_frame):
        if c_corners is None or len(c_corners) < 6: return 0.0
        mtx = self.camera_matrix
        dist = self.dist_coeffs
        if mtx is None:
            h, w = gray_frame.shape
            f = 1.2 * w
            mtx = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=float)
            dist = np.zeros(5)

        try:
            valid, rvec, tvec = aruco.estimatePoseCharucoBoard(c_corners, c_ids, self.CHARUCO_BOARD, mtx, dist, None,
                                                               None)
            if valid:
                R, _ = cv2.Rodrigues(rvec)
                normal = R[:, 2]
                angle = np.degrees(np.arccos(np.clip(abs(np.dot(normal, [0, 0, 1])), -1.0, 1.0)))
                return float(angle)
        except Exception:
            pass
        return 0.0

    def save_config(self, id):
        os.makedirs(self.config_dir, exist_ok=True)
        if self.camera_matrix is None: return
        data = {
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.tolist(),
            "rms": self.rms
        }

        # Запись по абсолютному пути
        full_path = self.config_dir / self.file_name_tpl.format(id=id)
        with open(full_path, 'w') as f: json.dump(data, f)

    def load_config(self, id):
        full_path = self.config_dir / self.file_name_tpl.format(id=id)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                d = json.load(f)
                self.camera_matrix = np.array(d["camera_matrix"])
                self.dist_coeffs = np.array(d["dist_coeffs"])