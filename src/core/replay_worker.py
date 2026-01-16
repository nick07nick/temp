# src/hardware/replay_worker.py
import time
import struct
import numpy as np
import os
from pathlib import Path
from loguru import logger

from src.data.shared_memory import SharedMemoryManager
from src.core.config import settings


def run_replay_worker(filepath: str, shm_name: str):
    """
    Воспроизводит записанный.bfm файл в Shared Memory,
    имитируя работу реальной камеры (соблюдая тайминги).
    """
    path = Path(filepath)
    if not path.exists():
        logger.error(f"File not found: {path}")
        return

    logger.info(f"🎬 Starting Replay from: {path.name}")

    # Открываем файл
    with open(path, 'rb') as f:
        # --- READ HEADER ---
        magic = f.read(8)
        if magic != b'BFM_RAW ':
            logger.error("Invalid file format")
            return

        ver, h, w, c, total_frames = struct.unpack('iiiii', f.read(20))
        logger.info(f"File Info: {w}x{h}, {total_frames} frames")

        # Инициализируем Shared Memory как ВЛАДЕЛЕЦ (мы заменяем камеру)
        shm = SharedMemoryManager(
            name=shm_name,
            shape=(h, w, c),
            create=True
        )

        try:
            frame_idx = 0
            start_time = time.time()
            # Читаем первый таймстемп, чтобы синхронизироваться
            first_ts_in_file = None

            while frame_idx < total_frames:
                # 1. Читаем размер меты
                meta_len_bytes = f.read(4)
                if not meta_len_bytes: break
                meta_len = struct.unpack('I', meta_len_bytes)

                # 2. Читаем мету
                meta_data = f.read(meta_len)
                orig_fid, orig_ts = struct.unpack('qd', meta_data)

                # 3. Читаем данные
                data_len = struct.unpack('I', f.read(4))
                raw_pixels = f.read(data_len)

                # Восстанавливаем массив
                frame = np.frombuffer(raw_pixels, dtype='uint8').reshape((h, w, c))

                # --- СИНХРОНИЗАЦИЯ ---
                if first_ts_in_file is None:
                    first_ts_in_file = orig_ts
                    start_sys_time = time.time()

                # Целевое время воспроизведения
                target_delay = orig_ts - first_ts_in_file
                current_delay = time.time() - start_sys_time

                if target_delay > current_delay:
                    time.sleep(target_delay - current_delay)

                # --- ЗАПИСЬ В SHM ---
                # Генерируем новый timestamp (текущий), но сохраняем относительные интервалы?
                # Или пишем оригинальный timestamp?
                # Лучше писать текущий системный, чтобы Core не сходил с ума от старых дат.
                new_ts = time.time()

                shm.write_frame(frame, orig_fid, new_ts, salt=1.0)

                frame_idx += 1
                if frame_idx % 90 == 0:
                    logger.debug(f"Replay: {frame_idx}/{total_frames}")

            logger.info("🎬 Replay finished.")

        finally:
            shm.close()


if __name__ == "__main__":
    # Тестовый запуск
    # Укажите путь к записанному файлу
    TEST_FILE = settings.DATA_DIR / "test_session.bfm"
    run_replay_worker(str(TEST_FILE), settings.SHM_CAMERA_BUFFER_NAME)