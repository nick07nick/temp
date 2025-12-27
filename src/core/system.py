# src/core/system.py
import time
import logging
import multiprocessing
from typing import List

from src.core.shared_memory import SharedMemoryManager
from src.core.models import SharedMemoryConfig
from src.core.camera_worker import camera_worker_loop
from src.hardware.mock_camera import MockCamera
from src.core.processor import MarkerDetector
from src.core.calibration import CalibrationManager
from src.core.storage import CalibrationStorage
from src.core.event_bus import EventBus

logger = logging.getLogger("BikeFit.Core")


def make_cam_0(): return MockCamera(camera_id=0)


def make_cam_1(): return MockCamera(camera_id=1)


def make_cam_2(): return MockCamera(camera_id=2)


def core_process_loop(event_bus: EventBus):
    """
    Основной цикл обработки видео.
    Запускается в отдельном ПРОЦЕССЕ, чтобы не блокировать API.
    """
    logger.info("Core Process Started")

    # 1. Init Logic
    storage = CalibrationStorage("bikefit_db.json")
    calib_manager = CalibrationManager(storage)

    # Загружаем дефолт, если есть
    workspaces = storage.list_workspaces()
    if workspaces:
        calib_manager.set_workspace(workspaces[0])

    detector = MarkerDetector()

    # 2. Init Hardware
    WIDTH, HEIGHT = 1920, 1080
    cam_configs = [
        SharedMemoryConfig(name=f"cam_{i}", size=WIDTH * HEIGHT * 3, width=WIDTH, height=HEIGHT)
        for i in range(3)
    ]
    factories = [make_cam_0, make_cam_1, make_cam_2]

    managers = []
    workers = []

    try:
        # Launch Camera Workers
        for i, cfg in enumerate(cam_configs):
            mgr = SharedMemoryManager(cfg, create=True)
            mgr.__enter__()
            managers.append(mgr)

            stop_evt = multiprocessing.Event()
            p = multiprocessing.Process(
                target=camera_worker_loop,
                args=(factories[i], cfg, stop_evt, i),
                daemon=True
            )
            p.start()
            workers.append((p, stop_evt))

        logger.info("Camera Workers Launched")

        # 3. Processing Loop
        while True:
            loop_start = time.time()

            # 3.1. Check Commands from API
            cmd_data = event_bus.get_command()
            if cmd_data:
                cmd, payload = cmd_data
                if cmd == "SET_WORKSPACE":
                    logger.info(f"Command received: SET_WORKSPACE -> {payload}")
                    calib_manager.set_workspace(payload)

            # 3.2. Process Frames
            stream_packet = {
                "timestamp": time.time(),
                "workspace": calib_manager._current_workspace,
                "cameras": {}
            }

            for i, mgr in enumerate(managers):
                frame = mgr.get_numpy_array()
                raw_points = detector.process_frame(frame)
                clean_points = calib_manager.undistort_points(i, raw_points)

                points_data = [{"x": round(p.x, 1), "y": round(p.y, 1)} for p in clean_points]
                stream_packet["cameras"][f"cam_{i}"] = points_data

            # 3.3. Send to API
            event_bus.publish_stream_data(stream_packet)

            # FPS Limit ~30
            elapsed = time.time() - loop_start
            time.sleep(max(0, 0.033 - elapsed))

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Core Crash: {e}", exc_info=True)
    finally:
        for p, stop in workers:
            stop.set()
            p.join(1)
            p.terminate()
        for mgr in managers:
            mgr.__exit__(None, None, None)