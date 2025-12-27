# src/main.py
import multiprocessing
import uvicorn
import logging
import sys
import os
import signal

from src.core.event_bus import EventBus
from src.core.system import core_process_loop
from src.api.server import create_app
from src.core.storage import CalibrationStorage
from src.core.models import CameraIntrinsics, WorkspaceProfile
from src.core.security import DevCryptoProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BikeFit.Boot")


def init_defaults_if_needed():
    """Создает дефолтную БД для первого запуска."""
    if not os.path.exists("bikefit_db.json"):
        logger.info("Seeding default DB...")
        storage = CalibrationStorage("bikefit_db.json")

        # Линзы
        mtx = [[1000.0, 0, 960.0], [0, 1000.0, 540.0], [0, 0, 1]]
        storage.add_intrinsic(CameraIntrinsics(name="Std_Lens", camera_id=0, camera_matrix=mtx, dist_coeffs=[0] * 5))

        # Воркспейсы
        ws1 = WorkspaceProfile(name="Trainer_1", camera_mapping={0: "Std_Lens", 1: "Std_Lens", 2: "Std_Lens"},
                               scale_factor=1.0)
        ws2 = WorkspaceProfile(name="Trainer_2", camera_mapping={0: "Std_Lens", 1: "Std_Lens", 2: "Std_Lens"},
                               scale_factor=1.5)

        storage.add_workspace(ws1)
        storage.add_workspace(ws2)


def main():
    # 1. Security Check
    crypto = DevCryptoProvider(simulation_mode=True)
    if not crypto.verify_license():
        sys.exit(1)

    init_defaults_if_needed()

    # 2. Infrastructure
    event_bus = EventBus()
    storage = CalibrationStorage("bikefit_db.json")

    # 3. Start Core Process (Logic + Hardware)
    # ВАЖНО: daemon=False, иначе он не сможет создавать свои подпроцессы (CameraWorkers)
    core_process = multiprocessing.Process(
        target=core_process_loop,
        args=(event_bus,),
        name="BikeFit-Core",
        daemon=False
    )
    core_process.start()
    logger.info(f"Core Process started PID: {core_process.pid}")

    # Обработчик для корректного завершения
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received...")
        if core_process.is_alive():
            logger.info("Terminating Core Process...")
            core_process.terminate()
            core_process.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 4. Start API Server (in Main Thread)
    app = create_app(event_bus, storage)

    logger.info("Starting API Server on http://0.0.0.0:8000")
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup if uvicorn stops
        if core_process.is_alive():
            core_process.terminate()
            core_process.join()


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    main()