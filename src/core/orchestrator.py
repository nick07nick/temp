# src/core/orchestrator.py
import time
import threading
import multiprocessing
from typing import Dict, Optional, List, Callable
from loguru import logger

from src.core.config import settings
from src.core.event_bus import EventBus
from src.data.models import SharedMemoryConfig
# Импортируем функцию запуска воркера (будет обновлена на след. этапе)
from src.hardware.camera_worker import run_camera_worker


# === SECURITY LAYER (Внутренний класс) ===

class DevCryptoProvider:
    """
    Заглушка для эмуляции USB-ключа (Hardware Layer).
    В продакшене заменяется на реальный драйвер ключа.
    """

    def check_license(self) -> bool:
        # Эмуляция проверки: всегда True, но с небольшой задержкой
        time.sleep(0.002)
        return True

    def get_math_salt(self) -> float:
        # Генерация "случайного" множителя для защиты памяти
        # В реальности зависит от внутреннего таймера ключа
        return 1.0 + (time.time() % 10.0) / 100.0  # Пример: 1.05


class SecurityController(threading.Thread):
    """
    Контроллер безопасности.
    Работает в отдельном потоке внутри Оркестратора.
    Обязанности:
    1. Watchdog лицензии (защита от сетевого шеринга ключа).
    2. Генерация Math Salt для воркеров.
    """

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
            # 1. Latency Watchdog (Проверка задержки ключа)
            t0 = time.perf_counter()
            if not self.crypto.check_license():
                logger.critical("🚫 LICENSE CHECK FAILED! System locked.")
                self.broadcast("SECURITY_LOCK", {"reason": "License fail"})
                break

            dt_ms = (time.perf_counter() - t0) * 1000
            if dt_ms > 50.0:
                logger.warning(f"⚠️ Slow Security Key response: {dt_ms:.1f}ms (Possible emulator attack)")

            # 2. Обновление Math Salt (Раз в 5 секунд)
            # Это число воркеры будут использовать для умножения координат
            if time.time() - self._last_salt_update > 5.0:
                new_salt = self.crypto.get_math_salt()

                # Рассылаем всем воркерам команду: "Обновить соль"
                self.broadcast("SET_SALT", {"value": new_salt})

                self._last_salt_update = time.time()
                # logger.debug(f"🧂 Secure Salt updated: {new_salt:.4f}")

            time.sleep(1.0)  # Проверка лицензии раз в секунду

    def stop(self):
        self._running = False


# === ORCHESTRATOR ===

