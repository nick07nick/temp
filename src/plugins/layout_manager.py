# src/plugins/layout_manager.py
import json
from typing import Dict, Any, List
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

# === 1. НАСТРОЙКИ ПУТЕЙ ===
current_file = Path(__file__).resolve()
try:
    src_index = current_file.parts.index('src')
    ROOT_DIR = Path(*current_file.parts[:src_index])
except ValueError:
    ROOT_DIR = current_file.parent.parent.parent

DATA_DIR = ROOT_DIR / "user_data"
LAYOUTS_FILE = DATA_DIR / "layouts.json"

# === 2. МОДЕЛИ ДАННЫХ (Для API) ===
class LayoutModel(BaseModel):
    name: str
    data: List[Dict[str, Any]]

# === 3. ЛОГИКА (Твой класс) ===
class LayoutManager:
    def __init__(self):
        self._ensure_dir()
        self._cache: Dict[str, Any] = self._load_from_disk()

    def _ensure_dir(self):
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not LAYOUTS_FILE.exists():
            with open(LAYOUTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f)

    def _load_from_disk(self) -> Dict[str, Any]:
        try:
            with open(LAYOUTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_to_disk(self):
        with open(LAYOUTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._cache, f, indent=2, ensure_ascii=False)

    def get_all_layouts(self) -> Dict[str, Any]:
        self._cache = self._load_from_disk()
        return self._cache

    def save_layout(self, name: str, layout_data: Any):
        self._cache[name] = layout_data
        self._save_to_disk()

    def delete_layout(self, name: str):
        if name in self._cache:
            del self._cache[name]
            self._save_to_disk()

# Экземпляр логики
layout_manager = LayoutManager()

# === 4. ROUTER (ВОТ ЧТО ПРОПУЩЕНО!) ===
# Именно этот объект ищет loader.py
router = APIRouter(prefix="/api/layouts", tags=["layouts"])

@router.get("")
async def get_layouts():
    return layout_manager.get_all_layouts()

@router.post("")
async def save_layout(layout: LayoutModel):
    layout_manager.save_layout(layout.name, layout.data)
    return {"status": "ok", "message": f"Layout '{layout.name}' saved"}

@router.delete("/{name}")
async def delete_layout(name: str):
    layout_manager.delete_layout(name)
    return {"status": "ok", "message": f"Layout '{name}' deleted"}