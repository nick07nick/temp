# src/core/orchestrator.py
import time
import threading
import multiprocessing
from typing import Dict, List, Callable, Set, Optional
from loguru import logger

from src.core.config import settings
from src.core.event_bus import EventBus
from src.data.models import SharedMemoryConfig
from src.core.device_manager import device_manager
from src.hardware.camera_worker import run_camera_worker


# === SECURITY LAYER ===
class DevCryptoProvider:
    def check_license(self) -> bool:
        time.sleep(0.002)
        return True

    def get_math_salt(self) -> float:
        return 1.0 + (time.time() % 10.0) / 100.0


class SecurityController(threading.Thread):
    def __init__(self, broadcast_callback: Callable[[str, dict], None]):
        super().__init__(daemon=True, name="SecController")
        self.broadcast = broadcast_callback
        self.crypto = DevCryptoProvider()
        self._running = False
        self._last_salt_update = 0.0

    def run(self):
        self._running = True
        logger.info("🛡️ Security Controller started.")
        while self._running:
            t0 = time.perf_counter()
            if not self.crypto.check_license():
                logger.critical("🚫 LICENSE CHECK FAILED! System locked.")
                self.broadcast("SECURITY_LOCK", {"reason": "License fail"})
                break

            if time.time() - self._last_salt_update > settings.PROFILE.math_salt_interval:
                new_salt = self.crypto.get_math_salt()
                self.broadcast("SET_SALT", {"value": new_salt})
                self._last_salt_update = time.time()
            time.sleep(1.0)

    def stop(self):
        self._running = False


