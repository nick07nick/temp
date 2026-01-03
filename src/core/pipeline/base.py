from abc import ABC, abstractmethod
from src.core.pipeline.context import ProcessingContext

class BaseStage(ABC):
    @abstractmethod
    def process(self, ctx: ProcessingContext) -> None:
        """Обрабатывает контекст, изменяя ctx.points или ctx.meta"""
        pass

    def cleanup(self):
        """Освобождение ресурсов"""
        pass