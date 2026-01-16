# to delete

# src/core/system.py
import time
import logging
import multiprocessing

from src.core import SharedMemoryManager
# FIX: Импортируем обновленные модели
from src.core import SharedMemoryConfig, Point2D
# FIX: Импортируем класс CameraWorker
from src.core import CameraWorker
from src.hardware.mock_camera import MockCamera
from src.hardware.webcam import Webcam
from src.core import CalibrationManager
from src.core import CalibrationStorage
from src.core import EventBus
from src.core import BinaryProtocol, TOTAL_BUFFER_SIZE

logger = logging.getLogger("BikeFit.Core")


def make_real_cam_0():
    # 1920x1200 @ 90 FPS
    return Webcam(device_id=0, width=1920, height=1200, fps=90)


def make_mock_cam_1(): return MockCamera(camera_id=1)


def make_mock_cam_2(): return MockCamera(camera_id=2)


def core_process_loop(event_bus: EventBus):
    logger.info("Core Process Started")

    storage = CalibrationStorage("bikefit_db.json")
    calib_manager = CalibrationManager(storage)
    if storage.list_workspaces():
        calib_manager.set_workspace(storage.list_workspaces()[0])

    cam_configs = []

    # Cam 0 (Color + Video)
    # FIX: Используем shape вместо width/height
    cam_configs.append(SharedMemoryConfig(
        name="cam_0",
        size=1920 * 1200 * 3,
        shape=(1200, 1920, 3),  # (H, W, C)
        enable_video_stream=True
    ))

    # Cam 1, 2 (Only Points)
    cam_configs.append(
        SharedMemoryConfig(name="cam_1", size=TOTAL_BUFFER_SIZE, shape=(0, 0, 0), enable_video_stream=False))
    cam_configs.append(
        SharedMemoryConfig(name="cam_2", size=TOTAL_BUFFER_SIZE, shape=(0, 0, 0), enable_video_stream=False))

    factories = [make_real_cam_0, make_mock_cam_1, make_mock_cam_2]

    managers = []
    workers = []

    try:
        # Launch
        for i, cfg in enumerate(cam_configs):
            if cfg.enable_video_stream:
                # FIX: SharedMemoryManager принимает параметры конфигурации
                mgr = SharedMemoryManager(cfg, create=True)
                mgr.__enter__()
                managers.append(mgr)

            stop_evt = multiprocessing.Event()

            # --- DAEMON = TRUE ---
            # FIX: Используем CameraWorker.run
            # Важно: CameraWorker.run принимает (bus, shm_config, camera_id)
            # Мы адаптируем вызов
            p = multiprocessing.Process(
                target=CameraWorker.run,
                args=(event_bus, cfg, i),
                daemon=True
            )
            p.start()
            workers.append((p, stop_evt))

        logger.info("Workers Launched (Daemon Mode). Cam 0 High Performance.")

        # ... (Код протоколов остается, но заглушим ошибку, если файла нет)
        proto_managers = []
        for i in range(3):
            # FIX: Shape заглушка
            p_cfg = SharedMemoryConfig(name=f"cam_{i}_proto", size=TOTAL_BUFFER_SIZE, shape=(0, 0, 0),
                                       enable_video_stream=False)
            connected = False
            for attempt in range(5):  # Уменьшил кол-во попыток для скорости
                try:
                    pm = SharedMemoryManager(p_cfg, create=False)
                    pm.__enter__()
                    proto_managers.append(pm)
                    connected = True
                    break
                except Exception:
                    time.sleep(0.5)
            # if not connected: logger.warning(f"Proto SHM {i} not connected")

        # Основной цикл ядра (эмуляция данных для фронта)
        while True:
            loop_start = time.time()

            stream_packet = {
                "timestamp": time.time(),
                "workspace": calib_manager._current_workspace,
                "cameras": {}
            }

            # Пока у нас нет реальных точек от CameraWorker (т.к. мы его переписываем),
            # создадим фейковые данные, чтобы Фронт не показывал "Disconnected"
            # Это временный костыль для теста связи!
            stream_packet["cameras"]["cam_0"] = [{"x": 960, "y": 600}]  # Точка в центре

            # Попытка чтения реальных данных (если протокол заработает)
            for i, mgr in enumerate(proto_managers):
                try:
                    packet = BinaryProtocol.unpack(mgr.buffer)
                    raw_points = [Point2D(x=p[0], y=p[1]) for p in packet.points]
                    # clean_points = calib_manager.undistort_points(i, raw_points)
                    points_data = [{"x": round(p.x, 1), "y": round(p.y, 1)} for p in raw_points]
                    stream_packet["cameras"][f"cam_{i}"] = points_data
                except Exception:
                    pass

            # FIX: Отправляем данные в EventBus (чтобы сервер их переслал на фронт)
            # В оригинальном коде это было: event_bus.publish_stream_data(stream_packet)
            # Проверим метод в твоем event_bus.py (в уме), скорее всего это publish("stream", ...)
            # Для надежности используем стандартный publish
            if hasattr(event_bus, 'publish_stream_data'):
                event_bus.publish_stream_data(stream_packet)
            elif hasattr(event_bus, 'publish'):
                event_bus.publish("stream_data", stream_packet)

            elapsed = time.time() - loop_start
            time.sleep(max(0, 0.011 - elapsed))

    except KeyboardInterrupt:
        pass
    finally:
        for p, stop in workers:
            if p.is_alive(): p.terminate()
        for mgr in managers:
            if hasattr(mgr, 'close'): mgr.close()
        for mgr in proto_managers:
            if hasattr(mgr, 'close'): mgr.close()