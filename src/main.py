# src/main.py
import multiprocessing
import threading
import time
import sys
from loguru import logger

try:
    from src.core.config import settings
    from src.core.event_bus import EventBus
    from src.core.orchestrator import ProcessorOrchestrator
    from src.api.server import run_server
    from src.data.models import SharedMemoryConfig
except ImportError as e:
    logger.critical(f"Import Error: {e}. Check PYTHONPATH.")
    sys.exit(1)


def main():
    logger.add("logs/bikefit_{time}.log", rotation="10 MB")
    logger.info(f"🚀 Starting BikeFit Motion System v3.0 (Orchestrated)...")

    # 1. Manager для общей памяти (IPC)
    manager = multiprocessing.Manager()

    # 2. Event Bus (без сохранения manager внутри)
    bus = EventBus(manager)
    logger.info("✅ Event Bus initialized (Shared Memory Mode).")

    # 3. Шаблон памяти
    shm_template = SharedMemoryConfig(
        name="shm_cam_0",
        size=0,
        shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
        dtype="uint8"
    )

    # 4. Оркестратор
    # [FIX] Передаем manager сюда, чтобы он мог создавать очереди
    orchestrator = ProcessorOrchestrator(bus, manager)
    orchestrator.start()

    # 5. API Server (Thread)
    server_thread = threading.Thread(
        target=run_server,
        args=(bus, shm_template),
        name="APIServer",
        daemon=True
    )
    server_thread.start()

    logger.success("✅ System is UP. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
            if not server_thread.is_alive():
                logger.critical("🚨 API Server died! Restarting system...")
                raise KeyboardInterrupt

    except KeyboardInterrupt:
        logger.warning("\n🛑 Shutting down system...")
    finally:
        if 'orchestrator' in locals():
            orchestrator.stop()
        logger.success("👋 System stopped cleanly.")


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    main()