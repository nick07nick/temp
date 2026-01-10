import os
import time
import psutil
from src.core.pipeline import PipelineStage, FrameContext


class SystemMonitorPlugin(PipelineStage):
    def __init__(self):
        super().__init__(name="sys_monitor")
        self._proc = psutil.Process(os.getpid())
        self.last_check = 0
        self.check_interval = 0.2

    def process(self, ctx: FrameContext):
        now = time.time()
        if now - self.last_check > self.check_interval:
            # Получаем метрики
            cpu_pct = self._proc.cpu_percent(interval=None)
            mem_info = self._proc.memory_info()
            ram_mb = mem_info.rss / 1024 / 1024

            # [FIX] Метод set_data требует 3 аргумента: (namespace, key, value)
            # Записываем данные по отдельности в пространство имен "sys_load"
            ctx.set_data("sys_load", "cpu", cpu_pct)
            ctx.set_data("sys_load", "ram", int(ram_mb))

            self.last_check = now


def create_plugin():
    return SystemMonitorPlugin()
