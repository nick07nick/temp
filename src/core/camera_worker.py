# src/core/camera_worker.py
import time
import signal
import sys
import numpy as np
from multiprocessing import Process, shared_memory
from typing import Optional

# Импорты проекта
from src.core.config import settings, log
from src.core.event_bus import EventBus
from src.core.models import SharedMemoryConfig
from src.hardware.webcam import Webcam
from src.core.shared_memory import VideoFrameLayout, RingBufferLayout
from src.core.processor import Processor
from src.core.calibration import CalibrationManager
from src.core.storage import CalibrationStorage


def run_camera_worker(
        camera_id: int,
        shm_config: SharedMemoryConfig,
        bus: EventBus
):
    """
    Процесс камеры.
    Цикл: Захват (Webcam -> Ring SHM) => Чтение View из SHM => Обработка (Processor) => EventBus.
    """
    log.info(f"🚀 CameraWorker-{camera_id} starting (PID: {sys.process_id if hasattr(sys, 'process_id') else '?'})")

    # --- 1. Обработка сигналов остановки ---
    should_run = True

    def stop_handler(signum, frame):
        nonlocal should_run
        log.info(f"🛑 CameraWorker-{camera_id} received stop signal ({signum}).")
        should_run = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    # --- 2. Инициализация ресурсов ---
    shm: Optional[shared_memory.SharedMemory] = None
    cam: Optional[Webcam] = None
    processor: Optional[Processor] = None

    # Переменные для ссылок на память (объявляем заранее, чтобы видеть их в finally)
    frame_view = None
    slot_view = None

    # Для работы с кольцевым буфером
    slot_size: int = 0

    try:
        # A. Shared Memory
        try:
            shm = shared_memory.SharedMemory(name=shm_config.name)

            # Рассчитываем размер одного слота, чтобы потом прыгать по памяти
            slot_size = VideoFrameLayout.get_slot_size(shm_config.shape, shm_config.dtype)

            log.success(f"💾 Connected to Ring SHM: {shm_config.name}")
        except FileNotFoundError:
            log.critical(f"❌ SHM {shm_config.name} not found! Worker cannot start.")
            return
        except Exception as e:
            log.critical(f"❌ SHM error: {e}")
            return

        # B. Webcam
        cam = Webcam(
            device_id=camera_id,
            width=shm_config.shape[1],
            height=shm_config.shape[0],
            fps=settings.CAMERA_FPS,
            shm_name=shm_config.name
        )

        if not cam.connect():
            log.critical(f"❌ Failed to connect to Camera #{camera_id}")
            return

        # C. Processor
        try:
            storage = CalibrationStorage("bikefit_db.json")
            calib_manager = CalibrationManager(storage)
            workspaces = storage.list_workspaces()
            if workspaces:
                calib_manager.set_workspace(workspaces[0])

            processor = Processor(bus, shm_config, calib_manager)
            processor.camera_id = camera_id
            log.success("🧠 Processor initialized.")
        except Exception as e:
            log.error(f"⚠️ Processor init warning: {e}")

        # --- 3. Главный цикл ---
        frame_idx = 0

        while should_run:
            # Шаг 1: Команды управления
            try:
                cmd_data = bus.get_command()
                if cmd_data and cmd_data.get("target") == f"cam_{camera_id}":
                    cmd = cmd_data.get("cmd")
                    val = cmd_data.get("args")

                    if cmd == "set_exposure":
                        cam.set_exposure(int(val))
                    elif cmd == "set_gain":
                        cam.set_gain(int(val))
                    elif cmd == "set_focus":
                        cam.set_focus(int(val))
                    elif cmd == "set_auto_exposure":
                        cam.set_auto_exposure()
            except Exception:
                pass

            # Шаг 2: Захват (Writer)
            # Эта функция сама сдвинет индекс кольца и запишет данные
            success = cam.capture_to_shm(frame_idx)

            if not success:
                time.sleep(0.01)
                continue

            # Шаг 3: Чтение актуального кадра (Reader)
            # Даже внутри того же процесса мы читаем из SHM, чтобы убедиться, что данные там корректны
            if processor:
                try:
                    # 3.1 Узнаем, куда записали последний кадр
                    current_head = RingBufferLayout.get_write_index(shm.buf)

                    # 3.2 Получаем View на этот слот
                    slot_view = RingBufferLayout.get_slot_view(shm.buf, current_head, slot_size)

                    # 3.3 Парсим (достаем картинку)
                    # Возвращает: id, timestamp, frame_view
                    # frame_view - это numpy array, ссылающийся на память (Zero-Copy)
                    fid, ts, frame_view = VideoFrameLayout.parse_from_buf(
                        slot_view,
                        shm_config.shape,
                        shm_config.dtype
                    )

                    # 3.4 Обрабатываем
                    processor.process_frame(frame_view, fid)

                except Exception as e:
                    log.error(f"Processing failed: {e}")

            frame_idx += 1

    except Exception as e:
        log.exception(f"🔥 Critical Worker Crash: {e}")

    finally:
        log.info(f"♻️ Worker-{camera_id} cleaning up resources...")

        # 1. Сначала отпускаем камеру (перестаем писать)
        if cam:
            try:
                cam.release()
                log.info(f"📷 Camera {camera_id} released.")
            except Exception as e:
                log.error(f"Error releasing camera: {e}")

        # 2. КРИТИЧНО: Удаляем все ссылки на данные из SHM
        # Переменные, созданные внутри цикла, остаются в области видимости функции.
        # Их нужно принудительно удалить перед закрытием SHM.
        if 'frame_view' in locals():
            del frame_view
        if 'slot_view' in locals():
            del slot_view

        # Удаляем процессор, так как он может хранить ссылки на кадры (например, для истории)
        if processor:
            del processor

        # 3. Теперь безопасно закрываем SHM
        if shm:
            try:
                shm.close()
                log.success(f"💾 SHM closed for worker {camera_id}")
            except Exception as e:
                log.error(f"⚠️ SHM close error: {e}")

        log.success(f"🏁 Worker-{camera_id} stopped cleanly.")


class CameraWorker:
    """
    Класс-обертка для запуска процесса из main.py.
    """

    def __init__(self, camera_id: int, bus: EventBus, shm_config: SharedMemoryConfig):
        self.camera_id = camera_id
        self.bus = bus
        self.shm_config = shm_config
        self.process: Optional[Process] = None

    def start(self):
        if self.process and self.process.is_alive():
            return

        self.process = Process(
            target=run_camera_worker,
            args=(self.camera_id, self.shm_config, self.bus),
            daemon=True,
            name=f"CameraWorker-{self.camera_id}"
        )
        self.process.start()

    def stop(self):
        """
        Мягкая остановка через SIGTERM -> join.
        """
        if self.process and self.process.is_alive():
            log.info(f"Sending SIGTERM to CameraWorker-{self.camera_id}...")
            self.process.terminate()  # Посылает SIGTERM, который ловится в stop_handler

            # Даем время на выполнение блока finally
            self.process.join(timeout=3.0)

            if self.process.is_alive():
                log.warning(f"CameraWorker-{self.camera_id} hung, killing...")
                self.process.kill()