# src/core/storage.py
import json
import os
import logging
from typing import List, Dict, Optional
from src.data.models import CameraIntrinsics, WorkspaceProfile

logger = logging.getLogger("BikeFit.Storage")


class CalibrationStorage:
    """
    Отвечает за сохранение и загрузку профилей (JSON файл).
    В будущем это заменится на SQLite или API вызов.
    """

    def __init__(self, filepath: str = "calibration_db.json"):
        self.filepath = filepath
        self._intrinsics: Dict[str, CameraIntrinsics] = {}
        self._workspaces: Dict[str, WorkspaceProfile] = {}
        self._load_db()

    def _load_db(self):
        if not os.path.exists(self.filepath):
            logger.info("Database file not found. Starting fresh.")
            return

        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)

            for item in data.get("intrinsics", []):
                prof = CameraIntrinsics(**item)
                self._intrinsics[prof.name] = prof

            for item in data.get("workspaces", []):
                ws = WorkspaceProfile(**item)
                self._workspaces[ws.name] = ws

            logger.info(f"Loaded {len(self._intrinsics)} lens profiles and {len(self._workspaces)} workspaces.")
        except Exception as e:
            logger.error(f"Failed to load DB: {e}")

    def save_db(self):
        data = {
            "intrinsics": [p.model_dump() for p in self._intrinsics.values()],
            "workspaces": [w.model_dump() for w in self._workspaces.values()]
        }
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Database saved.")

    # --- API ---
    def add_intrinsic(self, profile: CameraIntrinsics):
        self._intrinsics[profile.name] = profile
        self.save_db()

    def add_workspace(self, workspace: WorkspaceProfile):
        self._workspaces[workspace.name] = workspace
        self.save_db()

    def get_workspace(self, name: str) -> Optional[WorkspaceProfile]:
        return self._workspaces.get(name)

    def get_intrinsic(self, name: str) -> Optional[CameraIntrinsics]:
        return self._intrinsics.get(name)

    def list_workspaces(self) -> List[str]:
        return list(self._workspaces.keys())