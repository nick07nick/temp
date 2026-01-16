# src/stages/calibration.py
import cv2
import cv2.aruco as aruco
import numpy as np
import time
import base64
import random
import bisect
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext

from src.stages.calibration_lens import LensCalibrator
from src.stages.calibration_world import WorldAligner


class CalibrationStage(PipelineStage):
    # Жесткие ступени экспозиции для UVC драйвера
    EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001]

    def __init__(self):
        super().__init__("calibration")

        # --- MODULES ---
        self.lens = LensCalibrator()
        self.world = WorldAligner(self.lens.CHARUCO_BOARD)

        # Загружаем сохраненные данные (ЭТО РАБОТАЕТ ДЛЯ ЛИНЗЫ)
        self.lens.load_config(0)

        # Пробуем загрузить калибровку мира (НОВАЯ СТРОКА)
        self.world.load_config(0)

        # --- CAPTURE SETTINGS ---
        self.GRID_ROWS = 5
        self.GRID_COLS = 5
        self.last_capture_time = 0.0
        self.last_capture_center = None
        self.CAPTURE_DELAY = 0.5
        self.MIN_CORNERS = 8
        self.MOVE_THRESHOLD = 30.0

        self.last_preview_time = 0.0
        self.current_board_angle = 0.0

        # [NEW] Режим "Охоты" за доской (Auto-Align)
        self.is_auto_aligning = False

        # --- UI STATS & ALGORITHMS ---
        self.marker_counts_buffer = []
        self.visual_marker_count = 0
        self.last_avg_update = 0.0
        self.AVG_WINDOW = 0.5

        self.tuning_mode = False
        self.tune_step = 0
        self.MAX_TUNE_STEPS = 40
        self.best_score = 0
        self.best_config = {}
        self.last_sent_config = {}
        self.tune_wait_frames = 0
        self.tune_current_score = 0

        self.maintenance_enabled = True
        self.ae_target_brightness = 110
        self.last_ae_time = 0.0
        self.AE_INTERVAL = 0.2
        self.MAX_GAIN = 1000
        self.MIN_GAIN = 0
        self.AE_DEADBAND = 10
        self.is_locking_target = False
        self.lock_wait_counter = 0

    def process(self, ctx: FrameContext):
        frame = ctx.frame
        if frame is None: return

        is_calib_mode = getattr(ctx.config, 'is_calibration_mode', False)

        if is_calib_mode:
            self._process_calibration_mode(ctx, frame)
        elif self.lens.camera_matrix is not None:
            # 1. Undistort (Линза)
            self.lens.undistort_points(ctx.get_data("vision", "keypoints", []))
            # 2. Perspective Transform (Мир) - в будущем будет здесь

        # Обновление UI вне режима калибровки (чтобы виджет знал статус)
        if not is_calib_mode and (time.time() - self.last_preview_time > 1.0):
            self.last_preview_time = time.time()
            self._send_ui_update(ctx, None)

    def _process_calibration_mode(self, ctx: FrameContext, frame):
        # 1. Grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 2. Detection (Делегируем модулю линзы)
        corners, ids, _ = self.lens.detect(gray)
        count = len(ids) if ids is not None else 0
        self._update_stats(count)

        if self.tuning_mode: self.tune_current_score = count

        # 3. Handle Commands
        self._handle_commands(ctx, gray, corners)

        # 4. Logic Router (Auto Tune / AE)
        if self.tuning_mode:
            self._run_auto_tune(ctx)
        elif self.is_locking_target:
            self._finalize_and_measure_target(ctx, gray)
        elif self.maintenance_enabled:
            self._run_maintenance_ae(ctx, gray, corners)

        # 5. Visuals & Data Prep
        vis_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        charuco_corners, charuco_ids = None, None
        current_sector = -1
        board_center = None

        if ids is not None and len(ids) > 0:
            aruco.drawDetectedMarkers(vis_frame, corners, ids, (0, 255, 255))

            # Interpolate (Делегируем)
            ret, charuco_corners, charuco_ids = self.lens.interpolate(corners, ids, gray)

            # [MODIFIED] Используем минимальный порог 6-8 для надежности
            if charuco_corners is not None and len(charuco_corners) >= 6:
                aruco.drawDetectedCornersCharuco(vis_frame, charuco_corners, charuco_ids, (0, 255, 0))

                # Расчет угла наклона
                self._calculate_board_angle(charuco_corners, charuco_ids, w, h)

                # Логика секторов (для линзы)
                avg_x = np.mean(charuco_corners[:, 0, 0])
                avg_y = np.mean(charuco_corners[:, 0, 1])
                board_center = (avg_x, avg_y)

                col = int(avg_x / (w / self.GRID_COLS))
                row = int(avg_y / (h / self.GRID_ROWS))
                col = min(max(col, 0), self.GRID_COLS - 1)
                row = min(max(row, 0), self.GRID_ROWS - 1)
                current_sector = row * self.GRID_COLS + col

                cv2.circle(vis_frame, (int(avg_x), int(avg_y)), 10, (0, 0, 255), -1)

                # --- [NEW] AUTO-TRIGGER FOR ALIGN WORLD ---
                # Если режим "Охоты" включен И мы видим достаточно точек (>=8)
                if self.is_auto_aligning and len(charuco_corners) >= 8:
                    self._perform_world_alignment(ctx, charuco_corners, charuco_ids)
                    self.is_auto_aligning = False  # Выключаем режим охоты
                    ctx.ui.notify("AUTO SNAP", "World Aligned!", "success")

        # 6. Preview Generation
        now = time.time()
        preview_b64 = None
        if now - self.last_preview_time > 0.1:
            self.last_preview_time = now

            # Индикация режима "Охоты"
            if self.is_auto_aligning:
                cv2.putText(vis_frame, "LOOKING FOR BOARD...", (w // 2 - 150, h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                cv2.rectangle(vis_frame, (20, 20), (w - 20, h - 20), (0, 255, 255), 4)

            elif self.maintenance_enabled:
                cv2.circle(vis_frame, (w - 20, 20), 8, (0, 255, 0), -1)
                cv2.putText(vis_frame, f"KEEP: {self.ae_target_brightness:.0f}", (w - 120, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                color = (0, 255, 0) if self.current_board_angle > 20 else (0, 165, 255)
                cv2.putText(vis_frame, f"Angle: {self.current_board_angle:.0f}", (20, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            else:
                cv2.circle(vis_frame, (w - 20, 20), 8, (0, 0, 255), -1)
                cv2.putText(vis_frame, "MANUAL", (w - 100, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            small_vis = cv2.resize(vis_frame, (480, 360))
            _, buffer = cv2.imencode('.jpg', small_vis, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            preview_b64 = base64.b64encode(buffer).decode('utf-8')

        # 7. Capture Logic (Только если НЕ идет поиск доски для World Align)
        last_capture_sector = -1
        if not self.tuning_mode and not self.is_locking_target and not self.is_auto_aligning:
            last_capture_sector = self._handle_capture(ctx, current_sector, board_center, charuco_corners, charuco_ids,
                                                       now)

        self._send_ui_update(ctx, preview_b64, last_capture_sector)

    # --- ACTION HANDLERS ---

    def _perform_world_alignment(self, ctx, corners, ids):
        try:
            # Вычисляем и автоматически сохраняем (save_config вызывается внутри align)
            H = self.world.align(corners, ids)

            ctx.ui.notify("World Aligned",
                          f"Scale: {self.world.px_per_cm:.1f} px/cm, Error: {self.world.reproj_error:.2f} mm",
                          "success")
            logger.info("Auto-Align executed and saved successfully.")
        except Exception as e:
            ctx.ui.notify("Align Failed", str(e), "error")
            logger.error(f"Align Error: {e}")

    def _handle_capture(self, ctx, current_sector, board_center, charuco_corners, charuco_ids, now):
        cmd = ctx.get_data("cmd_buffer", "calibration_cmd")
        should_capture = False

        if charuco_corners is None or len(charuco_corners) < self.MIN_CORNERS: return -1

        if cmd == "CAPTURE":
            should_capture = True
            ctx.set_data("cmd_buffer", "calibration_cmd", None)

        if not should_capture and current_sector != -1 and board_center is not None:
            time_ok = (now - self.last_capture_time) > self.CAPTURE_DELAY
            is_new_sector = current_sector not in self.lens.captured_sectors
            dist = 9999
            if self.last_capture_center is not None:
                dist = np.linalg.norm(np.array(board_center) - np.array(self.last_capture_center))
            is_moved = dist > self.MOVE_THRESHOLD
            if time_ok and (is_new_sector or is_moved):
                should_capture = True

        if should_capture:
            # [DELEGATE] Сохраняем в модуль линзы
            self.lens.add_sample(charuco_corners, charuco_ids, current_sector)

            self.last_capture_time = now
            self.last_capture_center = board_center

            # Логируем
            logger.debug(f"📸 Captured #{len(self.lens.all_corners)} at Sector {current_sector}")
            return current_sector
        return -1

    def _handle_commands(self, ctx, gray, corners):
        cmd = getattr(ctx.config, 'calibration_cmd', None)
        if not cmd: cmd = ctx.get_data("cmd_buffer", "calibration_cmd")

        if cmd == "ALIGN_WORLD":
            # [NEW] Вместо немедленного запуска, включаем режим "Охоты"
            self.is_auto_aligning = True
            ctx.ui.notify("Auto-Align", "Looking for 8+ corners...", "info")
            self._clear_cmd(ctx)
            return

        if cmd == "CALCULATE":
            try:
                ret, _ = self.lens.calibrate()
                ctx.ui.notify("Success", f"RMS: {ret:.3f} px", "success")
                self._send_ui_update(ctx, None)
            except Exception as e:
                ctx.ui.notify("Failed", str(e), "error")
                logger.error(f"Calib Error: {e}")
            self._clear_cmd(ctx)

        elif cmd == "RESET":
            self.lens.reset()
            self.is_auto_aligning = False  # Сбрасываем флаг охоты тоже
            self.last_capture_center = None
            ctx.ui.notify("Reset", "Data cleared", "info")
            self._clear_cmd(ctx)

        elif cmd == "AUTO_TUNE":
            if self.tuning_mode:
                self.tuning_mode = False
                self.is_locking_target = False
                self._send_params(ctx, self.best_config.get('exposure', 157), self.best_config.get('gain', 0))
            else:
                self.maintenance_enabled = False
                self._start_auto_tune(ctx)
            self._clear_cmd(ctx)

        elif cmd == "TOGGLE_MAINTENANCE":
            self.maintenance_enabled = not self.maintenance_enabled
            self._clear_cmd(ctx)

        elif cmd == "SET_AE_TARGET":
            val = self._measure_brightness(gray, corners)
            self.ae_target_brightness = val
            self.maintenance_enabled = True
            self._clear_cmd(ctx)

        elif cmd == "CAPTURE":
            ctx.set_data("cmd_buffer", "calibration_cmd", "CAPTURE")

    def _clear_cmd(self, ctx):
        if hasattr(ctx.config, 'calibration_cmd'): ctx.config.calibration_cmd = None
        ctx.set_data("cmd_buffer", "calibration_cmd", None)

    def _calculate_board_angle(self, corners, ids, w, h):
        mtx = self.lens.camera_matrix
        dist = self.lens.dist_coeffs

        if mtx is None:
            f_px = 4000.0  # 12mm guess
            mtx = np.array([[f_px, 0, w / 2], [0, f_px, h / 2], [0, 0, 1]], dtype=float)
            dist = np.zeros(5)

        valid, rvec, tvec = aruco.estimatePoseCharucoBoard(corners, ids, self.lens.CHARUCO_BOARD, mtx, dist, None, None)
        if valid:
            R, _ = cv2.Rodrigues(rvec)
            # Ось Z доски (нормаль)
            normal = R[:, 2]
            # Ось Z камеры (взгляд)
            camera_axis = np.array([0, 0, 1])
            dot = np.dot(normal, camera_axis)
            angle_rad = np.arccos(np.clip(abs(dot), -1.0, 1.0))
            self.current_board_angle = np.degrees(angle_rad)
        else:
            self.current_board_angle = 0.0

    # --- UI UPDATES ---

    def _send_ui_update(self, ctx, preview_b64, last_capture_sector=-1):
        status_msg = f"Data: {len(self.lens.all_corners)}"
        if self.tuning_mode:
            status_msg = f"AI Tune: {self.tune_step}"
        elif self.is_locking_target:
            status_msg = "Locking AE..."
        elif self.is_auto_aligning:
            status_msg = "SEARCHING..."

        # Безопасные преобразования типов
        try:
            board_angle = int(self.current_board_angle) if self.current_board_angle is not None else 0
        except:
            board_angle = 0

        try:
            world_scale = float(self.world.px_per_cm) if self.world.px_per_cm is not None else 0.0
        except:
            world_scale = 0.0

        try:
            world_error = float(self.world.reproj_error) if self.world.reproj_error is not None else 0.0
        except:
            world_error = 0.0

        update_data = {
            # --- Основные данные ---
            "captured_count": len(self.lens.all_corners),
            "captured_sectors": list(self.lens.captured_sectors),
            "current_sector": -1,
            "last_capture_sector": last_capture_sector,
            "status": status_msg,

            # --- Настройки ---
            "threshold_val": getattr(ctx.config, 'calib_threshold', 0),
            "is_tuning": self.tuning_mode or self.is_locking_target,
            "is_maintenance": self.maintenance_enabled,

            # --- Метрики Линзы ---
            "markers_on_frame": self.visual_marker_count,
            "has_calibration": self.lens.camera_matrix is not None,
            "enable_undistort": getattr(ctx.config, 'enable_undistort', False),

            # --- Метрики Мира ---
            "board_angle": board_angle,
            "world_scale": world_scale,  # px/cm
            "world_error": world_error,  # mm
            "has_world": self.world.perspective_matrix is not None,

            # Флаг, что мы в режиме охоты
            "is_aligning": self.is_auto_aligning
        }

        if preview_b64:
            update_data["preview_b64"] = preview_b64

        ctx.ui.update_widget("calib_tool", "Calibration", update_data, "text")

        # Логируем что отправляем
        # logger.debug(f"Calibration UI Update: captured_count={update_data['captured_count']}, "
        #              f"has_calibration={update_data['has_calibration']}, "
        #              f"has_world={update_data['has_world']}, "
        #              f"world_scale={update_data['world_scale']}, "
        #              f"world_error={update_data['world_error']}")

        try:
            # Проверяем, есть ли у ctx.ui метод update_widget
            if hasattr(ctx.ui, 'update_widget'):
                ctx.ui.update_widget("calib_tool", "Calibration", update_data, "text")
                # logger.debug("Calibration: update_widget called successfully")
            else:
                logger.error("Calibration: ctx.ui has no update_widget method!")
        except Exception as e:
            logger.error(f"Calibration: Error in update_widget: {e}")

    # --- AUTO TUNE / AE HELPERS ---

    def _start_auto_tune(self, ctx):
        self.tuning_mode = True
        self.tune_step = 0
        self.best_score = -1
        self.last_sent_config = {'exposure': getattr(ctx.config, 'exposure', 157),
                                 'gain': getattr(ctx.config, 'gain', 0)}
        self.best_config = self.last_sent_config.copy()
        logger.info("🤖 Starting AI Auto-Tune...")
        ctx.ui.notify("AI Tune", "Searching...", "info")

    def _measure_brightness(self, gray, corners):
        if corners is not None and len(corners) > 0:
            all_pts = np.concatenate(corners)
            x_min, x_max = int(np.min(all_pts[:, :, 0])), int(np.max(all_pts[:, :, 0]))
            y_min, y_max = int(np.min(all_pts[:, :, 1])), int(np.max(all_pts[:, :, 1]))
            if x_max - x_min > 10 and y_max - y_min > 10:
                roi = gray[y_min:y_max, x_min:x_max]
                return np.mean(roi)
        h, w = gray.shape
        center = gray[h // 3:2 * h // 3, w // 3:2 * w // 3]
        return np.mean(center)

    def _run_maintenance_ae(self, ctx, gray, corners):
        now = time.time()
        if now - self.last_ae_time < self.AE_INTERVAL: return

        curr_gain = getattr(ctx.config, 'gain', 0)
        curr_exp = getattr(ctx.config, 'exposure', 157)
        exp_idx = self._get_exp_index(curr_exp)

        current_brightness = self._measure_brightness(gray, corners)
        err = self.ae_target_brightness - current_brightness
        new_gain = curr_gain
        new_exp_idx = exp_idx

        if abs(err) > self.AE_DEADBAND:
            change = int(err * 0.8)
            change = max(-40, min(40, change))
            new_gain += change

        if new_gain <= self.MIN_GAIN and current_brightness > (self.ae_target_brightness + self.AE_DEADBAND):
            new_gain = self.MIN_GAIN
            new_exp_idx = max(0, new_exp_idx - 1)
        elif new_gain >= self.MAX_GAIN and current_brightness < (self.ae_target_brightness - self.AE_DEADBAND):
            new_gain = self.MAX_GAIN
            new_exp_idx = min(len(self.EXPOSURE_STEPS) - 1, new_exp_idx + 1)

        new_gain = max(self.MIN_GAIN, min(self.MAX_GAIN, new_gain))
        new_exp_val = self.EXPOSURE_STEPS[new_exp_idx]

        if new_gain != curr_gain or new_exp_val != curr_exp:
            self.last_ae_time = now
            self._send_params(ctx, new_exp_val, new_gain)

    def _finalize_and_measure_target(self, ctx, gray):
        if self.lock_wait_counter > 0:
            self.lock_wait_counter -= 1
            return
        corners, _, _ = self.lens.detector.detectMarkers(gray)
        measured_brightness = self._measure_brightness(gray, corners)
        self.ae_target_brightness = measured_brightness
        self.is_locking_target = False
        self.tuning_mode = False
        self.maintenance_enabled = True
        ctx.ui.notify("AE Locked", f"Target: {measured_brightness:.1f}", "success")

    def _run_auto_tune(self, ctx):
        try:
            if self.tune_wait_frames > 0:
                self.tune_wait_frames -= 1
                return
            current_score = self.tune_current_score
            improved = False
            if current_score > self.best_score:
                improved = True
            elif current_score == self.best_score:
                if self.last_sent_config.get('gain', 999) < self.best_config.get('gain', 999):
                    improved = True

            if improved:
                self.best_score = current_score
                self.best_config = self.last_sent_config.copy()

            self.tune_step += 1
            if self.tune_step >= self.MAX_TUNE_STEPS:
                self._send_params(ctx, self.best_config['exposure'], self.best_config['gain'])
                self.tuning_mode = False
                self.is_locking_target = True
                self.lock_wait_counter = 35
                ctx.ui.notify("Locking...", "Measuring...", "info")
                return

            base_exp_idx = self._get_exp_index(self.best_config['exposure'])
            base_gain = self.best_config['gain']
            next_exp_idx = base_exp_idx
            next_gain = base_gain
            action = random.choice(['inc_exp', 'dec_exp', 'inc_gain', 'dec_gain', 'inc_gain_big', 'dec_gain_big'])

            if action == 'inc_exp':
                next_exp_idx = min(base_exp_idx + 1, len(self.EXPOSURE_STEPS) - 1)
            elif action == 'dec_exp':
                next_exp_idx = max(base_exp_idx - 1, 0)
            elif action == 'inc_gain':
                next_gain += 5
            elif action == 'dec_gain':
                next_gain -= 5
            elif action == 'inc_gain_big':
                next_gain += 15
            elif action == 'dec_gain_big':
                next_gain -= 15

            next_exp_val = self.EXPOSURE_STEPS[next_exp_idx]
            next_gain = int(max(0, next_gain))
            self.last_sent_config = {'exposure': next_exp_val, 'gain': next_gain}
            self._send_params(ctx, next_exp_val, next_gain)
            self.tune_wait_frames = 25
        except Exception:
            self.tuning_mode = False

    def _send_params(self, ctx, exposure, gain):
        if hasattr(ctx, "bus") and ctx.bus:
            cam_id = getattr(ctx.config, "camera_id", 0)
            if cam_id is None: cam_id = 0
            ctx.bus.send_command(f"cam_{cam_id}", "set_params",
                                 {"exposure": int(exposure), "gain": int(gain), "auto_exposure": False})

    def _get_exp_index(self, val):
        idx = bisect.bisect_right(self.EXPOSURE_STEPS, val) - 1
        return max(0, idx)

    def _update_stats(self, count):
        self.marker_counts_buffer.append(count)
        now = time.time()
        if now - self.last_avg_update > self.AVG_WINDOW:
            if self.marker_counts_buffer:
                avg = sum(self.marker_counts_buffer) / len(self.marker_counts_buffer)
                self.visual_marker_count = int(round(avg))
            else:
                self.visual_marker_count = 0
            self.marker_counts_buffer = []
            self.last_avg_update = now

    def _draw_tuning_ui(self, frame, count, ctx):
        pass