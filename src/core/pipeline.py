# src/core/pipeline.py

from typing import Any, Dict, List, Union, Optional
from abc import ABC, abstractmethod
import time
from loguru import logger

from src.data.schemas import (
    ModuleError, CameraConfig,
    UINotification, UIWidgetUpdate, NotificationType, WidgetType
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.event_bus import EventBus


class UIContext:
    def __init__(self, camera_id: int = -1):
        self._notifications: List[UINotification] = []
        self._widgets: List[UIWidgetUpdate] = []
        self.camera_id = camera_id  # [NEW] ID камеры

    def notify(self, title: str, message: str, level: str = "info", duration: float = 3.0):
        try:
            n_type = NotificationType(level)
        except ValueError:
            n_type = NotificationType.INFO

        n = UINotification(
            id=f"{time.time()}", title=title, message=message, type=n_type, duration=duration
        )
        self._notifications.append(n)

    def update_widget(self, widget_id: str, title: str, data: Any, w_type: str = "text"):
        try:
            wt = WidgetType(w_type)
        except ValueError:
            wt = WidgetType.TEXT

        # [NEW] Авто-инъекция camera_id в данные виджета
        # Если data — это dict, добавляем поле camera_id.
        # Это позволит фронтенду фильтровать данные: if (data.camera_id !== selectedId) return;
        enriched_data = data
        if isinstance(data, dict):
            # Делаем копию, чтобы не мутировать исходный dict, если он используется где-то еще
            enriched_data = data.copy()
            if "camera_id" not in enriched_data:
                enriched_data["camera_id"] = self.camera_id

        w = UIWidgetUpdate(widget_id=widget_id, type=wt, title=title, data=enriched_data)
        self._widgets.append(w)

    def get_updates(self):
        return {"notifications": self._notifications, "widgets": self._widgets}


class FrameContext:
    def __init__(self, frame_ref: Any, frame_id: int, config: CameraConfig, bus: Optional['EventBus'] = None,
                 camera_id: int = -1):
        self.frame = frame_ref
        self.bus = bus
        self.frame_id = frame_id
        self.camera_id = camera_id  # [NEW]
        self.timestamp = time.perf_counter()
        self.config = config
        self.errors: List[ModuleError] = []
        self._store: Dict[str, Any] = {}

        # Передаем ID в UI контекст
        self.ui = UIContext(camera_id=camera_id)

    def set_data(self, namespace: str, key: str, value: Any):
        if namespace not in self._store:
            self._store[namespace] = {}
        self._store[namespace][key] = value

    def get_data(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._store.get(namespace, {}).get(key, default)

    def has_data(self, namespace: str, key: str) -> bool:
        return key in self._store.get(namespace, {})

    def add_error(self, source: str, message: str, severity: str = "error"):
        self.errors.append(ModuleError(
            source=source, message=message, severity=severity, timestamp=time.perf_counter()
        ))

    @property
    def data_snapshot(self) -> Dict[str, Any]:
        return self._store


class PipelineStage(ABC):
    """
    Базовый класс для всех стадий.
    Сделан устойчивым к разным вариантам инициализации (с именем или без).
    """

    def __init__(self, name: Optional[str] = None, **kwargs):
        # Если имя передали — берем его, иначе берем имя класса
        self.name = name or self.__class__.__name__
        self.camera_id = -1  # [NEW] Будет обновляться при первом вызове process

    def process(self, ctx: FrameContext):
        pass

    def run(self, ctx: FrameContext):
        # [NEW] Обновляем ID при каждом кадре (на случай смены конфига, хотя это редкость)
        # Это позволяет плагину знать свой ID в методе handle_command
        self.camera_id = ctx.camera_id
        self.process(ctx)

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        pass