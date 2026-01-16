import time
import signal
import os
import queue
import cv2
import json
import numpy as np
from loguru import logger as log

# Core
from src.core.processor import Processor
from src.core.event_bus import EventBus
from src.core.config import settings
from src.core.device_manager import device_manager

# Data & Memory
from src.data.models import SharedMemoryConfig
from src.data.shared_memory import SharedMemoryManager, VideoFrameLayout, RingBufferLayout
from src.data.schemas import CameraConfig, PluginCommand

# Hardware
from src.hardware.webcam import Webcam


# [FIX] Добавил device_index=None в аргументы
def run_camera_worker(camera_id: int, shm_config: SharedMemoryConfig, bus: EventBus, device_index: int = None):
    """
    Процесс камеры (CameraWorker).
    Исправленная версия:
    1. Принимает явный device_index от Оркестратора.
    2. Если индекса нет — использует старую логику сканирования (Fallback).
    """
    pid = os.getpid()
    log.info(f"🚀 CameraWorker-{camera_id} starting (PID: {pid})...")

    should_run = True

    def stop_handler(signum, frame):
        nonlocal should_run
        should_run = False

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    webcam = None
    shm = None
    processor = None

    # === 1. Resolve Profile & Hardware ===
    camera_profile = None
    for role_key, profile in settings.PROFILE.cameras.items():
        if profile.role_id == camera_id:
            camera_profile = profile
            break

    current_role = camera_profile.role_name if camera_profile else "unknown"
    target_serial = camera_profile.serial_number if camera_profile else None
    tgt_res = camera_profile.resolution if camera_profile else [settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT]

    log.info(f"🎥 Worker-{camera_id} Role: {current_role} | Serial: {target_serial or 'N/A'}")

    # [FIX] Логика выбора устройства
    opencv_index = 0

    if device_index is not None:
        # Стратегия 1: Строгое подчинение Оркестратору
        opencv_index = device_index
        log.success(f"🔒 Worker-{camera_id} using Orchestrator assigned Device Index: {opencv_index}")
    else:
        # Стратегия 2: Самостоятельный поиск (Legacy / Fallback)
        log.warning(f"⚠️ Worker-{camera_id} started without explicit index. Scanning devices...")
        device_manager.scan_devices()

        if target_serial:
            found_idx = device_manager.get_camera_index_by_serial(target_serial)
            if found_idx is not None:
                opencv_index = found_idx
                log.success(f"✅ Bound {current_role} ({target_serial}) -> Device Index {opencv_index}")
            else:
                log.error(f"❌ Device {target_serial} NOT FOUND! Using fallback index 0.")
                opencv_index = 0
        else:
            opencv_index = camera_id

    # === 2. Init Webcam ===
    try:
        webcam = Webcam(
            device_id=opencv_index,
            width=tgt_res[0],
            height=tgt_res[1],
            fps=settings.CAMERA_FPS
        )
        if not webcam.connect():
            log.error(f"❌ Camera connect fail at index {opencv_index}")
            return
    except Exception as e:
        log.critical(f"❌ Webcam Init Init Error: {e}")
        return

    # === 3. Dynamic Memory Allocation (Working V3.3) ===
    real_w = int(webcam._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(webcam._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if real_w == 0 or real_h == 0:
        log.critical("❌ Camera reported 0x0 resolution! Aborting.")
        webcam.release()
        return

    TARGET_W, TARGET_H = real_w, real_h
    session_id = int(time.time())
    unique_shm_name = f"{shm_config.name}_{session_id}"

    # Recalculate size
    frame_size_bytes = real_w * real_h * 3
    total_shm_size = frame_size_bytes * settings.SHM_BUFFER_COUNT

    log.info(f"📏 Hardware Resolution: {real_w}x{real_h}. Re-allocating SHM to {total_shm_size / 1024 / 1024:.2f} MB")

    try:
        try:
            current_shm_config = shm_config.model_copy(update={
                "name": unique_shm_name, "shape": (real_h, real_w, 3), "size": total_shm_size
            })
        except AttributeError:
            current_shm_config = shm_config.copy(update={
                "name": unique_shm_name, "shape": (real_h, real_w, 3), "size": total_shm_size
            })

        shm = SharedMemoryManager(config=current_shm_config, create=True)
        shm_buf = shm.shm.buf

        # Handshake
        bus.publish_critical({
            "type": "shm_handshake",
            "payload": {
                "camera_id": camera_id, "role": current_role,
                "shm_name": unique_shm_name, "shape": current_shm_config.shape,
                "dtype": current_shm_config.dtype
            }
        })

    except Exception as e:
        log.error(f"❌ SHM Init Error: {e}")
        if webcam: webcam.release()
        return

    # === 4. Processor & Calibration ===
    try:
        processor = Processor(bus, camera_id)
        current_config = CameraConfig(camera_id=camera_id)

        if camera_profile and camera_profile.calibration_file:
            calib_path = settings.get_calibration_path(camera_profile.calibration_file)
            if calib_path.exists():
                try:
                    with open(calib_path, 'r') as f:
                        calib_data = json.load(f)
                    current_config.calibration_data = calib_data
                    log.info(f"📐 Loaded calibration: {calib_path.name}")
                except:
                    pass

        webcam.apply_config(current_config)

    except Exception as e:
        log.critical(f"❌ Processor/Config Error: {e}")
        if shm: shm.close()
        webcam.release()
        return

    # === 5. Main Loop ===
    frame_idx = int(time.time() * 1000)
    queue_cmd = bus._command_queues.get(camera_id)
    math_salt = 1.0
    last_heartbeat = time.time()

    log.success(f"🎥 Worker-{camera_id} Running at {TARGET_W}x{TARGET_H}. Salt Protected.")

    try:
        while should_run:
            # --- Command Handling ---
            if queue_cmd:
                while not queue_cmd.empty():
                    try:
                        pkt = queue_cmd.get_nowait()
                        if isinstance(pkt, dict):
                            cmd = pkt.get("cmd") or pkt.get("payload", {}).get("cmd")
                            args = pkt.get("args") or pkt.get("payload", {}).get("args", {})
                            target = pkt.get("target")
                        else:
                            cmd = getattr(pkt, "cmd", None)
                            args = getattr(pkt, "args", {})
                            target = getattr(pkt, "target", None)

                        if cmd == "SET_SALT":
                            math_salt = float(args.get("salt", 1.0))

                        elif cmd == "SET_CONFIG":
                            cfg_dict = current_config.model_dump()
                            cfg_dict.update(args)
                            current_config = CameraConfig(**cfg_dict)
                            webcam.apply_config(current_config)
                            log.info(f"⚙️ Config Updated: {args}")

                        elif processor:
                            plugin_cmd = PluginCommand(target=target or "broadcast", cmd=cmd, args=args)
                            processor.handle_command(plugin_cmd)

                    except queue.Empty:
                        break

            # --- Capture ---
            ret, frame = webcam.read_frame()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            ts = time.perf_counter()

            if frame.shape[1] != TARGET_W or frame.shape[0] != TARGET_H:
                frame = cv2.resize(frame, (TARGET_W, TARGET_H))

            # --- Write SHM ---
            slot_view = None
            try:
                head_idx = RingBufferLayout.get_write_index(shm_buf)
                next_idx = (head_idx + 1) % shm.capacity
                slot_view = RingBufferLayout.get_slot_view(shm_buf, next_idx, shm.slot_size)

                VideoFrameLayout.write_to_buf(slot_view, frame, frame_idx, ts, math_salt, 0)
                RingBufferLayout.update_write_index(shm_buf, next_idx)
            except:
                pass
            finally:
                if slot_view is not None: del slot_view

            # --- Process ---
            processor.process_frame(frame, frame_idx, current_config)

            # --- Heartbeat ---
            if time.time() - last_heartbeat > 1.0:
                bus.publish_event("heartbeat", {
                    "camera_id": camera_id,
                    "role": current_role,
                    "sn": target_serial,
                    "config": current_config.model_dump()
                })
                last_heartbeat = time.time()

            frame_idx += 1

    except Exception as e:
        log.critical(f"Worker Crash: {e}")
    finally:
        log.info(f"🛑 CameraWorker-{camera_id} cleanup...")
        if webcam: webcam.release()
        if shm:
            try:
                shm.close()
            except:
                pass
        log.info(f"👋 CameraWorker-{camera_id} finished.")