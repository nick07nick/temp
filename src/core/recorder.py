import time
import struct
import threading
from pathlib import Path
from loguru import logger
from src.core.config import settings
from src.data.shared_memory import SharedMemoryManager


class SessionRecorder:
    def __init__(self, filename: str, shm_name: str = None):
        self.filename = Path(filename)
        self.is_recording = False
        self.shm = None
        self._thread = None

        # Если имя не передано, пробуем дефолтное (для тестов),
        # но в реальности оно должно приходить из handshake
        self.target_shm_name = shm_name if shm_name else settings.SHM_CAMERA_BUFFER_NAME

        # Формат файла .bfm (BikeFit Motion Binary)

    def start(self):
        logger.info(f"🔴 Starting Recording to {self.filename}...")
        try:
            # Подключаемся к существующей памяти
            # ВАЖНО: Мы создаем конфиг "на лету" или должны знать параметры.
            # Для простоты пока предполагаем, что параметры в settings совпадают.
            # В идеале Recorder должен получать Config объект.

            from src.data.models import SharedMemoryConfig
            cfg = SharedMemoryConfig(
                name=self.target_shm_name,
                shape=(settings.CAMERA_HEIGHT, settings.CAMERA_WIDTH, 3),
                dtype='uint8'
            )

            self.shm = SharedMemoryManager(config=cfg, create=False)
            self.is_recording = True

            self._thread = threading.Thread(target=self._record_loop)
            self._thread.start()
        except FileNotFoundError:
            logger.error(
                f"❌ Cannot start recorder: Shared Memory '{self.target_shm_name}' not found. Is Camera running?")
        except Exception as e:
            logger.error(f"Recorder Init Error: {e}")

    def stop(self):
        self.is_recording = False
        if self._thread:
            self._thread.join()
        if self.shm:
            self.shm.close()
        logger.info(f"💾 Recording saved: {self.filename}")

    def _record_loop(self):
        last_frame_id = -1

        # Создаем папку если нет
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filename, 'wb') as f:
            # Пишем заголовок файла (версия формата)
            f.write(b'BFM1')

            while self.is_recording:
                data = self.shm.read_frame()
                if not data:
                    time.sleep(0.002)
                    continue

                frame_id, timestamp, points = data

                # Пишем только новые кадры
                if frame_id > last_frame_id:
                    # Упаковываем обратно
                    # Формат пакета в файле: [Len(4b)][Header...][Points...]

                    # 1. Заголовок кадра (как в SHM, но для файла)
                    # Используем форматы из SHM менеджера
                    header_data = struct.pack(self.shm.HEADER_FORMAT, frame_id, timestamp, 1.0, len(points), 0)

                    points_data = bytearray()
                    # Заглушка для точек (пока пустой список)
                    # for p in points:
                    #     points_data.extend(struct.pack(self.shm.POINT_FORMAT, p.id, p.x, p.y))

                    full_packet = header_data + points_data
                    packet_len = len(full_packet)

                    # 2. Пишем длину пакета и сам пакет
                    f.write(struct.pack('I', packet_len))
                    f.write(full_packet)

                    if frame_id % 90 == 0:
                        logger.debug(f"Recorded frame {frame_id}...")

                    last_frame_id = frame_id

                # Спим очень мало, чтобы не пропустить 90 FPS
                time.sleep(0.001)