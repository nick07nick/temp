# src/core/pipeline/vision.py
import cv2
import numpy as np
import math
from typing import List, Optional
# from loguru import logger  # <--- ДОБАВИЛ ИМПОРТ

from src.core.pipeline.base import BaseStage, ProcessingContext
from src.core.models import Point2D


class VisionTrackingStage(BaseStage):
    def __init__(self):
        # Параметры трекинга
        self.lk_params = dict(
            winSize=(31, 31),
            maxLevel=4,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
        )
        # Параметры детектора
        self.threshold_value = 200
        self.min_area = 20
        self.max_area = 2000
        self.DETECTION_INTERVAL = 30
        self.MERGE_RADIUS = 40.0

        # Состояние
        self.prev_gray_frame: Optional[np.ndarray] = None
        self.tracked_points: List[Point2D] = []
        self.next_point_id = 0
        self.frames_since_detection = 0

    def process(self, ctx: ProcessingContext) -> None:
        gray = ctx.frame_gray
        status = "IDLE"

        # 1. TRACKING
        if self.prev_gray_frame is not None and len(self.tracked_points) > 0:
            lost = self._update_tracker(self.prev_gray_frame, gray)
            if lost > 0:
                self.frames_since_detection = self.DETECTION_INTERVAL + 1
            status = "TRACK"

        # 2. DETECTION
        need_detection = (
                len(self.tracked_points) == 0 or
                self.frames_since_detection > self.DETECTION_INTERVAL
        )

        if need_detection:
            status = "DETECT"
            found = self._run_detector(gray)

            # --- DEBUG LOG ---
            # logger.debug(f"[Vision] DETECT found {len(found)} candidates")
            # -----------------

            if found:
                self._merge_detections(found)
            self.frames_since_detection = 0

        self.frames_since_detection += 1
        self.prev_gray_frame = gray.copy()

        # Записываем результат в контекст
        ctx.points = [p.model_copy(update={}) for p in self.tracked_points]
        ctx.meta["mode"] = status

        # --- DEBUG LOG ---
        # ids = [p.id for p in ctx.points]
        # logger.debug(f"[Vision] Output: {len(ctx.points)} pts | IDs: {ids}")
        # -----------------

    def _update_tracker(self, prev_gray, curr_gray):
        if not self.tracked_points: return 0
        start_len = len(self.tracked_points)

        p0 = np.array([[p.x, p.y] for p in self.tracked_points], dtype=np.float32).reshape(-1, 1, 2)
        p1, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **self.lk_params)

        good_new = []
        if p1 is not None:
            status_mask = st.flatten()
            new_coords = p1.reshape(-1, 2)
            for i, status in enumerate(status_mask):
                if status == 1:
                    nx, ny = new_coords[i]
                    h, w = curr_gray.shape
                    if 0 <= nx < w and 0 <= ny < h:
                        old_pt = self.tracked_points[i]
                        old_pt.x = float(nx)
                        old_pt.y = float(ny)
                        good_new.append(old_pt)

        self.tracked_points = good_new
        self._remove_duplicates()
        return start_len - len(self.tracked_points)

    def _run_detector(self, gray: np.ndarray) -> List[Point2D]:
        _, thresh = cv2.threshold(gray, self.threshold_value, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in contours:
            if self.min_area <= cv2.contourArea(cnt) <= self.max_area:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cX = float(M["m10"] / M["m00"])
                    cY = float(M["m01"] / M["m00"])
                    candidates.append(Point2D(x=cX, y=cY, id=None))
        return candidates

    def _merge_detections(self, candidates: List[Point2D]):
        if not self.tracked_points:
            for cand in candidates:
                new_pt = cand.model_copy(update={"id": self.next_point_id})
                self.next_point_id += 1
                self.tracked_points.append(new_pt)
            return

        used_candidates = set()
        for tracker_pt in self.tracked_points:
            best_idx = -1
            min_dist = self.MERGE_RADIUS
            for i, cand in enumerate(candidates):
                if i in used_candidates: continue
                dist = math.hypot(cand.x - tracker_pt.x, cand.y - tracker_pt.y)
                if dist < min_dist:
                    min_dist = dist
                    best_idx = i

            if best_idx != -1:
                cand = candidates[best_idx]
                tracker_pt.x = cand.x
                tracker_pt.y = cand.y
                used_candidates.add(best_idx)

        for i, cand in enumerate(candidates):
            if i not in used_candidates:
                new_pt = cand.model_copy(update={"id": self.next_point_id})
                self.next_point_id += 1
                self.tracked_points.append(new_pt)

    def _remove_duplicates(self, min_dist=20.0):
        if len(self.tracked_points) < 2: return
        self.tracked_points.sort(key=lambda p: p.id if p.id is not None else -1)
        unique = []
        for p in self.tracked_points:
            is_dup = False
            for u in unique:
                if math.hypot(p.x - u.x, p.y - u.y) < min_dist:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(p)
        self.tracked_points = unique