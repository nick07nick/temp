# src/main.py
import multiprocessing
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
    # 1. Настройка логов
    logger.add("logs/bikefit_{time}.log", rotation="10 MB")
    logger.info(f"🚀 Starting BikeFit Motion System v3.0 (Orchestrated)...")

    # 2. Инициализация Шины Событий
    bus = EventBus()
    logger.info("✅ Event Bus initialized.")

    # 3. Подготовка шаблона памяти для API Сервера
    # [FIX] Важно: имя должно совпадать с тем, что генерирует Orchestrator (shm_cam_X)
    # Для первой камеры (ID 0) это shm_cam_0
    shm_template = SharedMemoryConfig(
        name="shm_cam_0",  # <--- БЫЛО settings.SHM_CAMERA_BUFFER_NAME, СТАЛО ЯВНОЕ ИМЯ
        size=0,
        shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
        dtype="uint8"
    )

    processes = []

    # 4. Запуск Оркестратора
    orchestrator = ProcessorOrchestrator(bus)
    orchestrator.start()

    # 5. Запуск API Server
    server_process = multiprocessing.Process(
        target=run_server,
        args=(bus, shm_template),
        name="APIServer",
        daemon=True
    )
    server_process.start()
    processes.append(server_process)

    logger.success("✅ System is UP. Press Ctrl+C to stop.")

    # 6. Main Loop
    try:
        while True:
            time.sleep(1)
            if not server_process.is_alive():
                logger.critical("🚨 API Server died! Restarting system...")
                raise KeyboardInterrupt

    except KeyboardInterrupt:
        logger.warning("\n🛑 Shutting down system...")
    finally:
        if 'orchestrator' in locals():
            orchestrator.stop()

        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()

        logger.success("👋 System stopped cleanly.")


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    main()