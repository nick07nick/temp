# src/core/event_bus.py
import queue
from typing import Any, Dict, Optional, Union
from loguru import logger


class EventBus:
    def __init__(self, manager):
        # Мы используем manager только при инициализации, но НЕ СОХРАНЯЕМ его в self

        # 1. Воркер -> Оркестратор
        self._upstream_queue = manager.Queue(maxsize=1000)

        # 2. Оркестратор -> API
        self._broadcast_queue = manager.Queue(maxsize=1000)

        # 3. Видеопоток
        self._stream_queue = manager.Queue(maxsize=10)

        # 4. Критические
        self._critical_queue = manager.Queue()

        # 5. Команды
        self._command_queues = manager.dict()

        # [FIX] УДАЛЕНО: self._manager = manager
        # Нельзя хранить ссылку на менеджер, иначе объект не сериализуется!

    def register_worker(self, camera_id: int, manager) -> Any:
        # [FIX] Принимаем manager снаружи
        q = manager.Queue(maxsize=100)
        self._command_queues[camera_id] = q
        logger.info(f"🔌 EventBus: Registered SHARED queue for Camera {camera_id}")
        return q

    # --- Methods for Workers ---
    def publish_stream(self, data: Dict[str, Any]):
        try:
            self._stream_queue.put_nowait(data)
        except queue.Full:
            try:
                self._stream_queue.get_nowait()
            except:
                pass
            try:
                self._stream_queue.put_nowait(data)
            except:
                pass

    def publish_critical(self, data: Dict[str, Any]):
        self._critical_queue.put(data)

    def publish_event(self, event_type: str, payload: Dict[str, Any]):
        msg = {"type": event_type, "payload": payload}
        if event_type in ["heartbeat", "error", "worker_status"]:
            try:
                self._upstream_queue.put(msg, timeout=0.1)
            except queue.Full:
                pass

    def publish_to_api(self, event_type: str, payload: Dict[str, Any]):
        msg = {"type": event_type, "payload": payload}
        try:
            self._broadcast_queue.put(msg, timeout=0.1)
        except queue.Full:
            pass

    # --- Methods for Orchestrator/Server ---
    def get_updates(self) -> Optional[Dict]:
        try:
            return self._upstream_queue.get_nowait()
        except queue.Empty:
            return None

    def get_broadcast_data(self) -> Optional[Dict]:
        try:
            return self._broadcast_queue.get_nowait()
        except queue.Empty:
            return None

    def get_stream_data(self) -> Optional[Dict]:
        try:
            return self._stream_queue.get_nowait()
        except queue.Empty:
            return None

    def get_critical_data(self) -> Optional[Dict]:
        try:
            return self._critical_queue.get_nowait()
        except queue.Empty:
            return None

    def send_command(self, target_or_id: Union[str, int], cmd_or_payload: Union[str, Dict],
                     args: Optional[Dict] = None):
        if isinstance(target_or_id, int) and isinstance(cmd_or_payload, dict):
            self._send_to_queue(target_or_id, cmd_or_payload)
            return

        target_str = str(target_or_id)
        worker_payload = {"cmd": str(cmd_or_payload), "args": args or {}}
        target_id = self._resolve_camera_id(target_str)

        if target_id is not None:
            self._send_to_queue(target_id, worker_payload)
        else:
            keys = self._command_queues.keys()
            for cid in keys:
                self._send_to_queue(cid, worker_payload)

    def _resolve_camera_id(self, target: str) -> Optional[int]:
        if target.startswith("cam_") or target.startswith("camera_"):
            try:
                return int(target.split("_")[1])
            except:
                pass
        try:
            return int(target)
        except:
            return None

    def _send_to_queue(self, cam_id: int, payload: Dict):
        if cam_id in self._command_queues:
            q = self._command_queues[cam_id]
            try:
                q.put(payload, timeout=0.1)
            except queue.Full:
                logger.warning(f"⚠️ Queue full for Cam-{cam_id}")