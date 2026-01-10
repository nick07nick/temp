# src/core/transport.py
import json
from src.core import FrameData
from dataclasses import asdict

class DataTransport:
    def __init__(self, output_file: str = "session_log.json"):
        self.output_file = output_file
        self.buffer = []

    def send(self, data: FrameData):
        """Сохраняет данные кадра в буфер."""
        if data.keypoints:
            record = asdict(data)
            print(f"[Transport] Записан кадр: t={record['timestamp']:.2f}, угол={record['knee_angle']:.1f}")
            self.buffer.append(record)

    def save(self):
        """Сбрасывает буфер в файл."""
        try:
            with open(self.output_file, 'w') as f:
                json.dump(self.buffer, f, indent=2)
            print(f"[Transport] Данные сохранены в {self.output_file}")
        except Exception as e:
            print(f"[Transport] Ошибка сохранения: {e}")