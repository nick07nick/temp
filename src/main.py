# src/main.py
import multiprocessing
import time
import sys
from loguru import logger

# Проверяем структуру проекта
try:
    # Важно: SharedMemoryManager теперь использует новую логику Ring Buffer
    from src.core.shared_memory import SharedMemoryManager
    from src.core.event_bus import EventBus
    from src.core.camera_worker import CameraWorker
    from src.api.server import run_server
    from src.core.config import settings
except ImportError as e:
    logger.critical(f"Import Error: {e}. Check PYTHONPATH.")
    sys.exit(1)


def main():
    # Настройка логов
    logger.add("logs/bikefit_{time}.log", rotation="10 MB")
    logger.info("Starting BikeFit Motion System v2.1 (RingBuffer)...")

    # 1. Инициализация Шины Событий
    bus = EventBus()
    logger.info("Event Bus initialized.")

    # 2. Выделение Shared Memory (Ring Buffer)
    try:
        # Мы создаем память. Менеджер внутри посчитает:
        # Header + (SlotSize * capacity)
        shm_manager = SharedMemoryManager(
            name=settings.SHM_CAMERA_BUFFER_NAME,
            shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
            dtype="uint8",
            capacity=150,  # <--- ВАЖНО: 3 слота буферизации
            create=True  # Флаг создания (мы Master)
        )
        # Входим в контекст (выделяем память и инициализируем заголовок кольца)
        shm_manager.__enter__()

        # Получаем конфиг для передачи в дочерние процессы
        shm_config = shm_manager.get_config()

        # Можно добавить в лог реальный размер
        logger.info(f"Shared Memory allocated: {shm_manager.name} | Total Size: {shm_manager.size} bytes")

    except Exception as e:
        logger.critical(f"Failed to allocate shared memory: {e}")
        return

    # 3. Запуск Процессов
    processes = []

    # --- A. Camera Worker (Writer + Processor) ---
    cam_worker = CameraWorker(
        camera_id=settings.CAMERA_INDEX,
        bus=bus,
        shm_config=shm_config
    )
    cam_worker.start()
    processes.append(cam_worker.process)

    # --- B. API Server (Reader) ---
    server_process = multiprocessing.Process(
        target=run_server,
        args=(bus, shm_config),
        name="APIServer",
        daemon=True
    )
    server_process.start()
    processes.append(server_process)

    logger.info(f"System Running. Active processes: {[p.name for p in processes]}")

    # 4. Watchdog Loop
    try:
        while True:
            time.sleep(1)
            # Проверяем здоровье процессов
            for p in processes:
                if p and not p.is_alive():
                    logger.critical(f"🚨 Process {p.name} DIED! System unstable.")
                    raise KeyboardInterrupt

    except KeyboardInterrupt:
        logger.warning("Shutting down system...")
    finally:
        # Graceful Shutdown
        logger.info("Terminating processes...")

        if 'cam_worker' in locals():
            cam_worker.stop()

        for p in processes:
            if p and p.is_alive():
                p.terminate()
                p.join()

        # Удаляем Shared Memory
        if 'shm_manager' in locals():
            shm_manager.unlink()  # Удаляем файл из /dev/shm
            shm_manager.close()

        logger.success("System stopped cleanly.")


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    main()