# src/core/event_bus.py
import multiprocessing
import queue
from typing import Any, Dict, Optional, Union
from loguru import logger


class EventBus:
    def __init__(self):
        # Очередь для критических событий (Log, Heartbeat, SystemState)
        self._upstream_queue = multiprocessing.Queue(maxsize=1000)

        # Очередь для потоковых данных (Video, Keypoints)
        # Strategy: Always Fresh (храним только последние 3 пакета)
        self._stream_queue = multiprocessing.Queue(maxsize=3)

        # Очереди команд К воркерам (Key: Camera ID, Value: Queue)
        self._command_queues: Dict[int, multiprocessing.Queue] = {}

    def register_worker(self, camera_id: int) -> multiprocessing.Queue:
        """Регистрация очереди команд для камеры"""
        q = multiprocessing.Queue(maxsize=100)
        self._command_queues[camera_id] = q
        logger.info(f"🔌 EventBus: Registered queue for Camera {camera_id}")
        return q

    # --- Методы Воркеров (Upstream) ---

    def publish_stream(self, data: Dict[str, Any]):
        """Отправка данных (Non-blocking drop old)"""
        try:
            self._stream_queue.put_nowait(data)
        except queue.Full:
            try:
                self._stream_queue.get_nowait()
                self._stream_queue.put_nowait(data)
            except Exception:
                pass

    def publish_event(self, event_type: str, payload: Dict[str, Any]):
        msg = {"type": event_type, "payload": payload}
        try:
            self._upstream_queue.put(msg, timeout=0.1)
        except queue.Full:
            logger.error(f"EventBus Upstream Full! Dropped: {event_type}")

    # --- Методы Сервера/Оркестратора (Downstream) ---

    def get_updates(self) -> Optional[Dict]:
        try:
            return self._upstream_queue.get_nowait()
        except queue.Empty:
            return None

    def get_stream_data(self) -> Optional[Dict]:
        try:
            return self._stream_queue.get_nowait()
        except queue.Empty:
            return None

    def send_command(self, target_or_id: Union[str, int], cmd_or_payload: Union[str, Dict], args: Optional[Dict] = None):
        """
        Универсальный метод отправки.
        ВАЖНО: Обеспечивает совместимость между Orchestrator (int, dict) и API (str, str, dict).
        """

        # --- ВАРИАНТ 1: Вызов из Orchestrator (int, dict) ---
        if isinstance(target_or_id, int) and isinstance(cmd_or_payload, dict):
            camera_id = target_or_id
            payload = cmd_or_payload
            self._send_to_queue(camera_id, payload)
            return

        # --- ВАРИАНТ 2: Вызов из API/Plugins (str, str, dict) ---
        target_str = str(target_or_id)
        cmd_str = str(cmd_or_payload)
        real_args = args or {}

        # [FIX] Формируем payload строго под Pydantic модель воркера.
        # Воркер ждет: class PluginCommand(BaseModel): cmd: str, args: dict
        # Мы НЕ включаем сюда 'target', так как это лишнее поле для воркера,
        # которое вызывает ошибку валидации "Input should be a valid string".
        worker_payload = {
            "cmd": cmd_str,
            "args": real_args
        }

        # Логика Routing
        target_id = self._resolve_camera_id(target_str)

        if target_id is not None:
            # Адресная отправка
            self._send_to_queue(target_id, worker_payload)
        else:
            # Broadcast (если target="calibration_tool" или "broadcast")
            # Отправляем всем зарегистрированным камерам
            if len(self._command_queues) > 0:
                for cid in self._command_queues:
                    self._send_to_queue(cid, worker_payload)
            else:
                pass  # Нет активных камер

    def _resolve_camera_id(self, target: str) -> Optional[int]:
        if target.startswith("cam_") or target.startswith("camera_"):
            try:
                return int(target.split("_")[1])
            except (IndexError, ValueError):
                pass
        return None

    def _send_to_queue(self, cam_id: int, payload: Dict):
        if cam_id in self._command_queues:
            try:
                self._command_queues[cam_id].put(payload, timeout=0.1)
            except queue.Full:
                logger.warning(f"⚠️ Queue full for Cam-{cam_id}")