# src/api/server.py
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import logging
import cv2
import numpy as np
import time
import struct
import json  # <--- ИМПОРТ JSON
from typing import Dict, Optional

from src.core.event_bus import EventBus
from src.core.storage import CalibrationStorage
from src.core.shared_memory import SharedMemoryManager, VideoFrameLayout, RingBufferLayout
from src.core.models import SharedMemoryConfig

logger = logging.getLogger("BikeFit.API")


class WorkspaceSwitchRequest(BaseModel):
    name: str


class CameraConfigRequest(BaseModel):
    threshold: int
    exposure: int


video_managers: Dict[int, SharedMemoryManager] = {}
video_configs_store: Dict[int, SharedMemoryConfig] = {}


def create_app(event_bus: EventBus, storage: CalibrationStorage, vid_configs: dict = None):
    app = FastAPI(title="BikeFit Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if vid_configs:
        global video_configs_store
        video_configs_store = vid_configs

    def get_video_manager(cam_id: int):
        if cam_id in video_managers:
            mgr = video_managers[cam_id]
            if mgr.shm is not None:
                return mgr

        if cam_id not in video_configs_store: return None
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
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        placeholder = np.zeros((600, 800, 3), dtype=np.uint8)
        cv2.putText(placeholder, "WAITING FOR SYNC...", (150, 300),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        _, ph_bytes = cv2.imencode('.jpg', placeholder, encode_param)

        last_frame_id = -1

        while True:
            mgr = get_video_manager(cam_id)
            frame_data = None
            current_fid = 0

            if mgr and mgr.shm:
                try:
                    cfg = video_configs_store[cam_id]
                    head_idx = RingBufferLayout.get_write_index(mgr.shm.buf)
                    slot_view = RingBufferLayout.get_slot_view(mgr.shm.buf, head_idx, mgr.slot_size)
                    fid, ts, frame = VideoFrameLayout.parse_from_buf(
                        slot_view,
                        cfg.shape,
                        cfg.dtype
                    )

                    if fid > last_frame_id:
                        ret, jpg = cv2.imencode('.jpg', frame, encode_param)
                        if ret:
                            frame_data = jpg.tobytes()
                            current_fid = fid
                            last_frame_id = fid
                except Exception:
                    video_managers.pop(cam_id, None)

            if frame_data is not None:
                header = struct.pack('<QI', current_fid, len(frame_data))
                yield header + frame_data
            else:
                time.sleep(0.01)
                continue

            time.sleep(0.015)

    @app.get("/video_feed/{cam_id}")
    async def video_feed(cam_id: int):
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

    @app.websocket("/ws/stream")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        packet_window = deque(maxlen=3)

        # 1. ЗАДАЧА: Слушаем команды от фронта
        async def listen_to_frontend():
            try:
                while True:
                    raw_msg = await websocket.receive_text()
                    try:
                        msg = json.loads(raw_msg)
                        target = msg.get("target")
                        payload = msg.get("payload", {})

                        if target:
                            # Распаковываем payload, чтобы достать cmd и args
                            cmd = payload.get("cmd")
                            args = payload.get("args")

                            # Отправляем в шину
                            event_bus.send_plugin_command(target, cmd, args)
                            # logger.info(f"Frontend command -> {target}: {cmd}")

                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from frontend")
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"WS Listen Error: {e}")

        # 2. ЗАДАЧА: Шлем данные на фронт
        async def send_to_frontend():
            try:
                while True:
                    data = event_bus.get_stream_data()
                    if data:
                        packet_window.append(data)
                        await websocket.send_json(list(packet_window))
                    else:
                        await asyncio.sleep(0.005)

                    if websocket.client_state.name == "DISCONNECTED":
                        break
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"WS Send Error: {e}")

        # Запускаем параллельно
        await asyncio.gather(listen_to_frontend(), send_to_frontend())

    return app


def run_server(bus: EventBus, shm_config: SharedMemoryConfig):
    from uvicorn import Config, Server
    vid_configs = {0: shm_config}
    storage = CalibrationStorage("bikefit_db.json")
    app = create_app(event_bus=bus, storage=storage, vid_configs=vid_configs)

    config = Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
    server = Server(config)
    server.run()