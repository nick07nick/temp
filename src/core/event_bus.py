# src/core/event_bus.py
import multiprocessing
import queue
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("BikeFit.EventBus")

class EventBus:
    """
    Межпроцессная шина событий.
    Использует multiprocessing.Queue для передачи данных между Core, API и Workers.
    """
    def __init__(self):
        # Очередь для команд от API к ядру/камерам
        self._command_queue = multiprocessing.Queue()
        # Очередь для событий от ядра к API (логи, статусы)
        self._event_queue = multiprocessing.Queue()
        # Очередь для высокочастотного стрима данных (точки для фронта)
        self._stream_queue = multiprocessing.Queue(maxsize=600) # Dropping old frames if full

    def publish(self, channel: str, data: Any):
        """Универсальный метод отправки (совместимость)"""
        if channel == "stream_data":
            self.publish_stream_data(data)
        elif channel == "command":
            if isinstance(data, dict) and "target" in data:
                self.send_command(data["target"], data.get("cmd", ""), data.get("args"))
        else:
            # Прочие события в event_queue
            try:
                self._event_queue.put_nowait({"channel": channel, "data": data})
            except queue.Full:
                pass

    # --- Stream Data (High Frequency) ---
    def publish_stream_data(self, data: Dict):
        """Отправка координат и статуса на фронтенд (90 FPS)"""
        try:
            # Если очередь полна, выкидываем старое, чтобы не было лага
            if self._stream_queue.full():
                try:
                    self._stream_queue.get_nowait()
                except queue.Empty:
                    pass
            self._stream_queue.put_nowait(data)
        except Exception:
            pass

    def get_stream_data(self) -> Optional[Dict]:
        """Чтение данных для WebSocket (вызывается в API)"""
        try:
            return self._stream_queue.get_nowait()
        except queue.Empty:
            return None

    # --- Commands ---
    def send_command(self, target: str, cmd: str, args: Any = None):
        """Отправка команды (например, set_exposure)"""
        payload = {"target": target, "cmd": cmd, "args": args}
        self._command_queue.put(payload)
        logger.debug(f"Cmd sent: {payload}")

    def get_command(self) -> Optional[Dict]:
        """Получение команды (вызывается в Worker/Core)"""
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def send_plugin_command(self, plugin_id: str, cmd: str, args: Any = None):
        """
        Отправка команды конкретному плагину.
        Processor поймает это сообщение и передаст в PluginManager.
        """
        message = {
            "type": "plugin_command",
            "target": plugin_id,
            "cmd": cmd,
            "args": args
        }
        self._command_queue.put(message)
        # logger.debug(f"Plugin Cmd -> {plugin_id}: {cmd}")