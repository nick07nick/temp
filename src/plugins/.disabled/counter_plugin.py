import time
from typing import Dict, Any
from src.core.pipeline import PipelineStage, FrameContext
from loguru import logger


class CounterPlugin(PipelineStage):
    def __init__(self):
        super().__init__("counter")
        self.count = 1
        self.commands_received = 0
        logger.info(f"🔢 [COUNTER] CounterPlugin initialized. Initial count: {self.count}")

    def process(self, ctx: FrameContext):
        """Вызывается каждый кадр"""
        # Всегда отправляем текущее значение
        ctx.set_data("counter", "value", self.count)

        # Логируем каждые 30 кадров, чтобы не заспамить
        frame_id = getattr(ctx, 'frame_id', 0)
        if frame_id % 30 == 0:
            logger.debug(f"🔄 [COUNTER] Frame {frame_id}: counter = {self.count}")

    def handle_command(self, cmd: str, args: Dict[str, Any]):
        """Обработка команд от фронтенда"""
        self.commands_received += 1

        logger.info(f"📨 [COUNTER] Command received #{self.commands_received}: cmd='{cmd}', args={args}")

        old_value = self.count

        if cmd == "increment":
            self.count += 1
            logger.success(f"➕ [COUNTER] Incremented: {old_value} → {self.count}")

        elif cmd == "reset":
            self.count = 0
            logger.warning(f"🔄 [COUNTER] Reset: {old_value} → {self.count}")

        elif cmd == "set_value":
            new_value = args.get("value")
            if new_value is not None:
                try:
                    self.count = int(new_value)
                    logger.info(f"⚙️ [COUNTER] Set: {old_value} → {self.count}")
                except (ValueError, TypeError) as e:
                    logger.error(f"❌ [COUNTER] Invalid value: {new_value}, error: {e}")

        else:
            logger.warning(f"⚠️ [COUNTER] Unknown command: {cmd}")


def create_plugin():
    return CounterPlugin()