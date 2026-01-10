# src/tools/check_camera_control.py
import subprocess
import re
from pathlib import Path

# Путь к бинарнику
PROJECT_ROOT = Path(__file__).parent.parent
UVC_BIN = PROJECT_ROOT / "uvc-util" / "src" / "uvc-util"


def run_uvc(args):
    """Обертка для запуска uvc-util"""
    cmd = [str(UVC_BIN)] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def main():
    if not UVC_BIN.exists():
        print(f"❌ Бинарник не найден: {UVC_BIN}")
        return

    print(f"🚀 Запуск диагностики через: {UVC_BIN}")

    # 1. Список устройств (-d согласно help)
    print("\n--- 1. Поиск устройств ---")
    devices_output = run_uvc(["-d"])
    print(devices_output)

    # Пытаемся найти индексы устройств (обычно формат "0: DeviceName" или "[0]")
    # Ищем цифры в начале строк
    indices = re.findall(r'^\[?(\d+)\]?', devices_output, re.MULTILINE)

    if not indices:
        print("\n⚠️ Не удалось автоматически определить индексы из вывода. Пробую индекс '0' наугад.")
        indices = ['0']

    # 2. Полный опрос каждой камеры
    for idx in indices:
        print(f"\n{'=' * 40}")
        print(f"📷 КАМЕРА INDEX: {idx}")
        print(f"{'=' * 40}")

        # Список доступных контролов (-c)
        print(f"\n--- Список контролов (Simple List) ---")
        controls = run_uvc(["-I", idx, "-c"])
        print(controls)

        # Полная спецификация возможностей (-S *)
        # Это даст min, max, step и default для всех настроек сразу
        print(f"\n--- Полные возможности (Details) ---")
        details = run_uvc(["-I", idx, "-S", "*"])
        print(details)


if __name__ == "__main__":
    main()