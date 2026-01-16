# src/plugins/fps_meter.py
import time
from src.core.pipeline import PipelineStage, FrameContext


class FPSMeterPlugin(PipelineStage):
    def __init__(self):
        super().__init__(name="fps_meter")
        self.last_time = time.time()
        self.frames = 0
        self.fps = 0.0

    def process(self, ctx: FrameContext):
        self.frames += 1
        now = time.time()
        delta = now - self.last_time

        if delta >= 1.0:
            self.fps = self.frames / delta
            self.frames = 0
            self.last_time = now
            ctx.ui.update_widget("fps_real", "Real FPS", f"{self.fps:.1f}", "text")

        # [FIX] Исправленный вызов
        ctx.set_data("fps_meter", "fps", self.fps)