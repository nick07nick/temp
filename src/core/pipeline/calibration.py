from src.core.pipeline.base import BaseStage, ProcessingContext
from src.core.calibration import CalibrationManager

class CalibrationStage(BaseStage):
    def __init__(self, manager: CalibrationManager):
        self.manager = manager

    def process(self, ctx: ProcessingContext) -> None:
        if not self.manager or not ctx.points:
            return

        if ctx.camera_id in self.manager._active_intrinsics:
            ctx.points = self.manager.undistort_points(
                ctx.camera_id, ctx.points
            )
            ctx.is_calibrated = True