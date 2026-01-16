# src/hardware/webcam.py
import cv2
import subprocess
import threading
import time
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from loguru import logger as log

from src.data.schemas import CameraConfig

# [FIX] Жестко заданный путь к утилите (из твоего лога)
# Если у тебя есть src.core.config.UVC_BIN_PATH, можно использовать его, но для надежности пропишем тут или fallback
UVC_BIN_PATH = Path("/Users/nikfrants/Documents/it/BikeFit/uvc-util/src/uvc-util")


class Webcam:
    def __init__(
            self,
            device_id: int,
            width: int,
            height: int,
            fps: int,
            shm_name: Optional[str] = None
    ):
        self._id = device_id
        self._target_width = width
        self._target_height = height
        self._target_fps = fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._is_connected = False

        # Очередь команд UVC
        self._pending_state: Dict[str, str] = {}
        self._state_lock = threading.Lock()

        # Кэш, чтобы не спамить одинаковыми командами в терминал
        self._hw_cache: Dict[str, str] = {}

        # Фоновый поток настроек (чтобы не фризить видео при вызове subprocess)
        self._stop_control_thread = threading.Event()
        self._control_thread = threading.Thread(
            target=self._control_worker,
            daemon=True,
            name=f"CamCtrl-{device_id}"
        )

    def connect(self) -> bool:
        log.info(f"🔌 Connecting to Camera #{self._id}...")

        # На Mac только дефолтный бэкенд (AVFoundation) работает стабильно для захвата
        self._cap = cv2.VideoCapture(self._id)

        if not self._cap.isOpened():
            log.critical(f"❌ Failed to open camera index {self._id}")
            self._is_connected = False
            return False

        # MJPG
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_height)
        self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        real_w = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        real_h = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        log.info(f"✅ Camera #{self._id} connected. Actual: {int(real_w)}x{int(real_h)}")

        self._is_connected = True

        # Запускаем поток управления UVC
        if not self._control_thread.is_alive():
            self._control_thread.start()

        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self._is_connected or self._cap is None:
            return False, None
        return self._cap.read()

    def release(self):
        self._is_connected = False
        self._stop_control_thread.set()
        if self._control_thread.is_alive():
            self._control_thread.join(timeout=0.2)

        if self._cap:
            self._cap.release()
        log.info(f"Camera #{self._id} released.")

    # === CONFIG APPLICATOR ===
    def apply_config(self, config: CameraConfig):
        """
        Получает конфиг от Woker-а и ставит задачи в очередь UVC.
        """
        # Превращаем Pydantic модель в словарь
        updates = config.model_dump(exclude_unset=True, exclude_none=True)

        # [CRITICAL] Обработка авто-экспозиции
        # Если пришел запрос на изменение 'exposure', значит мы перешли в ручной режим
        # Надо принудительно выключить авто (если оно не выключено явно)
        if "exposure" in updates and "auto_exposure" not in updates:
            # Добавляем команду отключения авто
            updates["auto_exposure"] = False

        for key, value in updates.items():
            uvc_key = self._map_param_to_uvc(key)
            uvc_val = self._map_value_to_uvc(key, value)

            if uvc_key:
                self._update_param(uvc_key, uvc_val)

    def _map_param_to_uvc(self, key: str) -> Optional[str]:
        # Точный маппинг по твоему логу uvc-util
        mapping = {
            "auto_exposure": "auto-exposure-mode",
            "exposure": "exposure-time-abs",
            "gain": "gain",
            "auto_focus": "auto-focus",
            "focus": "focus-abs",
            "white_balance": "white-balance-temperature",
            # Добавим brightness/contrast на всякий случай
            "brightness": "brightness",
            "contrast": "contrast"
        }
        return mapping.get(key)

    def _map_value_to_uvc(self, key: str, value: Any) -> str:
        if key == "auto_exposure":
            # Твоя камера: 8 = Auto, 1 = Manual
            return "8" if value else "1"
        if key == "auto_focus":
            return "1" if value else "0"

        # Для слайдеров это просто число-строка
        return str(value)

    def _update_param(self, control: str, value: str):
        with self._state_lock:
            self._pending_state[control] = value

    # === BACKGROUND WORKER (UVC Subprocess) ===
    def _control_worker(self):
        """
        В фоновом потоке берет задачи и вызывает uvc-util.
        Это предотвращает лаги видеопотока.
        """
        while not self._stop_control_thread.is_set():
            tasks = {}
            with self._state_lock:
                if self._pending_state:
                    tasks = self._pending_state.copy()
                    self._pending_state.clear()

            if not tasks:
                time.sleep(0.05)
                continue

            # Сортировка: Сначала переключаем режимы (Auto/Manual), потом значения
            priority_keys = ["auto-exposure-mode", "auto-focus"]
            sorted_items = sorted(tasks.items(), key=lambda item: 0 if item[0] in priority_keys else 1)

            for control, value in sorted_items:
                # Оптимизация: не шлем команду, если значение уже установлено
                if self._hw_cache.get(control) == value:
                    continue

                success = self._run_uvc(control, value)

                if success:
                    self._hw_cache[control] = value
                    log.debug(f"⚙️ UVC Set: {control}={value}")
                    # Пауза, чтобы камера успела обработать (особенно переключение режимов)
                    if control in priority_keys:
                        time.sleep(0.1)
                    else:
                        time.sleep(0.01)

    def _run_uvc(self, control: str, value: str) -> bool:
        if not UVC_BIN_PATH.exists():
            log.error(f"❌ UVC tool not found at {UVC_BIN_PATH}")
            return False

        # Формируем команду: ./uvc-util -I <index> -s control=value
        # -I (Index) надежнее, так как Оркестратор гарантирует нам индекс
        cmd = [str(UVC_BIN_PATH), "-I", str(self._id), "-s", f"{control}={value}"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
            if res.returncode != 0:
                log.warning(f"⚠️ UVC Fail ({self._id}): {control}={value} -> {res.stderr.strip()}")
                return False
            return True
        except Exception as e:
            log.error(f"❌ UVC Subprocess Error: {e}")
            return False