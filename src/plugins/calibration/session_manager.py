# src/plugins/calibration/session_manager.py
import cv2
import numpy as np
import json
import time
import shutil
import os
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from pydantic import BaseModel
from src.core.config import ROOT_DIR

SESSION_ROOT = ROOT_DIR / "data" / "calibration_sessions"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)

# [FIX] Целевая папка для "боевой" калибровки
CURRENT_CALIB_DIR = ROOT_DIR / "data" / "current_calibration"
CURRENT_CALIB_DIR.mkdir(parents=True, exist_ok=True)


class CalibrationFrame(BaseModel):
    id: str
    path: str
    valid: bool
    used: bool
    corners_count: int
    reprojection_error: Optional[float] = None


class CalibrationSession:
    def __init__(self, camera_id: int, session_name: str = None):
        self.camera_id = camera_id
        if session_name:
            self.session_id = session_name
        else:
            self.session_id = f"cam_{camera_id}_{int(time.time())}"

        self.dir = SESSION_ROOT / self.session_id
        self.img_dir = self.dir / "images"

        self.CHARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.CHARUCO_BOARD = cv2.aruco.CharucoBoard((5, 7), 0.04, 0.02, self.CHARUCO_DICT)
        self.detector = cv2.aruco.ArucoDetector(self.CHARUCO_DICT)

        self.frames: Dict[str, CalibrationFrame] = {}
        self._init_storage()

    def _init_storage(self):
        if not self.dir.exists():
            self.dir.mkdir(parents=True)
            self.img_dir.mkdir()
        else:
            self.load_frames()

    def load_frames(self):
        p = self.dir / "frames.json"
        if p.exists():
            try:
                with open(p) as f:
                    data = json.load(f)
                    self.frames = {k: CalibrationFrame(**v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"Failed to load frames: {e}")

    def load_results(self) -> Dict:
        p = self.dir / "result.json"
        if p.exists():
            try:
                with open(p) as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_world_data(self, matrix: np.ndarray, scale: float, error: float = 0.0):
        world_data = {
            "perspective_matrix": matrix.tolist(),
            "px_per_cm": float(scale),
            "align_error": float(error)
        }
        with open(self.dir / "world.json", "w") as f:
            json.dump(world_data, f)

        res_path = self.dir / "result.json"
        current_res = {}
        if res_path.exists():
            with open(res_path, 'r') as f: current_res = json.load(f)

        current_res.update({
            "world_scale": float(scale),
            "align_error": float(error)
        })
        if "rms" not in current_res: current_res["rms"] = 0.0

        with open(res_path, "w") as f:
            json.dump(current_res, f)

    def load_world_data(self) -> Optional[Dict]:
        p = self.dir / "world.json"
        if p.exists():
            try:
                with open(p) as f:
                    return json.load(f)
            except:
                pass
        return None

    def add_frame(self, image: np.ndarray) -> CalibrationFrame:
        frame_id = f"img_{int(time.time() * 1000)}"
        filename = f"{frame_id}.jpg"
        filepath = self.img_dir / filename

        cv2.imwrite(str(filepath), image)
        valid, count = self._detect(image)

        frame = CalibrationFrame(
            id=frame_id, path=str(filepath), valid=valid, used=valid, corners_count=count,
            reprojection_error=None
        )
        self.frames[frame_id] = frame
        self._save_db()
        return frame

    def _detect(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is not None and len(ids) > 0:
            _, c_corners, c_ids = cv2.aruco.interpolateCornersCharuco(
                corners, ids, gray, self.CHARUCO_BOARD
            )
            if c_corners is not None:
                return True, len(c_corners)
        return False, 0

    def delete_frame(self, frame_id: str):
        if frame_id in self.frames:
            fr = self.frames[frame_id]
            try:
                if os.path.exists(fr.path): os.remove(fr.path)
            except:
                pass
            del self.frames[frame_id]
            self._save_db()

    def get_heatmap(self, width=1920, height=1200, grid_size=100):
        rows = height // grid_size
        cols = width // grid_size
        grid_scores = np.zeros((rows, cols), dtype=float)
        grid_counts = np.zeros((rows, cols), dtype=int)

        res = self.load_results()
        mtx = np.array(res['mtx']) if 'mtx' in res else None
        dist = np.array(res['dist']) if 'dist' in res else None
        has_calib = mtx is not None

        used_frames = [f for f in self.frames.values() if f.used and f.valid]

        for frame in used_frames:
            if not Path(frame.path).exists(): continue
            img = cv2.imread(frame.path)
            if img is None: continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            corners, ids, _ = self.detector.detectMarkers(gray)
            if ids is None: continue

            _, c_corners, c_ids = cv2.aruco.interpolateCornersCharuco(
                corners, ids, gray, self.CHARUCO_BOARD
            )

            if c_corners is not None and len(c_corners) > 0:
                point_errors = []
                if has_calib:
                    try:
                        obj_pts = self.CHARUCO_BOARD.getChessboardCorners()[c_ids.flatten()]
                        valid, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
                            c_corners, c_ids, self.CHARUCO_BOARD, mtx, dist, None, None
                        )
                        if valid:
                            proj_pts, _ = cv2.projectPoints(obj_pts, rvec, tvec, mtx, dist)
                            for k in range(len(c_corners)):
                                err = np.linalg.norm(c_corners[k] - proj_pts[k])
                                point_errors.append(err)
                    except Exception:
                        point_errors = [1.0] * len(c_corners)

                for i, point in enumerate(c_corners):
                    x, y = point[0]
                    c = int(x // grid_size)
                    r = int(y // grid_size)

                    if 0 <= r < rows and 0 <= c < cols:
                        grid_counts[r, c] += 1
                        score = 1.0
                        if has_calib and i < len(point_errors):
                            err = point_errors[i]
                            score = 0.5 / max(0.1, err)
                        grid_scores[r, c] += score

        heatmap = np.zeros((rows, cols), dtype=int)
        for r in range(rows):
            for c in range(cols):
                count = grid_counts[r, c]
                if count > 0:
                    avg_score = grid_scores[r, c] / count
                    count_factor = min(count, 3)
                    val = count_factor * avg_score * 30
                    heatmap[r, c] = int(min(100, val))

        return heatmap.tolist()

    def apply_to_system(self):
        """Копирует конфиги в data/current_calibration"""
        res = self.load_results()
        if not res or "mtx" not in res:
            return False, "No calibration data (calc first)"

        # 1. Формируем и сохраняем result.json (Линза)
        lens_config = {
            "mtx": res["mtx"],  # Твой код читает mtx/dist, это ок
            "dist": res["dist"],
            "rms": res["rms"],
            "date": time.time()
        }

        # 2. Формируем и сохраняем world.json (Перспектива)
        world_data = self.load_world_data()  # Читаем из сессии

        try:
            # Save Lens
            with open(CURRENT_CALIB_DIR / "result.json", 'w') as f:
                json.dump(lens_config, f)

            # Save World (если есть)
            if world_data:
                with open(CURRENT_CALIB_DIR / "world.json", 'w') as f:
                    json.dump(world_data, f)

            logger.success(f"✅ Applied session {self.session_id} to SYSTEM (data/current_calibration)")
            return True, "Applied successfully"
        except Exception as e:
            logger.error(f"Apply failed: {e}")
            return False, str(e)

    def compute_calibration(self):
        all_corners = []
        all_ids = []
        img_size = None
        frame_ids_ordered = []

        active_frames = [f for f in self.frames.values() if f.used and f.valid]
        if len(active_frames) < 5: return None

        logger.info(f"📐 Calculating on {len(active_frames)} frames...")

        for frame in active_frames:
            if not Path(frame.path).exists(): continue
            img = cv2.imread(frame.path)
            if img is None: continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if img_size is None: img_size = gray.shape[::-1]
            corners, ids, _ = self.detector.detectMarkers(gray)
            if ids is not None:
                _, c_corners, c_ids = cv2.aruco.interpolateCornersCharuco(
                    corners, ids, gray, self.CHARUCO_BOARD
                )
                if c_corners is not None and len(c_corners) > 6:
                    all_corners.append(c_corners)
                    all_ids.append(c_ids)
                    frame_ids_ordered.append(frame.id)

        try:
            ret, mtx, dist, rvecs, tvecs = cv2.aruco.calibrateCameraCharuco(
                all_corners, all_ids, self.CHARUCO_BOARD, img_size, None, None
            )
            for i, frame_id in enumerate(frame_ids_ordered):
                projected_points, _ = cv2.projectPoints(
                    self.CHARUCO_BOARD.getChessboardCorners()[all_ids[i].flatten()],
                    rvecs[i], tvecs[i], mtx, dist
                )
                error = cv2.norm(all_corners[i], projected_points, cv2.NORM_L2) / len(projected_points)
                self.frames[frame_id].reprojection_error = float(error)

            self._save_db()

            res_path = self.dir / "result.json"
            res_data = {}
            if res_path.exists():
                with open(res_path) as f: res_data = json.load(f)

            res_data.update({
                "mtx": mtx.tolist(),
                "dist": dist.tolist(),
                "rms": ret,
                "date": time.time()
            })
            with open(res_path, "w") as f:
                json.dump(res_data, f)

            logger.success(f"Calibration Result: RMSE={ret:.4f}")

            return {
                "mtx": mtx.tolist(),
                "dist": dist.tolist(),
                "rms": ret,
                "frames_stats": {f.id: f.reprojection_error for f in active_frames}
            }

        except Exception as e:
            logger.error(f"Calib Error: {e}")
            return None

    def _save_db(self):
        data = {k: v.dict() for k, v in self.frames.items()}
        with open(self.dir / "frames.json", "w") as f:
            json.dump(data, f, indent=2)


def get_all_sessions() -> List[Dict]:
    sessions = []
    for d in SESSION_ROOT.iterdir():
        if d.is_dir():
            rms = 0.0
            count = 0
            scale = 0.0

            res_file = d / "result.json"
            if res_file.exists():
                try:
                    with open(res_file) as f:
                        res = json.load(f)
                        rms = res.get("rms", 0.0)
                        scale = res.get("world_scale", 0.0)
                except:
                    pass

            frames_file = d / "frames.json"
            if frames_file.exists():
                try:
                    with open(frames_file) as f:
                        data = json.load(f)
                        count = len(data)
                except:
                    pass

            sessions.append({
                "id": d.name,
                "name": d.name,
                "rms": rms,
                "count": count,
                "scale": scale
            })
    return sorted(sessions, key=lambda x: x['name'], reverse=True)


def create_session(camera_id: int, name: str) -> CalibrationSession:
    clean_name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
    full_name = f"cam_{camera_id}_{clean_name}"
    return CalibrationSession(camera_id, full_name)