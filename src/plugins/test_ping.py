import cv2
import numpy as np
import base64
import time
from src.core.pipeline import PipelineStage, FrameContext
from loguru import logger


class TestPingPlugin(PipelineStage):
    def __init__(self):
        super().__init__("test_ping")  # Имя плагина для команд
        self.counter = 0
        self.is_green = False

    def process(self, ctx: FrameContext):
        # 1. Генерируем картинку 100x100 (Красный или Зеленый)
        color = (0, 255, 0) if self.is_green else (0, 0, 255)  # BGR
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        img[:] = color

        # Пишем текст прямо на картинке
        cv2.putText(img, str(self.counter), (50, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)

        # 2. Кодируем в Base64
        _, buffer = cv2.imencode('.jpg', img)
        img_b64 = base64.b64encode(buffer).decode('utf-8')
        full_src = f"data:image/jpeg;base64,{img_b64}"

        # 3. Отправляем во фронт
        payload = {
            "server_time": time.time(),
            "count_val": self.counter,
            "image_src": full_src
        }

        # ID виджета = "test_widget"
        ctx.ui.update_widget("test_widget", "PingPong Test", payload, "custom")

    def handle_command(self, cmd, args):
        logger.info(f"🏓 PING RECEIVED: {cmd}")
        if cmd == "click":
            self.counter += 1
            self.is_green = not self.is_green