# src/plugins/test_multicam.py
import time
from src.core.pipeline import PipelineStage, FrameContext


class TestMultiCamPlugin(PipelineStage):
    def __init__(self):
        super().__init__("test_multicam")  # Имя для команд
        self.frame_counter = 0

    def process(self, ctx: FrameContext):
        # Инкремент счетчика
        self.frame_counter += 1

        # Троттлинг (шлем данные раз в 30 кадров, чтобы не спамить)
        if self.frame_counter % 30 != 0:
            return

        # Формируем простейший пакет
        payload = {
            "ts": time.time(),
            "worker_cam_id": ctx.camera_id,  # <--- Самое важное: ID из контекста
            "counter": self.frame_counter
        }

        # Отправляем в виджет.
        # Внимание: благодаря нашему фиксу в pipeline.py,
        # сюда автоматически добавится поле "camera_id": ctx.camera_id
        ctx.ui.update_widget("test_multicam_widget", "MultiCam Debug", payload, "custom")

    def handle_command(self, cmd, args):
        pass