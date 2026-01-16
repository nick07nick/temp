# src/plugins/calibration/manager.py
import cv2
import numpy as np
import time
import base64
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext

# Убедись, что эти файлы существуют и лежат рядом
from .lens import LensCalibrator
from .world import WorldAligner
from .autotune import AutoTuner
from .session_manager import CalibrationSession, create_session, get_all_sessions


class CalibrationPlugin(PipelineStage):
    def __init__(self):
        super().__init__("calibration_tool")

        # 1. Modules
        self.lens = LensCalibrator()
        self.world = WorldAligner(self.lens.CHARUCO_BOARD)
        try:
            self.lens.load_config(0)
            self.world.load_config(0)
        except Exception as e:
            logger.warning(f"Config load warning: {e}")

        self.tuner = AutoTuner()

        # 2. Session
        self.session = None
        self._capture_requested = False
        self._pending_apply_event = False

        # 3. Settings
        self.auto_capture_active = False
        self.min_markers_threshold = 20
        self.last_auto_capture_time = 0.0
        self.COOLDOWN_CAPTURE = 2.0
        self.show_grid = False

        # 4. State (ВАЖНО: По умолчанию пауза включена)
        self.is_wizard_open = False
        self.is_paused = True

        self.FPS_PROCESS = 15.0
        self.last_process_time = 0.0

        # 5. Caches
        self._cached_markers_count = 0
        self.current_board_angle = 0.0
        self.current_brightness = 0
        self._cached_heatmap = []
        self._cached_frames_stats = {}
        self.last_rms = 0.0
        self.last_align_error = 0.0

        self._last_vis_raw_ids = None

    def process(self, ctx: FrameContext):
        # 1. GLOBAL CHECK: Если визард закрыт — полный выход.
        # CPU usage = 0%
        if not self.is_wizard_open:
            return

        # 2. THROTTLING: Ограничиваем частоту обновлений UI (15 FPS)
        # Это критично, чтобы не забить WebSocket, особенно в режиме паузы.
        now = time.time()
        if (now - self.last_process_time) < (1.0 / self.FPS_PROCESS):
            return
        self.last_process_time = now

        # 3. HOT SWAP LOGIC
        if self._pending_apply_event:
            self._pending_apply_event = False
            ctx.bus.publish_event("command", {"target": "undistort", "cmd": "reload_config", "args": {}})
            ctx.bus.publish_event("command", {"target": "perspective", "cmd": "reload_config", "args": {}})
            if hasattr(ctx, "ui"):
                ctx.ui.send_notification("success", "System calibration updated!")

        # 4. LAZY INIT
        if self.session is None:
            self.session = CalibrationSession(ctx.config.camera_id)
            self._cached_heatmap = self.session.get_heatmap()
            self._cached_frames_stats = {k: v.reprojection_error for k, v in self.session.frames.items()}

            res = self.session.load_results()
            self.last_rms = res.get("rms", 0.0)
            self.last_align_error = res.get("align_error", 0.0)
            if "world_scale" in res:
                self.world.px_per_cm = float(res["world_scale"])

        # 5. PAUSE LOGIC
        # Если пауза: шлем статус (чтобы кнопки работали) и выходим.
        # Картинку не шлем (экономим трафик).
        if self.is_paused:
            self._send_ui(ctx, None)
            return

        # === HEAVY PROCESSING STARTS HERE ===

        # 6. Safe Grayscale
        if ctx.frame is None:
            return

        if len(ctx.frame.shape) == 3:
            gray = cv2.cvtColor(ctx.frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = ctx.frame

        self.current_brightness = int(np.mean(gray))

        # 7. Detect
        raw_corners, raw_ids = self.lens.detect_markers(gray)
        self._cached_markers_count = len(raw_ids) if raw_ids is not None else 0
        self._last_vis_raw_ids = raw_ids

        charuco_corners, charuco_ids = self.lens.interpolate(raw_corners, raw_ids, gray)
        has_interpolation = (charuco_corners is not None and len(charuco_corners) >= 4)

        if has_interpolation:
            self.current_board_angle = self.lens.estimate_angle(charuco_corners, charuco_ids, gray)

        # 8. Tuner
        self.tuner.process(ctx, self.current_brightness, self._cached_markers_count)

        # 9. Align World
        if self.world.aligning_mode:
            vis_dummy = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            success, error = self.world.process_align(ctx, charuco_corners, charuco_ids, vis_dummy)
            if success:
                self.last_align_error = error
                self.session.save_world_data(self.world.perspective_matrix, self.world.px_per_cm, error)

        # 10. Auto Capture
        if self.auto_capture_active:
            if (now - self.last_auto_capture_time) > self.COOLDOWN_CAPTURE:
                valid_markers = len(charuco_ids) if charuco_ids is not None else 0
                if valid_markers >= self.min_markers_threshold:
                    self._capture_requested = True
                    self.last_auto_capture_time = now

        # 11. Capture Frame
        if self._capture_requested:
            self._capture_requested = False
            frame_obj = self.session.add_frame(ctx.frame)
            if frame_obj.valid:
                logger.info(f"📸 Frame captured: {frame_obj.id}")
                self._cached_heatmap = self.session.get_heatmap()
                self._cached_frames_stats[frame_obj.id] = None

        # 12. Visualization
        vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        if self._last_vis_raw_ids is not None:
            cv2.aruco.drawDetectedMarkers(vis, raw_corners, raw_ids)
        if has_interpolation:
            cv2.aruco.drawDetectedCornersCharuco(vis, charuco_corners, charuco_ids, (0, 255, 0))

        if self.show_grid:
            self.world.draw_grid(vis)

        self._send_ui(ctx, vis)

    def handle_command(self, cmd, args):
        # === WIZARD CONTROL ===
        if cmd is not None:
            # Если плагин еще ни разу не запускался, self.camera_id == -1.
            # В таком случае мы, возможно, захотим пропустить команду или обработать.
            # Но лучше игнорировать, чтобы не инициализировать лишний раз.
            if self.camera_id != -1 and int(cmd) != self.camera_id:
                return
        elif cmd == "wizard_opened":
            self.is_wizard_open = True
            self.is_paused = True  # При открытии встаем на паузу (safety)
            logger.info("📐 Calibration Wizard Opened")

        elif cmd == "wizard_closed":
            self.is_wizard_open = False
            self.is_paused = True
            self.tuner.stop()
            logger.info("📐 Calibration Wizard Closed")

        elif cmd == "toggle_pause":
            self.is_paused = not self.is_paused
            if self.is_paused: self.tuner.stop()
            logger.info(f"Calibration paused: {self.is_paused}")

        # === REST OF LOGIC (Only if Wizard is Open) ===
        if not self.is_wizard_open:
            return

        if cmd in ["toggle_tuning", "measure_brightness", "toggle_maintenance"]:
            self.tuner.handle_command(cmd, args)

        elif cmd == "list_sessions":
            pass

        elif cmd == "load_session":
            name = args.get("name")
            if name:
                cam_id = self.session.camera_id if self.session else 0
                self.session = CalibrationSession(cam_id, name)
                self._update_cache_full()

        elif cmd == "create_session":
            name = args.get("name")
            cam_id = self.session.camera_id if self.session else 0
            self.session = create_session(cam_id, name)
            self._reset_cache()

        elif cmd == "capture_frame":
            self._capture_requested = True

        elif cmd == "toggle_frame":
            if self.session:
                fid = args.get("frame_id")
                self.session.delete_frame(fid)
                self._update_cache_partial(fid)

        elif cmd == "compute_calibration":
            if self.session:
                res = self.session.compute_calibration()
                if res:
                    self._cached_frames_stats = res.get("frames_stats", {})
                    self.last_rms = res.get("rms", 0.0)

        elif cmd == "apply_calibration":
            if self.session:
                ok, msg = self.session.apply_to_system()
                if ok:
                    self._pending_apply_event = True
                    logger.info(f"Apply scheduled: {msg}")
                else:
                    logger.error(f"Apply failed: {msg}")

        elif cmd == "set_autocapture":
            self.auto_capture_active = args.get("active", False)
            self.min_markers_threshold = int(args.get("min_markers", 20))

        elif cmd == "set_grid_visible":
            self.show_grid = args.get("visible", False)

        elif cmd == "align_world":
            self.world.handle_command(cmd, args)
        elif cmd == "reset_data":
            self.world.reset()

    # === HELPERS ===

    def _update_cache_full(self):
        """Обновляет все кэши из сессии"""
        if not self.session: return
        self._cached_heatmap = self.session.get_heatmap()
        self._cached_frames_stats = {k: v.reprojection_error for k, v in self.session.frames.items()}
        res = self.session.load_results()
        self.last_rms = res.get("rms", 0.0)
        self.last_align_error = res.get("align_error", 0.0)

        # Load World Data
        world_data = self.session.load_world_data()
        if world_data:
            self.world.set_data(world_data)
        else:
            self.world.reset()

    def _update_cache_partial(self, fid):
        self._cached_heatmap = self.session.get_heatmap()
        if fid in self._cached_frames_stats:
            del self._cached_frames_stats[fid]

    def _reset_cache(self):
        self._cached_heatmap = []
        self._cached_frames_stats = {}
        self.last_rms = 0.0
        self.last_align_error = 0.0
        self.world.reset()

    def _send_ui(self, ctx, img):
        img_src = None
        # Кодируем картинку только если она есть (не пауза)
        if img is not None:
            h, w = img.shape[:2]
            target_w = 800  # Оптимизация размера превью
            scale = target_w / w
            target_h = int(h * scale)

            small = cv2.resize(img, (target_w, target_h))
            _, buf = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            b64 = base64.b64encode(buf).decode('utf-8')
            img_src = f"data:image/jpeg;base64,{b64}"

        payload = {
            "preview_img": img_src,
            "markers_on_frame": int(self._cached_markers_count),
            "board_angle": float(self.current_board_angle),
            "is_aligning": bool(self.world.aligning_mode),
            "is_paused": bool(self.is_paused),

            "is_tuning": bool(self.tuner.is_tuning),
            "is_maintenance": bool(self.tuner.maintenance_active),
            "lock_target": int(self.tuner.target_brightness),
            "current_bright": int(self.current_brightness),

            "session_name": self.session.session_id if self.session else "N/A",
            "session_list": get_all_sessions(),
            "heatmap": self._cached_heatmap,
            "frames_stats": self._cached_frames_stats,
            "session_count": len(self.session.frames) if self.session else 0,

            "is_autocapture": self.auto_capture_active,
            "min_markers": self.min_markers_threshold,

            "world_scale": float(self.world.px_per_cm),
            "lens_rms": float(self.last_rms),
            "align_error": float(self.last_align_error),

            "show_grid": self.show_grid
        }

        if hasattr(ctx, "ui") and ctx.ui:
            ctx.ui.update_widget("calibration_widget", "Calibration", payload, "custom")