# src/plugins/demo_plugin.py
from typing import Any
from loguru import logger  # <--- LOGURU
from src.core import BaseStage, ProcessingContext


class DemoStatsPlugin(BaseStage):
    PLUGIN_ID = "demo_stats"

    def __init__(self):
        self.counter = 0
        logger.info("DemoStatsPlugin initialized!")

    def process(self, ctx: ProcessingContext) -> None:
        points_count = len(ctx.points)

        # Записываем в meta
        if "plugins" not in ctx.meta:
            ctx.meta["plugins"] = {}

        ctx.meta["plugins"][self.PLUGIN_ID] = {
            "msg": f"Hello from Python! Frame: {self.counter}",
            "points_seen": points_count
        }

        self.counter += 1

    def on_command(self, cmd: str, args: Any):
        if cmd == "reset_counter":
            logger.warning("DemoPlugin received RESET command!")
            self.counter = 0
        elif cmd == "ping":
            logger.info(f"DemoPlugin PING received: {args}")