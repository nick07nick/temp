# src/api/server.py
from collections import deque
from typing import Dict, Optional, List, Any
import asyncio
import orjson
import logging
import cv2
import numpy as np
import time
import struct
import json
import os
import gc

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
# Оставляем jsonable_encoder для совместимости
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError

# === V3.0 IMPORTS ===
from src.core.event_bus import EventBus
from src.data.shared_memory import SharedMemoryManager, VideoFrameLayout, RingBufferLayout
from src.data.models import SharedMemoryConfig
from src.data.schemas import PluginCommand, CameraConfig
from src.core.loader import scan_api_routers

logger = logging.getLogger("BikeFit.API")

# --- GLOBAL STATE ---
video_managers: Dict[int, SharedMemoryManager] = {}

# Заглушка для Storage, если модуля нет (для совместимости)
try:
    from src.data.storage import CalibrationStorage
except ImportError:
    class CalibrationStorage:
        def __init__(self, path): pass

        def list_workspaces(self): return []


# --- MODELS (Восстановлены для совместимости с Frontend API) ---
class WorkspaceSwitchRequest(BaseModel):
    name: str


class CameraConfigRequest(BaseModel):
    threshold: Optional[int] = None
    exposure: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None


# --- MAIN APP ---
def create_app(event_bus: EventBus, storage: CalibrationStorage, default_shm: SharedMemoryConfig = None):
    app = FastAPI(title="BikeFit Backend v3.1 (Unique SHM)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 1. Подключаем плагины
    try:
        plugin_routers = scan_api_routers()
        for router in plugin_routers:
            app.include_router(router)
            logger.info(f"✅ API: Plugin router connected (Tags: {router.tags})")
    except Exception as e:
        logger.error(f"Failed to scan plugins: {e}")

    if default_shm:
        logger.info(f"ℹ️ Server knowns about default SHM: {default_shm.name}")

    # --- HANDSHAKE LOGIC ---
    def handle_update_shm(args: dict):
        """
        Обрабатывает сигнал shm_handshake от воркера.
        Использует логику проверки имен, чтобы избежать лишних реконнектов.
        """
        try:
            cam_id = int(args.get("camera_id", 0))
            new_shm_name = args.get("shm_name")
            shape = tuple(args.get("shape", (1200, 1920, 3)))
            dtype = args.get("dtype", "uint8")

            # [FIX] Idempotency Check
            # Если имя памяти не изменилось, значит это просто повторный хендшейк.
            current_mgr = video_managers.get(cam_id)
            if current_mgr and current_mgr.name == new_shm_name:
                return

            logger.info(f"♻️ Hot-Swap Signal: Cam {cam_id} switching to -> {new_shm_name}")

            # 1. Безопасно отключаемся от старой памяти
            if cam_id in video_managers:
                old_mgr = video_managers[cam_id]
                try:
                    old_mgr.close()
                except Exception:
                    pass
                video_managers.pop(cam_id, None)

            # 2. Подключаемся к новой (только чтение)
            new_config = SharedMemoryConfig(
                name=new_shm_name, size=0, shape=shape, dtype=dtype
            )
            mgr = SharedMemoryManager(new_config, create=False)

            if mgr.shm:
                video_managers[cam_id] = mgr
                logger.info(f"✅ Hot-Swap Success: Connected to {new_shm_name}")
            else:
                logger.error(f"❌ Hot-Swap Failed: Could not attach to {new_shm_name}")

        except Exception as e:
            logger.error(f"SHM Update Error: {e}")

    # --- BINARY STREAM GENERATOR ---
        # --- BINARY STREAM GENERATOR (SAFE ROLLBACK) ---
    def generate_binary_stream(cam_id: int):
            # [SAFE OPTIMIZATION] Качество 50 вместо 70.
            # Это снизит нагрузку на CPU, но не сломает формат картинки.
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]

            # Генерация заглушки (Waiting Screen)
            placeholder = np.zeros((600, 800, 3), dtype=np.uint8)
            cv2.putText(placeholder, "NO SIGNAL", (50, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            _, ph_bytes = cv2.imencode('.jpg', placeholder, encode_param)
            ph_data = ph_bytes.tobytes()
            ph_header = struct.pack('<QI', 0, len(ph_data))

            # Переменные состояния
            last_frame_id = -1
            active_manager_name = None

            fallback_shm_name = default_shm.name if default_shm else f"shm_cam_{cam_id}"
            retry_delay = 0.1
            last_error_time = 0

            # Дефолтные параметры
            current_shape = (1200, 1920, 3)
            current_dtype = "uint8"
            if default_shm:
                current_shape = default_shm.shape
                current_dtype = default_shm.dtype

            while True:
                slot_view = None
                frame = None

                try:
                    mgr = video_managers.get(cam_id)

                    # [FIX] Stream Reset Logic
                    if mgr and mgr.name != active_manager_name:
                        active_manager_name = mgr.name
                        last_frame_id = -1
                        logger.warning(f"🔄 Stream Reset: New SHM source detected ({mgr.name})")

                    # Если менеджера нет или память отвалилась
                    if not mgr or not mgr.shm:
                        if not active_manager_name:
                            try:
                                # Ленивая попытка авто-коннекта
                                cfg = SharedMemoryConfig(
                                    name=fallback_shm_name, size=0, shape=current_shape, dtype="uint8"
                                )
                                test_mgr = SharedMemoryManager(cfg, create=False)
                                if test_mgr.shm:
                                    video_managers[cam_id] = test_mgr
                                    logger.info(f"✅ Auto-Connect: Found {fallback_shm_name}")
                                    continue
                            except Exception:
                                # [FIX] Молчим при авто-коннекте, так как ждем Handshake
                                pass

                        yield ph_header + ph_data
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 1.5, 1.0)
                        continue

                    retry_delay = 0.1
                    frame_data = None
                    current_fid = 0

                    # --- CRITICAL SECTION: Чтение из Shared Memory ---
                    try:
                        head_idx = RingBufferLayout.get_write_index(mgr.shm.buf)
                        slot_view = RingBufferLayout.get_slot_view(mgr.shm.buf, head_idx, mgr.slot_size)

                        use_shape = getattr(mgr, 'shm_config', None) and mgr.shm_config.shape or current_shape
                        use_dtype = getattr(mgr, 'shm_config', None) and mgr.shm_config.dtype or current_dtype

                        fid, ts, salt, flags, frame = VideoFrameLayout.parse_from_buf(
                            slot_view, use_shape, use_dtype
                        )

                        if fid > last_frame_id:
                            # [NOTE] Тут было сжатие.
                            # Если хотим ресайз - надо делать его аккуратно.
                            # Пока оставляем оригинал, чтобы вернуть картинку.
                            ret, jpg = cv2.imencode('.jpg', frame, encode_param)
                            if ret:
                                frame_data = jpg.tobytes()
                                current_fid = fid
                                last_frame_id = fid

                        elif last_frame_id > fid + 5000:
                            last_frame_id = -1  # Auto-recovery

                    finally:
                        if slot_view is not None:
                            del slot_view
                            slot_view = None
                        if frame is not None:
                            del frame
                            frame = None
                    # --- END CRITICAL SECTION ---

                    if frame_data:
                        header = struct.pack('<QI', current_fid, len(frame_data))
                        yield header + frame_data
                    else:
                        time.sleep(0.004)

                except Exception as e:
                    if time.time() - last_error_time > 2.0:
                        last_error_time = time.time()

                    if isinstance(e, (BufferError, ValueError, FileNotFoundError)):
                        if cam_id in video_managers:
                            video_managers.pop(cam_id, None)
                    time.sleep(0.1)
                    continue

    @app.get("/video_feed/{cam_id}")
    async def video_feed(cam_id: int):
        return StreamingResponse(
            generate_binary_stream(cam_id),
            media_type="application/octet-stream"
        )

    # --- WEBSOCKET ENDPOINT ---
    @app.websocket("/ws/stream")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()

        def universal_encoder(obj: Any):
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, BaseModel): return obj.dict()
            if hasattr(obj, "model_dump"): return obj.model_dump()
            try:
                return jsonable_encoder(obj)
            except:
                return str(obj)

        async def listen_to_frontend():
            try:
                while True:
                    raw_msg = await websocket.receive_text()
                    try:
                        msg = json.loads(raw_msg)
                        if isinstance(msg, dict) and msg.get("type") == "ping":
                            continue

                        if "payload" in msg and "target" in msg:
                            cmd_data = {
                                "target": msg["target"],
                                "cmd": msg["payload"].get("cmd", "UNKNOWN"),
                                "args": msg["payload"].get("args", {})
                            }
                        else:
                            cmd_data = msg

                        command = PluginCommand(**cmd_data)
                        event_bus.publish_event("command", command.dict())

                    except Exception:
                        pass
            except WebSocketDisconnect:
                pass

        async def send_packet(packet: dict):
            """Helper для отправки JSON"""
            try:
                json_bytes = orjson.dumps(
                    packet,
                    default=universal_encoder,
                    # [FIX] Добавляем OPT_NON_STR_KEYS, чтобы числа-ключи не ломали отправку
                    option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS
                )
                await websocket.send_text(json_bytes.decode('utf-8'))
            except Exception as e:
                logger.error(f"Serialize Error: {e}")

        async def send_to_frontend():
            try:
                while True:
                    data_sent = False

                    # 1. [CRITICAL] СНАЧАЛА читаем гарантированный канал (Handshake)
                    critical = event_bus.get_critical_data()
                    if critical:
                        if critical.get("type") == "shm_handshake":
                            handle_update_shm(critical["payload"])
                        # Отправляем на фронт как есть
                        await send_packet(critical)
                        data_sent = True

                    # 2. [BROADCAST] Сообщения от Оркестратора (SystemMonitor, Logs)
                    # === FIX: Используем get_broadcast_data ===
                    broadcast = event_bus.get_broadcast_data()
                    if broadcast:
                        m_type = broadcast.get("type")
                        payload = broadcast.get("payload")

                        if m_type == "system_monitor":
                            # Оборачиваем, чтобы фронт положил это в pluginData.system_monitor
                            packet = {
                                "type": "plugin_data",
                                "payload": {
                                    "plugin": "system_monitor",
                                    "data": payload
                                }
                            }
                            await send_packet(packet)

                        elif m_type == "calibration_data":
                            # Специфично для калибровки
                            packet = {
                                "type": "plugin_data",
                                "payload": {
                                    "plugin": "calibration_widget",
                                    "data": payload
                                }
                            }
                            await send_packet(packet)

                        else:
                            # Остальные события
                            await send_packet(broadcast)

                        data_sent = True

                    # 3. Если критических данных нет, читаем стрим (точки)
                    if not data_sent:
                        for _ in range(10):  # Пачками, чтобы быстрее разгребать
                            stream_data = event_bus.get_stream_data()
                            if not stream_data: break
                            await send_packet(stream_data)
                            data_sent = True

                    if not data_sent:
                        await asyncio.sleep(0.005)

                    if websocket.client_state.name == "DISCONNECTED":
                        break
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"WS Send Error: {e}")

        await asyncio.gather(listen_to_frontend(), send_to_frontend())

    return app


def run_server(bus: EventBus, shm_config: SharedMemoryConfig):
    from uvicorn import Config, Server

    try:
        from src.data.storage import CalibrationStorage
        storage = CalibrationStorage("bikefit_db.json")
    except ImportError:
        storage = None

    app = create_app(event_bus=bus, storage=storage, default_shm=shm_config)
    config = Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
    server = Server(config)
    server.run()