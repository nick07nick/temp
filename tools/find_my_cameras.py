# tools/find_my_cameras.py
import sys
from pathlib import Path

# Добавляем корень проекта в путь, чтобы видеть src
sys.path.append(str(Path(__file__).parent.parent))

from src.core.device_manager import device_manager
from loguru import logger


def main():
    logger.info("🕵️‍♂️ Scanning cameras...")
    device_manager.scan_devices()

    print("\n" + "=" * 50)
    print("📸 FOUND CAMERAS (Copy ID to config.py)")
    print("=" * 50)

    if not device_manager._devices_map:
        print("❌ No cameras found!")

    for uid, idx in device_manager._devices_map.items():
        print(f"✅ OpenCV Index: {idx}")
        print(f"🔑 ID to copy:   {uid}")
        print("-" * 30)

    print("\nCopy the 'ID to copy' string into src/core/config.py -> CAMERAS dict.")


if __name__ == "__main__":
    main()