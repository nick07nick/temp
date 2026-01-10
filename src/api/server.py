# src/api/server.py
from collections import deque
from typing import Dict, Optional, List
import asyncio
import logging
import cv2
import numpy as np
import time
import struct
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError

# === V3.0 IMPORTS ===
from src.core.event_bus import EventBus
from src.data.shared_memory import SharedMemoryManager, VideoFrameLayout, RingBufferLayout
from src.data.models import SharedMemoryConfig
from src.data.schemas import PluginCommand, CameraConfig

# Импорт сканера
from src.core.loader import scan_api_routers

# Заглушка хранилища
try:
    from src.data.storage import CalibrationStorage
except ImportError:
    class CalibrationStorage:
        def __init__(self, path): pass

        def list_workspaces(self): return []

logger = logging.getLogger("BikeFit.API")


class WorkspaceSwitchRequest(BaseModel):
    name: str


class CameraConfigRequest(BaseModel):
    threshold: Optional[int] = None
    exposure: Optional[int] = None


# Глобальные хранилища для видео-менеджеров
video_managers: Dict[int, SharedMemoryManager] = {}
video_configs_store: Dict[int, SharedMemoryConfig] = {}


def create_app(event_bus: EventBus, storage: CalibrationStorage, vid_configs: dict = None):
    app = FastAPI(title="BikeFit Backend v3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 1. АВТОМАТИЧЕСКАЯ ЗАГРУЗКА РОУТЕРОВ ИЗ ПЛАГИНОВ
    try:
        plugin_routers = scan_api_routers()
        for router in plugin_routers:
            app.include_router(router)
            logger.info(f"✅ API: Plugin router connected (Tags: {router.tags})")
    except Exception as e:
        logger.error(f"Failed to scan plugins: {e}")

    if vid_configs:
        global video_configs_store
        video_configs_store = vid_configs

    # --- VIDEO FEED (CUSTOM BINARY PROTOCOL) ---
    def get_video_manager(cam_id: int):
        if cam_id in video_managers:
            mgr = video_managers[cam_id]
            if mgr.shm is not None:
                return mgr

        if cam_id not in video_configs_store:
            return None

        cfg = video_configs_store[cam_id]
        try:
            mgr = SharedMemoryManager(cfg, create=False)
            if mgr.shm is not None:
                video_managers[cam_id] = mgr
                logger.info(f"API Server: Linked to video buffer {cfg.name}")
                return mgr
        except Exception:
            pass
        return None

    def generate_binary_stream(cam_id: int):
        """
        Генератор Бинарного потока.
        Оптимизирован для стабильности: не падает при ошибках чтения SHM.
        """
        # Параметры сжатия (70% качества - баланс скорости и картинки)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]

        # 1. Подготовка заглушки (чтобы не кодировать её каждый раз)
        placeholder = np.zeros((600, 800, 3), dtype=np.uint8)
        cv2.putText(placeholder, "WAITING FOR CAMERA...", (50, 300),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        _, ph_bytes = cv2.imencode('.jpg', placeholder, encode_param)
        ph_data = ph_bytes.tobytes()
        ph_header = struct.pack('<QI', 0, len(ph_data))  # Заранее упакованный заголовок

        last_frame_id = -1

        # [DEBUG] Логируем старт
        logger.info(f"🎥 Stream started for Cam-{cam_id}")

        while True:
            mgr = get_video_manager(cam_id)

            # Если менеджера нет (камера не инициализирована)
            if not mgr or not mgr.shm:
                # Шлем заглушку раз в секунду, чтобы клиент не отвалился по таймауту
                yield ph_header + ph_data
                time.sleep(1.0)
                continue

            frame_data = None
            current_fid = 0

            try:
                # Читаем данные из SHM
                # Используем write_index, чтобы читать самый свежий кадр
                head_idx = RingBufferLayout.get_write_index(mgr.shm.buf)
                slot_view = RingBufferLayout.get_slot_view(mgr.shm.buf, head_idx, mgr.slot_size)

                # Парсим заголовок (ОЧЕНЬ БЫСТРО)
                fid, ts, salt, flags, frame = VideoFrameLayout.parse_from_buf(
                    slot_view,
                    video_configs_store[cam_id].shape,
                    video_configs_store[cam_id].dtype
                )

                # Если это новый кадр
                if fid > last_frame_id:
                    # Кодируем (ТЯЖЕЛО)
                    ret, jpg = cv2.imencode('.jpg', frame, encode_param)
                    if ret:
                        frame_data = jpg.tobytes()
                        current_fid = fid
                        last_frame_id = fid

            except Exception as e:
                # Ошибки чтения (например, гонка записи/чтения) игнорируем, просто ждем следующий цикл
                # logger.warning(f"Stream Error: {e}") # Можно раскомментить для отладки
                time.sleep(0.001)
                continue

            # Отправка
            if frame_data is not None:
                try:
                    # Header: [Frame ID (8b)][Size (4b)]
                    header = struct.pack('<QI', current_fid, len(frame_data))
                    yield header + frame_data
                except Exception as e:
                    logger.error(f"Stream Yield Error: {e}")
                    break  # Если клиент отключился, выходим
            else:
                # Кадров новых нет -> спим коротко, чтобы не грузить CPU
                time.sleep(0.005)

    @app.get("/video_feed/{cam_id}")
    async def video_feed(cam_id: int):
        # [FIX] media_type теперь octet-stream, так как это не стандартный MJPEG
        return StreamingResponse(
            generate_binary_stream(cam_id),
            media_type="application/octet-stream"
        )

    @app.get("/workspaces")
    async def get_workspaces():
        return {"workspaces": storage.list_workspaces() if storage else []}

    @app.post("/camera/{cam_id}/config")
    async def set_camera_config(cam_id: int, req: CameraConfigRequest):
        target = f"cam_{cam_id}"
        event_bus.send_command(target, "SET_CONFIG", req.model_dump())
        return {"status": "ok"}

    # --- WEBSOCKET STREAM ---
    @app.websocket("/ws/stream")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("🟢 UI Connected to WebSocket")

        packet_window = deque(maxlen=5)

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

                    except (ValidationError, json.JSONDecodeError):
                        pass

            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"WS Listen Error: {e}")

        async def send_to_frontend():
            log_counter = 0
            try:
                while True:
                    data = event_bus.get_stream_data()
                    if data:
                        # === [DEBUG] ВСТАВИТЬ ЭТОТ БЛОК ===
                        log_counter += 1
                        if log_counter % 30 == 0:
                            try:
                                results = data.get("results", {})
                                vision = results.get("vision", {})
                                points = vision.get("keypoints", [])

                                count = len(points)
                                # if count > 0:
                                    # [FIX] logger.success -> logger.info
                                    # logger.info(f"📡 WS sending: {count} points (Frame {data.get('frame_id')})")
                                # else:
                                #     logger.warning(f"📡 WS sending: 0 points")
                            except Exception as e:
                                logger.error(f"Debug logger error: {e}")
                        # ==================================
                        packet_window.append(data)
                        await websocket.send_json(jsonable_encoder(list(packet_window)))
                    else:
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

    vid_configs = {0: shm_config}
    try:
        from src.to_del.storage import CalibrationStorage
        storage = CalibrationStorage("bikefit_db.json")
    except ImportError:
        storage = None

    app = create_app(event_bus=bus, storage=storage, vid_configs=vid_configs)

    config = Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
    server = Server(config)
    server.run()