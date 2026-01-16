import sys
import subprocess


def get_usb_devices_linux():
    # Попробуем самый универсальный способ для Linux - lsusb
    try:
        print("--- LSUSB ---")
        res = subprocess.check_output(['lsusb'], text=True)
        print(res)
    except Exception as e:
        print(f"lsusb error: {e}")

    # Попробуем v4l2-ctl если есть
    try:
        print("\n--- V4L2 Devices ---")
        res = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True)
        print(res)
    except Exception as e:
        print(f"v4l2 error: {e}")

    # Если ты на macOS (судя по uvc-util)
    if sys.platform == 'darwin':
        try:
            print("\n--- System Profiler (macOS) ---")
            # Это аналог диспетчера устройств
            res = subprocess.check_output(['system_profiler', 'SPCameraDataType'], text=True)
            print(res)
        except Exception as e:
            print(f"system_profiler error: {e}")


if __name__ == "__main__":
    get_usb_devices_linux()