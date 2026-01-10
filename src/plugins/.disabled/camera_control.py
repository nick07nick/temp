# src/plugins/camera_control.py
from src.core.pipeline import PipelineStage, FrameContext


class CameraControlPlugin(PipelineStage):
    """
    Legacy plugin.
    В v3.0 управление камерой происходит через ctx.config, который обновляется автоматически.
    """

    def __init__(self):
        super().__init__(name="camera_control")

    def process(self, ctx: FrameContext):
        # Просто логируем текущие параметры раз в 5 сек для отладки, или ничего не делаем
        pass

    def handle_command(self, cmd, args):
        pass