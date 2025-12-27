# src/api/server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import logging

from src.core.event_bus import EventBus
from src.core.storage import CalibrationStorage

logger = logging.getLogger("BikeFit.API")

class WorkspaceSwitchRequest(BaseModel):
    name: str

def create_app(event_bus: EventBus, storage: CalibrationStorage):
    app = FastAPI(title="BikeFit Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/workspaces")
    async def get_workspaces():
        return {"workspaces": storage.list_workspaces()}

    @app.post("/workspaces/active")
    async def set_active_workspace(req: WorkspaceSwitchRequest):
        event_bus.send_command("SET_WORKSPACE", req.name)
        return {"status": "ok", "message": f"Switching to {req.name}"}

    @app.websocket("/ws/stream")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("Client connected to WebSocket")
        try:
            while True:
                data = None
                while data is None:
                    data = event_bus.get_stream_data()
                    if data is None:
                        await asyncio.sleep(0.01)
                await websocket.send_json(data)
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"WS Error: {e}")

    return app