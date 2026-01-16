# src/plugins/geometry_manager.py
import math
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
import numpy as np

from src.core.pipeline import PipelineStage, FrameContext
from src.data.models import Point2D


class GeometryManager(PipelineStage):
    def __init__(self):
        super().__init__(name="geometry_manager")
        # id -> { type, points: [], color, current, min, max, unit }
        self.tools: Dict[str, Dict[str, Any]] = {}

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        t_id = args.get("id")

        if cmd == "cmd_add_tool" and t_id:
            self.tools[t_id] = {
                "type": args.get("type"),
                "points": args.get("points", []),
                "color": args.get("color", "#fbbf24"),
                "min": float('inf'), "max": float('-inf'),
                "current": 0.0,
                "unit": "px"  # Значение по умолчанию
            }
            logger.info(f"📏 Tool added: {t_id}")

        elif cmd == "cmd_remove_tool":
            if t_id and t_id in self.tools:
                del self.tools[t_id]
                logger.info(f"🗑️ Tool removed: {t_id}")

        elif cmd == "cmd_remove_by_point":
            pid = args.get("point_id")
            to_del = [k for k, v in self.tools.items() if pid in v["points"]]
            for k in to_del: del self.tools[k]
            if to_del: logger.info(f"🗑️ Removed tools for point {pid}")

        elif cmd == "cmd_clear_all":
            self.tools.clear()

    def process(self, ctx: FrameContext):
        # 1. Получаем объекты Point2D (они содержат x, y, ux, uy, wx, wy)
        points: List[Point2D] = ctx.get_data("vision", "keypoints", [])
        points_map = {p.id: p for p in points if p.id is not None}

        # 2. Расчет геометрии
        for tool in self.tools.values():
            pts_ids = tool["points"]

            # Проверяем наличие всех точек
            current_points = []
            for pid in pts_ids:
                if pid in points_map:
                    current_points.append(points_map[pid])
                else:
                    break

            if len(current_points) != len(pts_ids):
                continue  # Не все точки видны -> пропускаем расчет

            val = 0.0
            unit = "px"

            # --- ЛОГИКА ДЛЯ ДИСТАНЦИИ ---
            if tool["type"] == "distance" and len(current_points) == 2:
                p1, p2 = current_points[0], current_points[1]

                # Приоритет 1: Мировые координаты (Metric)
                if p1.wx is not None and p2.wx is not None:
                    val = math.sqrt((p1.wx - p2.wx) ** 2 + (p1.wy - p2.wy) ** 2)
                    # Обычно wx/wy хранятся в мм (если калибровались по доске с размером в мм)
                    # Если значение маленькое (< 3.0), возможно это метры, тогда умножаем
                    unit = "mm"

                    # Приоритет 2: Исправленные пиксели (Undistorted)
                elif p1.ux is not None and p2.ux is not None:
                    val = math.sqrt((p1.ux - p2.ux) ** 2 + (p1.uy - p2.uy) ** 2)
                    unit = "px (undist)"

                # Приоритет 3: Сырые пиксели (Raw)
                else:
                    val = math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
                    unit = "px"

            # --- ЛОГИКА ДЛЯ УГЛОВ ---
            elif tool["type"] == "angle" and len(current_points) == 3:
                p1, vertex, p2 = current_points[0], current_points[1], current_points[2]

                # Для углов важнее всего геометрия (Undistorted или World).
                # Raw pixels могут дать ошибку на краях кадра из-за дисторсии линзы.

                coords_1 = self._get_angle_coords(p1)
                coords_v = self._get_angle_coords(vertex)
                coords_2 = self._get_angle_coords(p2)

                if coords_1 and coords_v and coords_2:
                    val = self._calc_angle(coords_1, coords_v, coords_2)

                unit = "deg"

            # Обновляем состояние инструмента
            tool["current"] = val
            tool["unit"] = unit

            if val < tool["min"]: tool["min"] = val
            if val > tool["max"]: tool["max"] = val

        # 3. Публикация данных
        # Overlay для VideoPlayer (чтобы рисовать линии поверх видео)
        ctx.set_data("overlay", "geometry", self.tools)

        # Данные для UI виджета (список значений)
        ctx.ui.update_widget("geometry_control", "Geometry Tools", {"tools": self.tools}, "custom")

    def _get_angle_coords(self, p: Point2D) -> Optional[Tuple[float, float]]:
        """Выбирает лучшие координаты для угловых расчетов"""
        # Лучше всего - Undistorted (ux, uy), так как они выпрямляют линии
        if p.ux is not None and p.uy is not None:
            return (p.ux, p.uy)
        # Если нет, сойдут и мировые (они линейно зависят от undistorted)
        if p.wx is not None and p.wy is not None:
            return (p.wx, p.wy)
        # В крайнем случае - сырые
        return (p.x, p.y)

    def _calc_angle(self, a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]):
        """Считает угол ABC (вершина в B)"""
        ba = np.array([a[0] - b[0], a[1] - b[1]])
        bc = np.array([c[0] - b[0], c[1] - b[1]])

        norm_ba = np.linalg.norm(ba)
        norm_bc = np.linalg.norm(bc)

        if norm_ba < 1e-6 or norm_bc < 1e-6:
            return 0.0

        cosine = np.dot(ba, bc) / (norm_ba * norm_bc)
        angle = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        return angle