# === ORCHESTRATOR ===
class ProcessorOrchestrator:
    # [FIX 1] Добавил manager в конструктор
    def __init__(self, bus: EventBus, manager):
        self.bus = bus
        self.manager = manager  # [FIX 2] Сохранил ссылку
        self._workers: Dict[int, Dict] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self.security = SecurityController(broadcast_callback=self._broadcast_command_internal)
        self._system_state = {"cameras": {}, "global_fps": 0.0, "security_status": "ok"}
        self._lock = threading.Lock()

        # Реестр занятых ресурсов: { phys_index: logical_role_id }
        self._allocated_devices: Dict[int, int] = {}

    def start(self):
        """Запуск системы с умным распределением ресурсов"""
        logger.info("🧠 Orchestrator starting...")
        self._running = True

        # 1. Сканируем железо
        device_manager.scan_devices()
        logger.info(f"🔎 Available Devices: {device_manager._devices_map}")

        # 2. Аллокация ресурсов (кто какую камеру берет)
        self._allocate_resources()

        # 3. Запуск процессов (только для тех, кому досталось железо)
        cameras = settings.PROFILE.cameras
        started_count = 0

        if not cameras:
            logger.warning("⚠️ No cameras in profile. Starting Mock/Legacy Worker-0.")
            # Для мока (без реальной камеры) передаем индекс 0 или None
            self._spawn_worker(0, device_index=0)
        else:
            for role_key, cam_profile in cameras.items():
                if not cam_profile.enabled:
                    continue

                # Ищем, какой физический индекс был выделен для этой роли
                # _allocated_devices хранит { phys_index: role_id }
                # Нам нужно найти индекс по role_id
                assigned_index = None
                for idx, r_id in self._allocated_devices.items():
                    if r_id == cam_profile.role_id:
                        assigned_index = idx
                        break

                if assigned_index is not None:
                    # [NEW] Передаем явный индекс устройства
                    self._spawn_worker(cam_profile.role_id, device_index=assigned_index)
                    started_count += 1
                else:
                    logger.warning(
                        f"⛔ Skipping {cam_profile.role_name} (ID {cam_profile.role_id}): No available physical device or conflict.")

            logger.info(f"🚀 Launched {started_count} camera workers.")

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="OrchestratorMonitor")
        self._monitor_thread.start()
        self.security.start()
        logger.success("✅ System started & Secured.")

    def stop(self):
        logger.info("🛑 Orchestrator stopping...")
        self._running = False
        self.security.stop()

        for cam_id, info in self._workers.items():
            self._kill_process(info['proc'])
            logger.info(f"Worker-{cam_id} stopped.")

        self._workers.clear()

    # --- Resource Management ---
    def _allocate_resources(self):
        """
        Распределяет физические индексы камер между логическими ролями.
        Гарантирует, что один индекс не будет использован дважды.
        """
        self._allocated_devices.clear()
        used_indices: Set[int] = set()

        # Сортируем роли по ID, чтобы 0 (Side) имел приоритет над 1 (Front)
        sorted_profiles = sorted(settings.PROFILE.cameras.values(), key=lambda x: x.role_id)

        for profile in sorted_profiles:
            if not profile.enabled:
                continue

            target_serial = profile.serial_number
            found_idx = device_manager.get_camera_index_by_serial(target_serial)

            final_idx = None

            # Стратегия 1: Нашли по серийнику
            if found_idx is not None:
                if found_idx not in used_indices:
                    final_idx = found_idx
                    logger.success(f"✅ Allocating {profile.role_name} -> Physical Index {final_idx} (Serial Match)")
                else:
                    logger.error(
                        f"❌ Conflict: Serial {target_serial} points to Index {found_idx}, which is ALREADY BUSY.")

            # Стратегия 2: Fallback (если серийник не найден или занят)
            if final_idx is None:
                if profile.role_id == 0 and 0 not in used_indices:
                    logger.warning(f"⚠️ Fallback: {profile.role_name} taking Index 0 (Dev Mode)")
                    final_idx = 0
                else:
                    logger.error(f"❌ Could not allocate device for {profile.role_name}. Skipped.")
                    continue

            # Фиксация
            if final_idx is not None:
                self._allocated_devices[final_idx] = profile.role_id
                used_indices.add(final_idx)

    # --- Worker Management ---
    def _spawn_worker(self, camera_id: int, device_index: int):
        """
        Запускает воркера для указанной роли (camera_id) на указанном устройстве (device_index).
        """
        shm_name = f"shm_cam_{camera_id}"
        shm_config = SharedMemoryConfig(
            name=shm_name,
            size=0,
            shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
            dtype="uint8"
        )

        # [FIX 3] Передаю self.manager в метод регистрации
        self.bus.register_worker(camera_id, self.manager)

        # [NEW] Передаем device_index в аргументы процесса
        proc = multiprocessing.Process(
            target=run_camera_worker,
            args=(camera_id, shm_config, self.bus, device_index),  # <-- [CHANGED] Добавил device_index
            name=f"Worker-{camera_id}",
            daemon=True
        )
        proc.start()

        self._workers[camera_id] = {
            "proc": proc,
            "last_beat": time.time(),
            "shm_config": shm_config,
            "restarts": 0,
            "device_index": device_index  # Запоминаем, на каком устройстве висит
        }
        logger.info(f"👶 Spawned Worker-{camera_id} (PID: {proc.pid}) on Device {device_index}")

    def _kill_process(self, proc):
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
            if proc.is_alive():
                proc.kill()

    def _restart_worker(self, camera_id: int):
        logger.warning(f"♻️ Restarting Worker-{camera_id}...")

        old_info = self._workers.get(camera_id)
        current_device_index = old_info.get("device_index", 0) if old_info else 0

        if old_info:
            self._kill_process(old_info['proc'])

            # SHM Cleanup
            shm_name = f"shm_cam_{camera_id}"
            try:
                from multiprocessing.shared_memory import SharedMemory
                existing_shm = SharedMemory(name=shm_name)
                existing_shm.close()
                existing_shm.unlink()
            except:
                pass

        # [SMART RECOVERY] Перед перезапуском проверим, не уехала ли камера
        # Если это рестарт из-за зависания, возможно USB порт сменился
        # Поэтому делаем быстрый перескан
        logger.info("🔄 Rescanning devices before restart...")
        device_manager.scan_devices()

        # Пытаемся найти новый индекс для этой роли
        # Берем серийник из профиля
        target_serial = settings.PROFILE.cameras[f"cam_{camera_id}"].serial_number \
            if f"cam_{camera_id}" in settings.PROFILE.cameras else None

        new_index = None
        if target_serial:
            new_index = device_manager.get_camera_index_by_serial(target_serial)

        # Если нашли новый индекс - используем его
        if new_index is not None:
            if new_index != current_device_index:
                logger.warning(f"🔀 Device Moved! {current_device_index} -> {new_index}")
            current_device_index = new_index
        else:
            logger.warning(
                f"⚠️ Device for Cam {camera_id} not found by serial. Trying old index {current_device_index}")

        # Перезапускаем с (возможно новым) индексом
        self._spawn_worker(camera_id, device_index=current_device_index)

        if old_info:
            self._workers[camera_id]['restarts'] = old_info.get('restarts', 0) + 1

    # --- Monitoring Loop ---
    def _monitor_loop(self):
        last_broadcast = 0.0
        while self._running:
            # 1. Читаем сообщения от воркеров (Heartbeats, Errors)
            while True:
                msg = self.bus.get_updates()
                if not msg: break
                self._handle_message(msg)

            # 2. Проверяем здоровье (Restart dead workers)
            self._check_health()

            # 3. [NEW] Рассылаем глобальное состояние (1 Hz)
            if time.time() - last_broadcast > 1.0:
                with self._lock:
                    active_cameras = {}
                    for cam_id, info in self._workers.items():
                        cam_data = self._system_state["cameras"].get(cam_id, {})
                        if not cam_data:
                            cam_data = {
                                "camera_id": cam_id,
                                "role": f"Camera {cam_id}",
                                "status": "starting"
                            }
                        # !!! FIX: JSON требует строковые ключи !!!
                        active_cameras[str(cam_id)] = cam_data

                    payload = {
                        "cameras": active_cameras,
                        "global_fps": 0,
                        "security": "ok"
                    }

                # !!! FIX: Шлем в API через отдельный канал !!!
                self.bus.publish_to_api("system_monitor", payload)
                last_broadcast = time.time()

            time.sleep(0.01)

    def _handle_message(self, msg: Dict):
        m_type = msg.get("type")
        payload = msg.get("payload", {})

        if m_type == "heartbeat":
            cid = payload.get("camera_id")
            if cid is not None and cid in self._workers:
                self._workers[cid]["last_beat"] = time.time()

                # [FIX] Сохраняем payload (где лежат role, config, fps) в system_state
                with self._lock:
                    self._system_state["cameras"][cid] = payload

        elif m_type == "stream_data":
            # cid = payload.get("camera_id")
            # if cid is not None:
            #     with self._lock: self._system_state["cameras"][cid] = payload
            pass

        elif m_type == "command":
            target = payload.get("target")
            cmd = payload.get("cmd")
            args = payload.get("args")

            if target == "system":
                pass
            elif isinstance(target, str) and target.startswith("camera_"):
                try:
                    cam_id = int(target.split("_")[1])
                    self.send_command_to_camera(cam_id, cmd, args)
                except:
                    logger.error(f"Invalid target: {target}")
            else:
                self.send_command_to_camera(-1, cmd, args, target=target)

    def _check_health(self):
        now = time.time()
        for cam_id, info in list(self._workers.items()):
            proc = info['proc']
            last_beat = info['last_beat']

            if not proc.is_alive():
                logger.critical(f"💀 Worker-{cam_id} DIED.")
                self._restart_worker(cam_id)
                continue

            if now - last_beat > 5.0:
                logger.error(f"❄️ Worker-{cam_id} FROZEN (No Heartbeat > 5s).")
                self._restart_worker(cam_id)

    def _broadcast_command_internal(self, cmd: str, args: dict):
        self.send_command_to_camera(-1, cmd, args, target="system")

    def send_command_to_camera(self, camera_id: int, command: str, args: dict = None, target: str = None):
        target_to_use = target if target is not None else "system"
        payload = {"target": target_to_use, "cmd": command, "args": args or {}}
        if camera_id == -1:
            for cid in list(self._workers.keys()):
                self.bus.send_command(cid, payload)
        else:
            self.bus.send_command(camera_id, payload)

    def get_system_state(self) -> Dict:
        with self._lock: return self._system_state.copy()