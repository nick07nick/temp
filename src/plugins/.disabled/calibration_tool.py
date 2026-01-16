import cv2
import cv2.aruco as aruco
import numpy as np
import time
import base64
import random
import bisect
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext


class CalibrationTool(PipelineStage):
    EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001]

    def __init__(self):
        super().__init__("calibration_tool")

        # Helpers
        try:
            from src.plugins.calibration_lens import LensCalibrator
            from src.plugins.calibration_world import WorldAligner
            self.lens = LensCalibrator()
            self.world = WorldAligner(self.lens.CHARUCO_BOARD)
            self.lens.load_config(0)
            self.world.load_config(0)
        except ImportError:
            logger.error("Calibration helpers not found!")
            self.lens = None
            self.world = None

        # --- Performance Throttling ---
        self.FPS_PROCESS = 10.0  # Частота работы ArUco (раз в сек)
        self.FPS_STREAM = 15.0  # Частота отправки картинки во фронт

        self.last_process_time = 0.0
        self.last_stream_time = 0.0
        self.last_pause_toggle = 0.0  # Для защиты от дребезга кнопки

        # State
        self.is_wizard_open = False
        self.is_paused = False

        self.GRID_COLS = 5
        self.GRID_ROWS = 5
        self.last_capture_time = 0.0
        self.min_capture_delay = 0.2
        self.recently_captured = {}
        self.current_board_angle = 0.0

        # Cache for UI (храним последние данные, чтобы отправлять их между кадрами обработки)
        self._cached_markers_count = 0
        self._cached_corners = []
        self._cached_ids = None

        # Results
        self.lens_rms = 0.0

        # Modes
        self.tuning_mode = False
        self.aligning_mode = False
        self.maintenance_active = False

        # Tuning
        self.tune_step = 0
        self.MAX_TUNE_STEPS = 40
        self.best_score = 0
        self.best_config = {}
        self.last_sent_config = {}
        self.tune_wait_frames = 0

        # Maintenance (AE)
        self.target_brightness = 110
        self.current_brightness = 0
        self.last_ae_time = 0.0
        self.AE_INTERVAL = 0.2
        self.MIN_GAIN = 0
        self.MAX_GAIN = 1000

    def process(self, ctx: FrameContext):
        # Если визард закрыт или пауза - вообще не тратим циклы, но изредка шлем статус
        if ctx.frame is None or not self.is_wizard_open or self.is_paused:
            if ctx.frame_id % 30 == 0: self._send_ui(ctx, None)
            return

        now = time.time()

        # 1. Лимит Стриминга: Если рано слать картинку, пропускаем всё, если не нужно обрабатывать
        # (Экономим ресурсы на cvtColor и resize)
        need_stream = (now - self.last_stream_time) > (1.0 / self.FPS_STREAM)
        need_process = (now - self.last_process_time) > (1.0 / self.FPS_PROCESS)

        if not need_stream and not need_process:
            return

        # 2. Подготовка (Общая для обоих)
        gray = cv2.cvtColor(ctx.frame, cv2.COLOR_BGR2GRAY)

        # 3. Тяжелая обработка (ArUco) - только 10 раз в сек
        if need_process:
            self.last_process_time = now
            self.current_brightness = int(np.mean(gray))

            if self.lens:
                # Сохраняем в кэш, чтобы использовать при отрисовке стрима
                self._cached_corners, self._cached_ids = self.lens.detect(gray)
                self._cached_markers_count = len(self._cached_ids) if self._cached_ids is not None else 0

                if self._cached_markers_count > 0:
                    self.current_board_angle = self.lens.estimate_angle(self._cached_corners, self._cached_ids, gray)

            # Алгоритмы запускаем тоже в ритме процессинга
            if self.tuning_mode:
                self._run_auto_tune(ctx, self._cached_markers_count)
            elif self.maintenance_active:
                self._run_maintenance(ctx, gray)

            if self.lens and self._cached_markers_count > 0 and not self.tuning_mode and not self.aligning_mode:
                self._try_auto_capture(self._cached_corners, self._cached_ids, gray)

        # 4. Стриминг и Отрисовка - 15-20 раз в сек
        if need_stream:
            self.last_stream_time = now

            # Рисуем на копии для UI (используем кэшированные данные с последнего процессинга)
            vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            if self._cached_markers_count > 0:
                aruco.drawDetectedMarkers(vis, self._cached_corners, self._cached_ids)

            if self.aligning_mode:
                self._run_align_world(ctx, self._cached_corners, self._cached_ids, vis)

            self._draw_grid_overlay(vis)
            self._send_ui(ctx, vis)

    # === UI UPDATE ===
    def _send_ui(self, ctx, img):
        img_src = None
        if img is not None:
            # Сжимаем сильнее (50%) для скорости
            small = cv2.resize(img, (320, 240))
            _, buf = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            b64 = base64.b64encode(buf).decode('utf-8')
            img_src = f"data:image/jpeg;base64,{b64}"

        payload = {
            "preview_img": img_src,
            "markers_on_frame": self._cached_markers_count,
            "captured_count": len(self.lens.all_corners) if self.lens else 0,
            "board_angle": self.current_board_angle,

            "has_calibration": self.lens.camera_matrix is not None if self.lens else False,
            "has_world": self.world.perspective_matrix is not None if self.world else False,
            "lens_rms": self.lens_rms,
            "world_scale": self.world.px_per_cm if self.world else 0.0,

            "is_tuning": self.tuning_mode,
            "is_aligning": self.aligning_mode,
            "is_maintenance": self.maintenance_active,
            "is_paused": self.is_paused,
            "lock_target": self.target_brightness,
            "current_bright": self.current_brightness
        }
        ctx.ui.update_widget("calibration_widget", "Calibration", payload, "custom")

    # === COMMANDS ===
    def handle_command(self, cmd, args):
        # logger.info(f"🔧 CMD: {cmd}") # Можно закомментить, чтобы не спамить лог

        if cmd == "wizard_opened":
            self.is_wizard_open = True
            self.is_paused = False

        elif cmd == "wizard_closed":
            self.is_wizard_open = False
            self.tuning_mode = False

        elif cmd == "toggle_pause":
            self.is_paused = not self.is_paused
        elif cmd == "toggle_tuning":
            self.tuning_mode = not self.tuning_mode
            if self.tuning_mode:
                self.maintenance_active = False
                self.aligning_mode = False
                self.tune_step = 0
                self.best_score = -1
                self.last_sent_config = {'exposure': 157, 'gain': 0}
                logger.info("🚀 STARTED AUTO TUNE")
            else:
                logger.info("🛑 STOPPED AUTO TUNE")

        elif cmd == "toggle_maintenance":
            self.maintenance_active = not self.maintenance_active
            logger.info(f"💡 MAINTENANCE: {self.maintenance_active}")

        elif cmd == "measure_brightness":
            self.target_brightness = self.current_brightness
            self.maintenance_active = True
            logger.info(f"🎯 MEASURED & LOCKED: {self.target_brightness}")

        elif cmd == "calibrate_lens":
            if self.lens:
                ret, _ = self.lens.calibrate()
                self.lens_rms = ret
                logger.success(f"CALCULATED LENS. RMS: {ret}")

        elif cmd == "reset_data":
            if self.lens: self.lens.reset()
            if self.world:
                self.world.perspective_matrix = None
                self.world.px_per_cm = 0.0
            self.recently_captured.clear()
            self.lens_rms = 0.0
            logger.warning("🗑️ ALL DATA RESET")

        elif cmd == "align_world":
            self.aligning_mode = not self.aligning_mode
            logger.info(f"🌍 ALIGN MODE: {self.aligning_mode}")

    # ... (Остальные методы: _run_align_world, _run_auto_tune, _run_maintenance,
    # _try_auto_capture, _draw_grid_overlay, _get_exp_index, _apply_camera_config
    # оставляем БЕЗ ИЗМЕНЕНИЙ из предыдущего файла) ...

    # Я продублирую их здесь, чтобы ты мог скопировать файл целиком и не запутаться:

    def _run_align_world(self, ctx, corners, ids, vis):
        cv2.putText(vis, "ALIGN WORLD: SEARCHING...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        if corners and len(corners) > 0:
            try:
                if self.world.align(corners, ids):
                    self.aligning_mode = False
                    self.world.save_config(0)
                    ctx.ui.send_notification("success", f"Aligned! Scale: {self.world.px_per_cm:.2f} px/cm")
                    if hasattr(ctx.bus, 'publish_event'):
                        ctx.bus.publish_event("command", {"target": "undistort", "cmd": "reload_config", "args": {}})
            except Exception as e:
                logger.error(f"Align Error: {e}")

    def _run_auto_tune(self, ctx, score):
        if self.tune_wait_frames > 0:
            self.tune_wait_frames -= 1
            return
        if score > self.best_score:
            self.best_score = score
            self.best_config = self.last_sent_config.copy()

        self.tune_step += 1
        if self.tune_step >= self.MAX_TUNE_STEPS:
            self.tuning_mode = False
            self._apply_camera_config(ctx, self.best_config)
            self.maintenance_active = True
            self.target_brightness = self.current_brightness
            ctx.ui.send_notification("success", "Tuning Done. Brightness Locked.")
            return

        base_exp = self.best_config.get('exposure', 157)
        base_gain = self.best_config.get('gain', 0)
        action = random.choice(['inc_exp', 'dec_exp', 'inc_gain', 'dec_gain'])

        new_exp = base_exp
        new_gain = base_gain
        idx = self._get_exp_index(base_exp)

        if action == 'inc_exp':
            new_exp = self.EXPOSURE_STEPS[min(idx + 1, len(self.EXPOSURE_STEPS) - 1)]
        elif action == 'dec_exp':
            new_exp = self.EXPOSURE_STEPS[max(0, idx - 1)]
        elif action == 'inc_gain':
            new_gain = min(self.MAX_GAIN, base_gain + 10)
        elif action == 'dec_gain':
            new_gain = max(self.MIN_GAIN, base_gain - 10)

        cfg = {'exposure': new_exp, 'gain': new_gain}
        self.last_sent_config = cfg
        self._apply_camera_config(ctx, cfg)
        self.tune_wait_frames = 5

    def _run_maintenance(self, ctx, gray):
        now = time.time()
        if now - self.last_ae_time < self.AE_INTERVAL: return
        self.last_ae_time = now
        err = self.target_brightness - self.current_brightness
        if abs(err) < 5: return
        curr_gain = getattr(ctx.config, 'gain', 0)
        curr_exp = getattr(ctx.config, 'exposure', 157)
        new_gain = curr_gain + int(err * 2.0)
        new_gain = max(self.MIN_GAIN, min(self.MAX_GAIN, new_gain))
        new_exp = curr_exp
        idx = self._get_exp_index(curr_exp)
        if new_gain == self.MAX_GAIN and err > 10:
            new_exp = self.EXPOSURE_STEPS[min(idx + 1, len(self.EXPOSURE_STEPS) - 1)]
        elif new_gain == self.MIN_GAIN and err < -10:
            new_exp = self.EXPOSURE_STEPS[max(0, idx - 1)]
        if new_gain != curr_gain or new_exp != curr_exp:
            self._apply_camera_config(ctx, {'exposure': new_exp, 'gain': new_gain})

    def _try_auto_capture(self, corners, ids, gray):
        if not self.lens: return
        c_corn, c_ids = self.lens.interpolate(corners, ids, gray)
        if c_corn is not None and len(c_corn) > 6:
            h, w = gray.shape
            pts = np.concatenate(corners)
            cx = np.mean(pts[:, :, 0])
            cy = np.mean(pts[:, :, 1])
            col = int(cx // (w / self.GRID_COLS))
            row = int(cy // (h / self.GRID_ROWS))
            sector_id = row * self.GRID_COLS + col
            now = time.time()
            last_cap = self.recently_captured.get(sector_id, 0)
            if now - last_cap > 1.0:
                self.lens.add_sample(c_corn, c_ids, sector_id)
                self.recently_captured[sector_id] = now
                # logger.info(f"📸 Captured Sector {sector_id}")

    def _draw_grid_overlay(self, img):
        h, w = img.shape[:2]
        sx, sy = w // self.GRID_COLS, h // self.GRID_ROWS
        for i in range(1, self.GRID_COLS): cv2.line(img, (i * sx, 0), (i * sx, h), (50, 50, 50), 1)
        for i in range(1, self.GRID_ROWS): cv2.line(img, (0, i * sy), (w, i * sy), (50, 50, 50), 1)
        if not self.lens: return
        for sec in self.lens.captured_sectors:
            r, c = sec // self.GRID_COLS, sec % self.GRID_COLS
            x1, y1 = c * sx, r * sy
            x2, y2 = (c + 1) * sx, (r + 1) * sy
            cv2.rectangle(img, (x1 + 2, y1 + 2), (x2 - 2, y2 - 2), (0, 150, 0), 2)
            cv2.putText(img, str(sec + 1), (x1 + 10, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 150, 0), 1)
        now = time.time()
        for sec, t in list(self.recently_captured.items()):
            if now - t > 0.5: continue
            r, c = sec // self.GRID_COLS, sec % self.GRID_COLS
            x1, y1 = c * sx, r * sy
            x2, y2 = (c + 1) * sx, (r + 1) * sy
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), 4)

    def _get_exp_index(self, val):
        idx = bisect.bisect_right(self.EXPOSURE_STEPS, val) - 1
        return max(0, idx)

    def _apply_camera_config(self, ctx, cfg):
        if hasattr(ctx, "bus"):
            ctx.bus.send_command(f"cam_{getattr(ctx, 'camera_id', 0)}", "set_params", cfg)