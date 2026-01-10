# src/tools/cam_exposure.py
import subprocess
import sys
import time
from pathlib import Path

# === ПУТЬ К УТИЛИТЕ ===
# Беру из твоих логов, проверь, если что
UVC_PATH = Path("/Users/nikfrants/Documents/it/BikeFit/uvc-util/src/uvc-util")
DEVICE_INDEX = "0"


def run_cmd(args):
    """Просто запускает команду и печатает результат"""
    if not UVC_PATH.exists():
        print(f"❌ Файл не найден: {UVC_PATH}")
        return False

    cmd = [str(UVC_PATH), "-I", DEVICE_INDEX] + args
    print(f"💻 Выполняю: {' '.join(cmd)}")

    try:
        # Запускаем и ждем
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.stdout.strip():
            print(f"🟢 STDOUT: {res.stdout.strip()}")
        if res.stderr.strip():
            print(f"🔴 STDERR: {res.stderr.strip()}")

        return res.returncode == 0
    except Exception as e:
        print(f"❌ Ошибка Python: {e}")
        return False


def main():
    print("=== РУЧНОЙ ТЕСТ ЭКСПОЗИЦИИ ===")
    print(f"Утилита: {UVC_PATH}")

    # 1. Сначала принудительно Manual Mode
    print("\n1. Включаю ручной режим (auto-exposure-mode=1)...")
    if run_cmd(["-s", "auto-exposure-mode=1"]):
        print("✅ Ручной режим включен.")
    else:
        print("⚠️ Не удалось включить ручной режим. Попробуем продолжить...")

    print("\n---------------------------------------------------")
    print("Вводи значения экспозиции (например: 10, 100, 500, 5000).")
    print("Для выхода нажми Ctrl+C или введи 'q'.")
    print("---------------------------------------------------")

    while True:
        try:
            user_input = input("\n👉 Введи exposure-time-abs: ").strip()

            if user_input.lower() in ['q', 'exit', 'quit']:
                print("Пока!")
                break

            if not user_input.isdigit():
                print("❌ Введи целое число!")
                continue

            # 2. Отправляем значение
            val = int(user_input)
            run_cmd(["-s", f"exposure-time-abs={val}"])

            # Можно сразу прочитать обратно, чтобы убедиться
            # run_cmd(["-o", "exposure-time-abs"])

        except KeyboardInterrupt:
            print("\nВыход.")
            break


if __name__ == "__main__":
    main()