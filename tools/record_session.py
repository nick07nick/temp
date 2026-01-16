import sys
import time
from pathlib import Path

# Добавляем корень в путь
sys.path.append(str(Path(__file__).parent.parent))

from src.core.recorder import SessionRecorder
from src.core.config import settings
from loguru import logger


def main():
    print("=" * 40)
    print("🎥 BikeFit Motion Recorder Tool")
    print("=" * 40)
    print("NOTE: Этот инструмент пытается подключиться к памяти камеры.")
    print("Убедитесь, что main.py запущен.")

    # Пытаемся угадать имя памяти (пока хардкод для теста первой камеры)
    # В будущем здесь будет список доступных SHM каналов
    # Имя должно совпадать с тем, что генерирует воркер: "camera_side_buffer_TIMESTAMP"
    # СЕЙЧАС ЭТО ПРОБЛЕМА: Имя динамическое.
    # РЕШЕНИЕ: Для тестов записи временно отключите timestamp в camera_worker.py
    # или скопируйте имя из логов main.py сюда.

    shm_name = input(f"Enter SHM Name (default: {settings.SHM_CAMERA_BUFFER_NAME}): ").strip()
    if not shm_name:
        shm_name = settings.SHM_CAMERA_BUFFER_NAME

    print(f"Targeting SHM: {shm_name}")
    print("Press ENTER to start recording...")
    input()

    # Генерируем имя файла
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = settings.DATA_DIR / "sessions" / f"session_{timestamp}.bfm"

    recorder = SessionRecorder(str(filename), shm_name=shm_name)
    recorder.start()

    print(f"🔴 RECORDING... ({filename})")
    print("Press CTRL+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        recorder.stop()
        print("Done!")


if __name__ == "__main__":
    main()