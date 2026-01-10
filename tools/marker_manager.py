# src/plugins/marker_manager.py
from typing import Dict, Any
from loguru import logger
from src.core.pipeline import PipelineStage, FrameContext


class MarkerManager(PipelineStage):
    def __init__(self):
        super().__init__("marker_manager")
        self._subscribed = False

        # Начальное состояние маркеров (пример для Bike Fit)
        # В реальной системе это может загружаться из конфига/базы
        self.markers: Dict[str, Any] = {
            "shoulder": {"x": 400, "y": 300, "label": "Плечо", "color": "#FF0000"},
            "hip": {"x": 400, "y": 600, "label": "Таз", "color": "#00FF00"},
            "knee": {"x": 400, "y": 800, "label": "Колено", "color": "#0000FF"},
            "ankle": {"x": 400, "y": 950, "label": "Лодыжка", "color": "#FFFF00"},
        }

    def _handle_update_marker(self, event_data: Dict[str, Any]):
        """Обработчик события обновления маркера с фронтенда"""
        try:
            m_id = event_data.get("id")
            data = event_data.get("data", {})

            if m_id and m_id in self.markers:
                # Обновляем координаты или свойства
                self.markers[m_id].update(data)
                logger.info(f"Marker '{m_id}' updated: {data}")
            else:
                logger.warning(f"Attempt to update unknown marker: {m_id}")
        except Exception as e:
            logger.error(f"Error updating marker: {e}")

    def process(self, ctx: FrameContext):
        # 1. Ленивая подписка на EventBus (один раз при первом кадре)
        if ctx.bus and not self._subscribed:
            # Слушаем команду 'cmd_update_marker', которую шлет фронт
            ctx.bus.subscribe("cmd_update_marker", self._handle_update_marker)
            self._subscribed = True
            logger.info("MarkerManager subscribed to EventBus commands")

        # 2. Публикуем данные для фронтенда через официальный API

        # А) Основные данные плагина (координаты для отрисовки)
        ctx.set_data("marker_manager", {
            "markers": self.markers
        })

        # Б) Метаданные для контекстного меню (названия, лейблы)
        # Кладем в отдельный ключ, так как фронт ищет их там (судя по твоему коду VideoPlayer)
        meta_info = {
            k: {"id": k, "label": v.get("label", k)}
            for k, v in self.markers.items()
        }
        ctx.set_data("marker_meta", meta_info)

        # 3. (Опционально) Пример взаимодействия с UI - выводим кол-во маркеров в виджет
        # ctx.ui.update_widget("markers_count", "Markers", len(self.markers))