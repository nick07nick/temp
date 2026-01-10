# src/plugins/calibration/manager.py
import cv2
import numpy as np
import time
import base64
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext

from .lens import LensCalibrator
from .world import WorldAligner
from .autotune import AutoTuner


class CalibrationPlugin(PipelineStage):
    def __init__(self):
        super().__init__("calibration_tool")

        self.lens = LensCalibrator()
        self.world = WorldAligner(self.lens.CHARUCO_BOARD)
        try:
            self.lens.load_config(0)
            self.world.load_config(0)
        except Exception as e:
            logger.warning(f"Config load warning: {e}")

        self.tuner = AutoTuner()

        self.is_wizard_open = False
        self.is_paused = False

        # [FIX] Оптимизация производительности
        self.FPS_PROCESS = 15.0  # Частота работы алгоритмов (снижаем нагрузку с 90 до 15 FPS)
        self.last_process_time = 0.0
        self.last_stream_time = 0.0

        # UI Cache
        self._cached_markers_count = 0
        self.current_board_angle = 0.0
        self.current_brightness = 0

        # Кеш для отрисовки (чтобы UI не мерцал между расчетами)
        self._last_vis_raw_corners = []
        self._last_vis_raw_ids = None
        self._last_vis_charuco_corners = None
        self._last_vis_charuco_ids = None

    def process(self, ctx: FrameContext):
        # Если визард закрыт - вообще не тратим циклы
        if ctx.frame is None or not self.is_wizard_open:
            return

        now = time.time()

        # 1. THROTTLING (Ограничение FPS обработки)
        # Если прошло слишком мало времени с последнего расчета - пропускаем кадр
        if (now - self.last_process_time) < (1.0 / self.FPS_PROCESS):
            return

        self.last_process_time = now

        # Grayscale нужен для детекции
        gray = cv2.cvtColor(ctx.frame, cv2.COLOR_BGR2GRAY)

        # 2. PAUSE (Только стрим картинки, без расчетов)
        if self.is_paused:
            vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            cv2.putText(vis, "PAUSED", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            self._send_ui(ctx, vis)
            return

        # 3. DETECT (Тяжелая операция)
        raw_corners, raw_ids = self.lens.detect_markers(gray)
        self._cached_markers_count = len(raw_ids) if raw_ids is not None else 0
        self.current_brightness = int(np.mean(gray))

        # Сохраняем для отрисовки
        self._last_vis_raw_corners = raw_corners
        self._last_vis_raw_ids = raw_ids

        # 4. INTERPOLATE (Grid)
        charuco_corners, charuco_ids = self.lens.interpolate(raw_corners, raw_ids, gray)

        has_interpolation = False
        if charuco_corners is not None and not isinstance(charuco_corners, (int, float)):
            if len(charuco_corners) >= 4:
                has_interpolation = True

        self._last_vis_charuco_corners = charuco_corners
        self._last_vis_charuco_ids = charuco_ids

        # 5. Logic
        if has_interpolation:
            self.current_board_angle = self.lens.estimate_angle(charuco_corners, charuco_ids, gray)

        self.tuner.process(ctx, self.current_brightness, self._cached_markers_count)

        if has_interpolation and not self.tuner.is_tuning and not self.world.aligning_mode:
            self.lens.try_auto_capture(charuco_corners, charuco_ids, gray)

        # 6. UI Streaming (рисуем результат текущего шага)
        vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        if self._last_vis_raw_ids is not None and len(self._last_vis_raw_ids) > 0:
            cv2.aruco.drawDetectedMarkers(vis, self._last_vis_raw_corners, self._last_vis_raw_ids)

        if has_interpolation:
            cv2.aruco.drawDetectedCornersCharuco(vis, charuco_corners, charuco_ids, (0, 255, 0))

        self.lens.draw_grid(vis)

        if self.world.aligning_mode:
            self.world.process_align(ctx, charuco_corners, charuco_ids, vis)

        self._send_ui(ctx, vis)

    def handle_command(self, cmd, args):
        if cmd == "toggle_pause":
            self.is_paused = not self.is_paused
        elif cmd == "wizard_opened":
            self.is_wizard_open = True
            self.is_paused = False
        elif cmd == "wizard_closed":
            self.is_wizard_open = False
            self.tuner.stop()

        elif cmd in ["toggle_tuning", "toggle_maintenance", "measure_brightness"]:
            self.tuner.handle_command(cmd, args)
        elif cmd in ["calibrate_lens", "reset_data"]:
            self.lens.handle_command(cmd, args)
            if cmd == "reset_data": self.world.reset()
        elif cmd == "align_world":
            self.world.handle_command(cmd, args)

    def _send_ui(self, ctx, img):
        img_src = None
        if img is not None:
            # Сжимаем превью (CPU save)
            small = cv2.resize(img, (320, 240))
            _, buf = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            b64 = base64.b64encode(buf).decode('utf-8')
            img_src = f"data:image/jpeg;base64,{b64}"

        payload = {
            "preview_img": img_src,
            "markers_on_frame": int(self._cached_markers_count),
            "captured_count": int(len(self.lens.all_corners)),
            "board_angle": float(self.current_board_angle),
            "has_calibration": bool(self.lens.camera_matrix is not None),
            "has_world": bool(self.world.perspective_matrix is not None),
            "lens_rms": float(self.lens.rms),
            "world_scale": float(self.world.px_per_cm),
            "is_tuning": bool(self.tuner.is_tuning),
            "is_maintenance": bool(self.tuner.maintenance_active),
            "lock_target": int(self.tuner.target_brightness),
            "current_bright": int(self.current_brightness),
            "is_aligning": bool(self.world.aligning_mode),
            "is_paused": bool(self.is_paused)
        }
        ctx.ui.update_widget("calibration_widget", "Calibration", payload, "custom")