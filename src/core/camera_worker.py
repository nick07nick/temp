# src/core/camera_worker.py
import time
import logging
import setproctitle  # Нужно добавить в requirements.txt
from multiprocessing import Process, Event
from src.core.interfaces import ICamera
from src.core.shared_memory import SharedMemoryManager
from src.core.models import SharedMemoryConfig, FrameMetadata


# Настройка логгера для отдельного процесса
def setup_worker_logging(worker_name: str):
    logging.basicConfig(
        level=logging.DEBUG,
        format=f"%(asctime)s | {worker_name} | %(levelname)s | %(message)s"
    )


def camera_worker_loop(
        camera_factory_func,  # Функция, создающая инстанс ICamera
        shm_config: SharedMemoryConfig,
        stop_event: Event,
        camera_id: int
):
    """
    Главный цикл процесса захвата видео.
    Изолирован от основного процесса.
    """
    proc_name = f"BikeFit-Cam-{camera_id}"
    setproctitle.setproctitle(proc_name)
    setup_worker_logging(proc_name)
    logger = logging.getLogger(proc_name)

    logger.info("Worker started. Initializing resources...")

    camera: ICamera = None

    try:
        # 1. Подключаемся к Shared Memory (она уже создана Main процессом)
        with SharedMemoryManager(shm_config, create=False) as shm:

            # 2. Инициализируем камеру
            camera = camera_factory_func()
            camera.connect()

            w, h = camera.get_resolution()
            if w != shm_config.width or h != shm_config.height:
                logger.error(f"Resolution mismatch! Cam: {w}x{h}, SHM: {shm_config.width}x{shm_config.height}")
                return

            frame_count = 0
            start_time = time.time()

            logger.info("Entering capture loop...")

            # 3. Бесконечный цикл захвата
            while not stop_event.is_set():
                # Пишем прямо в память (Zero-Copy)
                success = camera.capture_to_buffer(shm.buffer)

                if success:
                    frame_count += 1
                    # Здесь мы должны отправить уведомление (Metadata) в очередь,
                    # что кадр готов. Пока просто логируем раз в секунду.

                    if frame_count % 30 == 0:
                        fps = frame_count / (time.time() - start_time)
                        logger.debug(f"Streaming Active. FPS: {fps:.2f}")

    except Exception as e:
        logger.critical(f"Worker crashed: {e}", exc_info=True)
    finally:
        if camera:
            camera.release()
        logger.info("Worker stopped.")