class ProcessorOrchestrator:
    """
    Главный управляющий процесс (Brain).
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._workers: Dict[int, Dict] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        # Инициализация контроллера безопасности
        # Передаем ему метод отправки команд всем камерам
        self.security = SecurityController(broadcast_callback=self._broadcast_command_internal)

        # Глобальное состояние системы
        self._system_state = {
            "cameras": {},
            "global_fps": 0.0,
            "security_status": "ok"
        }
        self._lock = threading.Lock()

    def start(self):
        """Запуск системы"""
        logger.info("🧠 Orchestrator starting...")
        self._running = True

        # 1. Запуск воркеров (пока берем из конфига)
        active_cameras = [settings.CAMERA_INDEX]
        # Если нужно больше: list(range(4))

        for cam_id in active_cameras:
            self._spawn_worker(cam_id)

        # 2. Запуск мониторинга
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="OrchestratorMonitor")
        self._monitor_thread.start()

        # 3. Запуск безопасности
        self.security.start()

        logger.success("✅ System started & Secured.")

    def stop(self):
        """Остановка"""
        logger.info("🛑 Orchestrator stopping...")
        self._running = False
        self.security.stop()

        # Kill workers
        for cam_id, info in self._workers.items():
            self._kill_process(info['proc'])
            logger.info(f"Worker-{cam_id} stopped.")

        self._workers.clear()

    # --- Worker Management ---

    def _spawn_worker(self, camera_id: int):
        # 1. Конфиг памяти (Размер считается внутри Manager'а)
        shm_name = f"shm_cam_{camera_id}"
        shm_config = SharedMemoryConfig(
            name=shm_name,
            size=0,
            shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
            dtype="uint8"
        )

        # 2. Регистрируем очередь
        self.bus.register_worker(camera_id)

        # 3. Старт процесса
        proc = multiprocessing.Process(
            target=run_camera_worker,
            args=(camera_id, shm_config, self.bus),
            name=f"Worker-{camera_id}",
            daemon=True
        )
        proc.start()

        self._workers[camera_id] = {
            "proc": proc,
            "last_beat": time.time(),
            "shm_config": shm_config,
            "restarts": 0
        }
        logger.info(f"👶 Spawned Worker-{camera_id} (PID: {proc.pid})")

    def _kill_process(self, proc):
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
            if proc.is_alive():
                proc.kill()

    def _restart_worker(self, camera_id: int):
        logger.warning(f"♻️ Restarting Worker-{camera_id}...")
        old_proc = self._workers[camera_id]['proc']
        self._kill_process(old_proc)
        self._spawn_worker(camera_id)
        self._workers[camera_id]['restarts'] += 1

    # --- Monitoring Loop ---

    def _monitor_loop(self):
        while self._running:
            # 1. Обработка входящих сообщений
            while True:
                msg = self.bus.get_updates()
                if not msg:
                    break
                self._handle_message(msg)

            # 2. Watchdog
            self._check_health()

            # Частота цикла
            time.sleep(0.01)

    def _handle_message(self, msg: Dict):
        m_type = msg.get("type")
        payload = msg.get("payload", {})

        if m_type == "heartbeat":
            cid = payload.get("camera_id")
            if cid is not None and cid in self._workers:
                self._workers[cid]["last_beat"] = time.time()

        elif m_type == "stream_data":
            cid = payload.get("camera_id")
            if cid is not None:
                with self._lock:
                    self._system_state["cameras"][cid] = payload

        elif m_type == "command":
            target = payload.get("target")
            cmd = payload.get("cmd")
            args = payload.get("args")

            # logger.info(f"🎯 Orchestrator received command: target='{target}', cmd='{cmd}', args={args}")

            # Логика маршрутизации
            if target == "system":
                logger.info(f"🖥️ System command: {cmd} {args}")
                pass

            elif isinstance(target, str) and target.startswith("camera_"):
                # Парсим ID: "camera_0" -> 0
                try:
                    cam_id = int(target.split("_")[1])
                    self.send_command_to_camera(cam_id, cmd, args)
                except (ValueError, IndexError):
                    logger.error(f"Invalid camera target: {target}")

            else:
                # Если target непонятный (например 'counter', 'blob_detector') - шлем всем камерам
                # но сохраняем оригинальный target!
                # logger.info(f"🔌 Plugin command: {target}.{cmd} → broadcasting to all workers")
                self.send_command_to_camera(-1, cmd, args, target=target)

        elif m_type == "security_alert":
            logger.critical(f"🚨 SECURITY ALERT: {payload}")

    def _check_health(self):
        now = time.time()
        for cam_id, info in list(self._workers.items()):
            proc = info['proc']
            last_beat = info['last_beat']

            # Crash
            if not proc.is_alive():
                logger.critical(f"💀 Worker-{cam_id} DIED.")
                self._restart_worker(cam_id)
                continue

            # Freeze (3 сек тишины)
            if now - last_beat > 3.0:
                logger.error(f"❄️ Worker-{cam_id} FROZEN.")
                self._restart_worker(cam_id)

    # --- Commands ---

    def _broadcast_command_internal(self, cmd: str, args: dict):
        """Внутренний метод для SecurityController"""
        self.send_command_to_camera(-1, cmd, args, target="system")

    def send_command_to_camera(self, camera_id: int, command: str, args: dict = None, target: str = None):
        """
        Отправка команды камере.

        Args:
            camera_id: ID камеры (-1 = broadcast всем)
            command: имя команды
            args: аргументы команды
            target: оригинальный target (если None, используется "system")
        """
        # Используем переданный target или "system" по умолчанию
        target_to_use = target if target is not None else "system"
        payload = {"target": target_to_use, "cmd": command, "args": args or {}}

        # logger.debug(f"📤 Orchestrator sending: target='{target_to_use}', cmd='{command}' to cam-{camera_id}")

        if camera_id == -1:
            # Broadcast всем известным воркерам
            for cid in list(self._workers.keys()):
                self.bus.send_command(cid, payload)
        else:
            self.bus.send_command(camera_id, payload)

    def get_system_state(self) -> Dict:
        with self._lock:
            return self._system_state.copy()

