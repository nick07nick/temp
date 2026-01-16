# src/core/device_manager.py
import sys
import subprocess
import re
from typing import Dict, Optional, List
from loguru import logger
from src.core.config import ROOT_DIR, settings


class DeviceManager:
    def __init__(self):
        # Словарь: { "SERIAL_OR_UID": opencv_index }
        self._devices_map: Dict[str, int] = {}
        self.uvc_util_path = ROOT_DIR / "uvc-util/src/uvc-util"
        if not self.uvc_util_path.exists():
            self.uvc_util_path = ROOT_DIR / "uvc-util/uvc-util"

    def scan_devices(self):
        """
        Сканирует USB-шину и обновляет карту устройств.
        """
        self._devices_map.clear()
        sys_platform = sys.platform

        if sys_platform == 'darwin':
            self._scan_macos()
        elif sys_platform == 'win32':
            self._scan_windows()
        else:
            logger.warning("Linux scanning not implemented fully yet.")

        logger.info(f"🔎 Device Scan Complete. Found: {self._devices_map}")

    def get_camera_index_by_serial(self, target_serial: str) -> Optional[int]:
        """
        Ищет индекс камеры по Serial Number / Hardware ID.
        """
        # 1. Точное совпадение
        if target_serial in self._devices_map:
            return self._devices_map[target_serial]

        # 2. Частичное совпадение (если serial длинный)
        for dev_id, idx in self._devices_map.items():
            if target_serial in dev_id or dev_id in target_serial:
                logger.warning(f"⚠️ Exact Serial match failed, using partial: {dev_id} -> {target_serial}")
                return idx

        return None

    def _scan_macos(self):
        """Парсинг вывода uvc-util для macOS"""
        if not self.uvc_util_path.exists():
            logger.error(f"uvc-util not found at {self.uvc_util_path}")
            return

        try:
            # uvc-util --list-devices выводит: Index, Vend:Prod, LocationID, Serial?
            # Нам нужен Unique ID. Обычно это LocationID или Serial.
            result = subprocess.check_output([str(self.uvc_util_path), '--list-devices'], text=True)
            lines = result.strip().split('\n')

            for line in lines:
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue

                parts = line.split()
                if len(parts) >= 3:
                    try:
                        idx = int(parts[0])
                        # В текущей версии uvc-util 3-й столбец - LocationID (Unique for port)
                        loc_id = parts[2]
                        self._devices_map[loc_id] = idx
                        # TODO: Если uvc-util поддерживает вывод Serial, парсить и его
                    except ValueError:
                        pass

        except Exception as e:
            logger.error(f"MacOS Scan Error: {e}")

    def _scan_windows(self):
        """
        Парсинг через PowerShell (WMI) для Windows.
        """
        try:
            # Получаем PNPDeviceID, который содержит VID, PID и Serial
            cmd = "Get-PnpDevice -Class Camera -Status OK | Select-Object -ExpandProperty PNPDeviceID"
            result = subprocess.check_output(["powershell", "-Command", cmd], text=True)
            ids = [line.strip() for line in result.split('\n') if line.strip()]

            for idx, pnp_id in enumerate(ids):
                # pnp_id пример: USB\VID_046D&PID_0825\6F7F2D2F
                # Последняя часть часто является серийником или уникальным ID
                self._devices_map[pnp_id] = idx

                # Попробуем извлечь чистый серийник (после последнего слэша)
                if "\\" in pnp_id:
                    clean_serial = pnp_id.split("\\")[-1]
                    self._devices_map[clean_serial] = idx

        except Exception as e:
            logger.error(f"Windows Scan Error: {e}")


# Синглтон
device_manager = DeviceManager()