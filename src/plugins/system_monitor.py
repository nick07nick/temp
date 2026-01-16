import os
import time
import psutil
from src.core.pipeline import PipelineStage, FrameContext


class SystemMonitorPlugin(PipelineStage):
    def __init__(self):
        super().__init__(name="sys_monitor")
        self._proc = psutil.Process(os.getpid())
        self.last_check = 0
        self.check_interval = 0.5  # Обновляем раз в 0.5 сек

        # Кэшируем значения, чтобы отправлять их в каждом кадре
        self.cached_cpu = 0.0
        self.cached_ram = 0

    def process(self, ctx: FrameContext):
        now = time.time()

        # Читаем тяжелые метрики только раз в интервал
        if now - self.last_check > self.check_interval:
            self.cached_cpu = self._proc.cpu_percent(interval=None)
            mem_info = self._proc.memory_info()
            self.cached_ram = int(mem_info.rss / 1024 / 1024)
            self.last_check = now

        # Пишем в контекст КАЖДЫЙ кадр (иначе график на фронте падает в 0)
        ctx.set_data("sys_load", "cpu", self.cached_cpu)
        ctx.set_data("sys_load", "ram", self.cached_ram)


def create_plugin():
    return SystemMonitorPlugin()