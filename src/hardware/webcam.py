# /src/hardware/webcam.py
import cv2
import subprocess
import threading
import time
import numpy as np
from typing import Optional, Dict, Any, Tuple
from loguru import logger as log

from src.core.config import settings, UVC_BIN_PATH
from src.data.schemas import CameraConfig


class Webcam:
    """
    Низкоуровневый драйвер камеры.
    Управляет захватом (OpenCV) и настройками железа (UVC).
    """

    def __init__(
            self,
            device_id: int = settings.CAMERA_INDEX,
            width: int = settings.CAMERA_WIDTH,
            height: int = settings.CAMERA_HEIGHT,
            fps: int = settings.CAMERA_FPS,
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
        self._hw_cache: Dict[str, str] = {}

        # Фоновый поток настроек
        self._stop_control_thread = threading.Event()
        self._control_thread = threading.Thread(target=self._control_worker, daemon=True, name=f"CamCtrl-{device_id}")

    def connect(self) -> bool:
        log.info(f"🔌 Connecting to Camera #{self._id}...")

        # Используем V4L2 backend
        self._cap = cv2.VideoCapture(self._id, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            # Fallback
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

        self._is_connected = True

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
        if self._cap:
            self._cap.release()
        log.info(f"Camera #{self._id} released.")

    # === CONFIG APPLICATOR ===

    def apply_config(self, config: CameraConfig):
        """
        Применяет конфиг.
        """
        updates = config.model_dump(exclude_unset=True, exclude_none=True)

        # [FIX] Принудительное отключение авто-экспозиции при ручной настройке
        if "exposure" in updates:
            # Получаем правильное имя команды для авто-режима (с дефисами)
            auto_key = self._map_param_to_uvc("auto_exposure")
            if auto_key:
                self._update_param(auto_key, "1")  # 1 = Manual Mode

        for key, value in updates.items():
            uvc_key = self._map_param_to_uvc(key)
            uvc_val = self._map_value_to_uvc(key, value)

            if uvc_key:
                self._update_param(uvc_key, uvc_val)

    def _map_param_to_uvc(self, key: str) -> Optional[str]:
        # [FIX] Вернул маппинг из старой работающей версии (с дефисами)
        mapping = {
            "auto_exposure": "auto-exposure-mode",
            "exposure": "exposure-time-abs",
            "gain": "gain",
            "auto_focus": "auto-focus",
            "focus": "focus-abs",
            "white_balance": "white-balance-temperature"
        }
        return mapping.get(key)

    def _map_value_to_uvc(self, key: str, value: Any) -> str:
        if key == "auto_exposure":
            # [FIX] Вернул логику из старого файла: 1=Manual, 8=Auto
            return "8" if value else "1"
        if key == "auto_focus":
            return "1" if value else "0"
        return str(value)

    def _update_param(self, control: str, value: str):
        with self._state_lock:
            self._pending_state[control] = value

    # === BACKGROUND WORKER ===

    def _control_worker(self):
        while not self._stop_control_thread.is_set():
            tasks = {}
            with self._state_lock:
                if self._pending_state:
                    tasks = self._pending_state.copy()
                    self._pending_state.clear()

            if not tasks:
                time.sleep(0.05)
                continue

            # [FIX] Приоритет: используем имена с дефисами, как они лежат в tasks
            priority_keys = ["auto-exposure-mode", "auto-focus"]

            sorted_items = sorted(tasks.items(), key=lambda item: 0 if item[0] in priority_keys else 1)

            for control, value in sorted_items:
                if self._hw_cache.get(control) == value:
                    continue

                success = self._run_uvc(control, value)
                if success:
                    self._hw_cache[control] = value
                    if control in priority_keys:
                        time.sleep(0.1)
                    else:
                        time.sleep(0.01)

    def _run_uvc(self, control: str, value: str) -> bool:
        if not UVC_BIN_PATH.exists():
            return False

        cmd = [str(UVC_BIN_PATH), "-I", str(self._id), "-s", f"{control}={value}"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
            if res.returncode != 0:
                log.warning(f"UVC Fail: {control}={value} -> {res.stderr.strip()}")
                return False
            return True
        except Exception as e:
            log.error(f"UVC Error: {e}")
            return False