# src/plugins/calibration/autotune.py
import time
import random
import bisect
from loguru import logger


class AutoTuner:
    EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001]
    MIN_GAIN = 0
    MAX_GAIN = 1000
    MAX_TUNE_STEPS = 40
    AE_INTERVAL = 0.2

    # [FIX] Cooldown time (секунды). Время реакции камеры.
    COOLDOWN = 0.8

    def __init__(self):
        self.is_tuning = False
        self.maintenance_active = False
        self.tune_step = 0
        self.best_score = -1
        self.best_config = {}
        self.last_sent_config = {}
        self.tune_wait_frames = 0

        self.target_brightness = 110
        self.last_ae_time = 0.0

        # [FIX] Таймер последней команды для паузы
        self.last_command_time = 0.0

    def start(self):
        self.is_tuning = True
        self.maintenance_active = False
        self.tune_step = 0
        self.best_score = -1
        self.last_sent_config = {'exposure': 157, 'gain': 0}

        # [FIX] Даем фору при старте
        self.last_command_time = time.time()
        logger.info("🚀 STARTED AUTO TUNE")

    def stop(self):
        self.is_tuning = False
        # logger.info("🛑 STOPPED AUTO TUNE")

    def handle_command(self, cmd, args):
        if cmd == "toggle_tuning":
            if self.is_tuning:
                self.stop()
            else:
                self.start()
        elif cmd == "toggle_maintenance":
            self.maintenance_active = not self.maintenance_active
            logger.info(f"💡 MAINTENANCE: {self.maintenance_active}")
        elif cmd == "measure_brightness":
            # Target will be set in process loop
            self.maintenance_active = True
            self.force_measure = True

    def process(self, ctx, current_brightness, score):
        # [FIX] Глобальный кулдаун: если недавно меняли настройки - ждем
        if time.time() - self.last_command_time < self.COOLDOWN:
            return

        # 1. Handle "measure" command logic
        if getattr(self, 'force_measure', False):
            self.target_brightness = current_brightness
            self.force_measure = False
            logger.info(f"🎯 MEASURED & LOCKED: {self.target_brightness}")

        # 2. Tuning Logic
        if self.is_tuning:
            self._step_tuning(ctx, score)

        # 3. Maintenance Logic (Auto Exposure)
        elif self.maintenance_active:
            self._step_maintenance(ctx, current_brightness)

    def _step_tuning(self, ctx, score):
        if self.tune_wait_frames > 0:
            self.tune_wait_frames -= 1
            return

        if score > self.best_score:
            self.best_score = score
            self.best_config = self.last_sent_config.copy()

        self.tune_step += 1
        if self.tune_step >= self.MAX_TUNE_STEPS:
            self.is_tuning = False
            self._apply_config(ctx, self.best_config)
            self.maintenance_active = True
            ctx.ui.send_notification("success", "Tuning Done. Brightness Locked.")
            return

        # Simple Random Search
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
        self._apply_config(ctx, cfg)
        self.tune_wait_frames = 5

    def _step_maintenance(self, ctx, current_brightness):
        now = time.time()
        # Этот таймер можно оставить как доп. ограничение для P-контроллера
        if now - self.last_ae_time < self.AE_INTERVAL: return
        self.last_ae_time = now

        err = self.target_brightness - current_brightness
        if abs(err) < 5: return  # Deadband

        # [FIX] Безопасное получение конфига с дефолтами
        config_obj = getattr(ctx, 'config', None)
        curr_gain = getattr(config_obj, 'gain', 0) if config_obj else 0
        curr_exp = getattr(config_obj, 'exposure', 157) if config_obj else 157

        # Simple P-controller
        new_gain = curr_gain + int(err * 2.0)
        new_gain = max(self.MIN_GAIN, min(self.MAX_GAIN, new_gain))

        new_exp = curr_exp
        idx = self._get_exp_index(curr_exp)

        # If Gain maxed out, increase Exposure
        if new_gain == self.MAX_GAIN and err > 10:
            new_exp = self.EXPOSURE_STEPS[min(idx + 1, len(self.EXPOSURE_STEPS) - 1)]
        elif new_gain == self.MIN_GAIN and err < -10:
            new_exp = self.EXPOSURE_STEPS[max(0, idx - 1)]

        if new_gain != curr_gain or new_exp != curr_exp:
            self._apply_config(ctx, {'exposure': new_exp, 'gain': new_gain})

    def _get_exp_index(self, val):
        idx = bisect.bisect_right(self.EXPOSURE_STEPS, val) - 1
        return max(0, idx)

    def _apply_config(self, ctx, cfg):
        # Отправляем команду и обновляем время кулдауна
        if hasattr(ctx, "bus"):
            target = f"cam_{getattr(ctx, 'camera_id', 0)}"
            ctx.bus.send_command(target, "SET_CONFIG", cfg)

            # [FIX] Сброс таймера (ЖДЕМ ПОКА КАМЕРА ОТРАБОТАЕТ)
            self.last_command_time = time.time()