import math
from typing import Dict, Any, List, Optional
from loguru import logger

from src.core.pipeline import PipelineStage, FrameContext
from src.data.models import Point2D


class GeometryManager(PipelineStage):
    """
    Плагин для геометрических измерений.
    Управляет инструментами (Angles, Distances), созданными пользователем.
    Использует Undistorted координаты (ux, uy) для точности.
    """

    def __init__(self):
        super().__init__(name="geometry_manager")
        # Хранилище инструментов: { "tool_id": { type: 'angle', points: [1, 2, 3], color: '...' } }
        self.tools: Dict[str, Dict[str, Any]] = {}

    def process(self, ctx: FrameContext):
        # 1. Получаем точки (уже с ID и ux/uy от предыдущих стадий)
        points: List[Point2D] = ctx.get_data("vision", "keypoints", [])
        if not points:
            return

        # Для быстрого поиска точки по ID превращаем список в dict
        # points_map = { 1: Point2D(...), 5: Point2D(...) }
        points_map = {p.id: p for p in points if p.id is not None}

        results = {}

        # 2. Проходим по всем активным инструментам
        for tool_id, tool in self.tools.items():
            t_type = tool.get("type")
            t_point_ids = tool.get("points", [])

            # Проверяем, все ли точки инструмента сейчас видны в кадре
            if not all(pid in points_map for pid in t_point_ids):
                continue

            # Собираем объекты точек
            pts = [points_map[pid] for pid in t_point_ids]

            # Считаем значение
            value = 0.0
            label_pos = (0, 0)

            if t_type == "distance" and len(pts) == 2:
                value = self._calc_distance(pts[0], pts[1])
                # Позиция текста - середина линии
                label_pos = ((pts[0].x + pts[1].x) / 2, (pts[0].y + pts[1].y) / 2)

            elif t_type == "angle" and len(pts) == 3:
                # pts[0]=A, pts[1]=Vertex(B), pts[2]=C
                value = self._calc_angle(pts[0], pts[1], pts[2])
                label_pos = (pts[1].x, pts[1].y - 20)  # Чуть выше вершины

            # 3. Формируем результат для фронтенда
            results[tool_id] = {
                "id": tool_id,
                "type": t_type,
                "value": round(value, 1),
                "points": t_point_ids,  # Возвращаем ID точек, чтобы фронт знал кого соединять
                "color": tool.get("color", "#ffffff"),
                "label_x": label_pos[0],
                "label_y": label_pos[1]
            }

        # 4. Сохраняем в контекст (VideoPlayer это заберет)
        ctx.set_data("geometry", "tools", results)

        # Также отправляем общий results в корень (для совместимости с VideoPlayer.jsx)
        # Он ищет framePlugins = sysState.results || {}
        if not ctx.has_data("results", "geometry"):
            ctx.set_data("results", "geometry", results)

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        """Обработка команд от VideoPlayer.jsx"""

        if cmd == "cmd_add_tool":
            # args: { id: "tool_123", type: "angle", points: [1, 2, 3], color: "..." }
            t_id = args.get("id")
            if t_id:
                self.tools[t_id] = args
                logger.info(f"📐 Tool added: {t_id} ({args.get('type')})")
                # Можно уведомить UI, но это лишний шум, т.к. юзер сам добавил

        elif cmd == "cmd_remove_tool":
            t_id = args.get("id")
            if t_id in self.tools:
                del self.tools[t_id]
                logger.info(f"🗑️ Tool removed: {t_id}")

        elif cmd == "cmd_clear_all":
            self.tools.clear()
            logger.info("🗑️ All tools cleared")

    # === MATH HELPERS ===

    def _get_coords(self, p: Point2D):
        """Возвращает (ux, uy) если есть, иначе (x, y)"""
        if p.ux is not None and p.uy is not None:
            return p.ux, p.uy
        return p.x, p.y

    def _calc_distance(self, p1: Point2D, p2: Point2D) -> float:
        x1, y1 = self._get_coords(p1)
        x2, y2 = self._get_coords(p2)
        # Пока считаем в пикселях.
        # Если будет CalibrationWorld, тут можно домножить на scale (px -> mm)
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def _calc_angle(self, p1: Point2D, vertex: Point2D, p2: Point2D) -> float:
        """Считает угол p1-vertex-p2 в градусах (0..180)"""
        ax, ay = self._get_coords(p1)
        bx, by = self._get_coords(vertex)  # Вершина
        cx, cy = self._get_coords(p2)

        # Вектора BA и BC
        ba_x, ba_y = ax - bx, ay - by
        bc_x, bc_y = cx - bx, cy - by

        # Скалярное произведение и модули
        dot_product = ba_x * bc_x + ba_y * bc_y
        mag_ba = math.sqrt(ba_x ** 2 + ba_y ** 2)
        mag_bc = math.sqrt(bc_x ** 2 + bc_y ** 2)

        if mag_ba * mag_bc == 0:
            return 0.0

        # Защита от floating point errors (cos должен быть [-1, 1])
        cos_angle = max(-1.0, min(1.0, dot_product / (mag_ba * mag_bc)))
        angle_rad = math.acos(cos_angle)

        return math.degrees(angle_rad)