# src/core/event_bus.py
import multiprocessing
import queue
import logging
from typing import Optional, Any

logger = logging.getLogger("BikeFit.Bus")

class EventBus:
    """
    Шина для передачи сообщений от Core (тяжелые процессы) к API (легкий процесс).
    """
    def __init__(self):
        # Очередь для координат (только легкие данные!)
        self._stream_queue = multiprocessing.Queue(maxsize=100)
        # Очередь для команд управления (API -> Core)
        self._command_queue = multiprocessing.Queue(maxsize=10)

    def publish_stream_data(self, data: Any):
        try:
            self._stream_queue.put_nowait(data)
        except queue.Full:
            pass

    def get_stream_data(self) -> Optional[Any]:
        try:
            return self._stream_queue.get_nowait()
        except queue.Empty:
            return None

    def send_command(self, cmd: str, payload: Any = None):
        try:
            self._command_queue.put((cmd, payload))
        except queue.Full:
            logger.error("Command queue full!")

    def get_command(self) -> Optional[tuple]:
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None