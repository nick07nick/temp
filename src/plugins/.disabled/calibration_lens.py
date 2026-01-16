import cv2
import cv2.aruco as aruco
import numpy as np
import json
import os


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

        self.camera_matrix = None
        self.dist_coeffs = None
        self.file_path = "config/calibration_cam_{id}.json"

    def detect(self, gray):
        if self.img_size is None:
            h, w = gray.shape
            self.img_size = (w, h)
        try:
            res = self.detector.detectMarkers(gray)
            if len(res) >= 2: return res[0], res[1]
            return [], None
        except Exception:
            return [], None

    def interpolate(self, corners, ids, gray):
        if ids is None or len(ids) == 0: return None, None
        try:
            res = aruco.interpolateCornersCharuco(corners, ids, gray, self.CHARUCO_BOARD)
            if isinstance(res, tuple) and len(res) >= 2:
                if len(res) == 3: return res[1], res[2]
                return res[0], res[1]
            return None, None
        except Exception:
            return None, None

    def add_sample(self, c_corn, c_ids, sector_id):
        self.all_corners.append(c_corn)
        self.all_ids.append(c_ids)
        self.captured_sectors.add(sector_id)

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
            return ret, mtx
        except Exception:
            return 999.9, None

    # [FIX] Исправленный метод расчета угла
    def estimate_angle(self, corners, ids, gray_frame):
        # 1. Нужна матрица камеры. Если нет - создаем примерную.
        mtx = self.camera_matrix
        dist = self.dist_coeffs
        if mtx is None:
            h, w = gray_frame.shape
            f = 1.2 * w
            mtx = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=float)
            dist = np.zeros(5)

        # 2. Сначала ИНТЕРПОЛЯЦИЯ! (Pose считается по Charuco, а не по маркерам)
        c_corners, c_ids = self.interpolate(corners, ids, gray_frame)

        if c_corners is None or len(c_corners) < 4:
            return 0.0

        # 3. Теперь считаем позу
        try:
            valid, rvec, tvec = aruco.estimatePoseCharucoBoard(c_corners, c_ids, self.CHARUCO_BOARD, mtx, dist, None,
                                                               None)
            if valid:
                R, _ = cv2.Rodrigues(rvec)
                # Угол между нормалью доски (Z) и осью камеры (Z)
                normal = R[:, 2]
                cam_axis = np.array([0, 0, 1])
                dot = np.dot(normal, cam_axis)
                angle = np.degrees(np.arccos(np.clip(abs(dot), -1.0, 1.0)))
                return angle
        except Exception:
            pass

        return 0.0

    def save_config(self, id):
        os.makedirs("config", exist_ok=True)
        data = {"camera_matrix": self.camera_matrix.tolist(), "dist_coeffs": self.dist_coeffs.tolist()}
        with open(self.file_path.format(id=id), 'w') as f: json.dump(data, f)

    def load_config(self, id):
        path = self.file_path.format(id=id)
        if os.path.exists(path):
            with open(path, 'r') as f:
                d = json.load(f)
                self.camera_matrix = np.array(d["camera_matrix"])
                self.dist_coeffs = np.array(d["dist_coeffs"])