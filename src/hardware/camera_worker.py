import time
import signal
import os
import queue
import cv2
import numpy as np
from loguru import logger as log

# Core
from src.core.processor import Processor
from src.core.event_bus import EventBus
from src.core.config import settings

# Data & Memory
from src.data.models import SharedMemoryConfig
from src.data.shared_memory import SharedMemoryManager, VideoFrameLayout, RingBufferLayout
# [FIX] Добавили PluginCommand для корректной передачи в Processor
from src.data.schemas import CameraConfig, PluginCommand

# Hardware
from src.hardware.webcam import Webcam


def run_camera_worker(camera_id: int, shm_config: SharedMemoryConfig, bus: EventBus):
    """
    Процесс камеры (CameraWorker).
    Интегрирован с Processor для маршрутизации команд плагинам.
    """

    # === 0. Setup Process ===
    log.info(f"🚀 CameraWorker-{camera_id} starting (PID: {os.getpid()})...")

    should_run = True

    def stop_handler(signum, frame):
        nonlocal should_run
        should_run = False

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    # === 1. Init Resources ===

    # A. Queue
    try:
        command_queue = bus._command_queues[camera_id]
    except (AttributeError, KeyError):
        log.critical("❌ No command queue!")
        return

    # B. Webcam
    webcam = Webcam(
        device_id=settings.CAMERA_INDEX + camera_id,
        width=settings.CAMERA_WIDTH,
        height=settings.CAMERA_HEIGHT,
        fps=settings.CAMERA_FPS
    )

    if not webcam.connect():
        log.error("❌ Camera connect fail")
        return

    # C. Shared Memory
    try:
        shm = SharedMemoryManager(config=shm_config, create=True)
        shm_buf = shm.shm.buf
        log.info(f"💾 SHM Allocated: {shm.size} bytes ({shm.capacity} slots)")
    except Exception as e:
        log.error(f"❌ SHM Init Error: {e}")
        webcam.release()
        return

    # D. Processor & Config
    processor = Processor(bus, camera_id)
    current_config = CameraConfig(camera_id=camera_id)
    webcam.apply_config(current_config)

    # Runtime vars
    frame_idx = 0
    math_salt = 1.0
    last_heartbeat = time.time()
    TARGET_W = settings.CAMERA_WIDTH
    TARGET_H = settings.CAMERA_HEIGHT

    log.success(f"🎥 CameraWorker-{camera_id} ready. Loop running.")

    # === 3. Main Loop ===
    while should_run:
        iter_start = time.perf_counter()

        # --- PHASE 1: Commands (Control Plane) ---
        while not command_queue.empty():
            try:
                cmd_packet = command_queue.get_nowait()

                # 1. Нормализация формата команды
                target = None
                cmd = None
                args = {}

                if isinstance(cmd_packet, dict):
                    target = cmd_packet.get("target")
                    # Поддержка вложенности payload (если приходит от сервера)
                    cmd = cmd_packet.get("cmd") or cmd_packet.get("payload", {}).get("cmd")
                    args = cmd_packet.get("args") or cmd_packet.get("payload", {}).get("args", {})
                else:
                    # Если это объект
                    target = getattr(cmd_packet, "target", None)
                    cmd = getattr(cmd_packet, "cmd", None)
                    args = getattr(cmd_packet, "args", {})

                if not cmd:
                    continue

                # 2. Системные команды (обрабатывает Воркер)
                if cmd == "SET_CONFIG":
                    cfg_dict = current_config.model_dump()
                    cfg_dict.update(args)
                    current_config = CameraConfig(**cfg_dict)
                    webcam.apply_config(current_config)
                    # log.info(f"⚙️ Config updated: {args}")

                elif cmd == "SET_SALT":
                    math_salt = float(args.get("salt", 1.0))

                # 3. Команды Плагинам (Делегируем Процессору)
                else:
                    # Упаковываем в PluginCommand и отдаем мозгу
                    # Processor сам найдет нужную стадию по target
                    plugin_cmd = PluginCommand(
                        target=target if target else "broadcast",
                        cmd=cmd,
                        args=args
                    )
                    processor.handle_command(plugin_cmd)

            except queue.Empty:
                break
            except Exception as e:
                log.error(f"Command Error: {e}")

        # --- PHASE 2: Capture ---
        ret, frame = webcam.read_frame()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        timestamp = time.perf_counter()

        # Resize Guard
        h, w = frame.shape[:2]
        if w != TARGET_W or h != TARGET_H:
            frame = cv2.resize(frame, (TARGET_W, TARGET_H))

        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # --- PHASE 3: Write SHM ---
        try:
            head_idx = RingBufferLayout.get_write_index(shm_buf)
            # shm.capacity теперь берется из settings, так что всё безопасно
            next_idx = (head_idx + 1) % shm.capacity

            slot_view = RingBufferLayout.get_slot_view(shm_buf, next_idx, shm.slot_size)

            VideoFrameLayout.write_to_buf(
                slot_view, frame, frame_idx, timestamp, math_salt, 0
            )
            RingBufferLayout.update_write_index(shm_buf, next_idx)
        except Exception as e:
            log.error(f"SHM Write Error: {e}")

        # --- PHASE 4: Processing ---
        try:
            processor.process_frame(frame, frame_idx, current_config)
        except Exception:
            log.error(f"Pipeline Error: {e}")

        # --- PHASE 5: Heartbeat ---
        if time.time() - last_heartbeat > 1.0:
            bus.publish_event("heartbeat", {"camera_id": camera_id, "pid": os.getpid()})
            last_heartbeat = time.time()

        frame_idx += 1

    try:
        webcam.release()
    except:
        pass
    try:
        shm.close()
    except:
        pass