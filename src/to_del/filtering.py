# src/core/pipeline/filtering.py
from typing import Dict
from loguru import logger  # <--- ДОБАВИЛ ИМПОРТ

from src.core.pipeline import PipelineStage, FrameContext
from src.stages.filters import PointSmoother


class SmoothingStage(BaseStage):
    def __init__(self):
        self.filters: Dict[int, PointSmoother] = {}

    def process(self, ctx: ProcessingContext) -> None:
        current_time = ctx.timestamp

        # --- DEBUG LOG ---
        # ids_input = [p.id for p in ctx.points]
        # logger.debug(f"[Filter] Input IDs: {ids_input}")
        # -----------------

        for p in ctx.points:
            safe_id = p.id if p.id is not None else -1

            # Если ID нет, мы увидим это в логах
            # if p.id is None:
            #     logger.warning(f"[Filter] Point has NO ID! Coords: {p.x:.1f}, {p.y:.1f}")

            if safe_id not in self.filters:
                self.filters[safe_id] = PointSmoother(min_cutoff=0.5, beta=0.05)

            sx, sy = self.filters[safe_id].filter(p.x, p.y, current_time)

            p.x = sx
            p.y = sy