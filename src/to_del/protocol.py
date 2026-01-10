# src/core/protocol.py
import struct
import time
from typing import List, Tuple
from dataclasses import dataclass

# Структура заголовка:
# Q = unsigned long long (8 bytes) -> Frame ID
# d = double (8 bytes) -> Timestamp
# B = unsigned char (1 byte) -> Marker Count
# B = unsigned char (1 byte) -> Lock Flag (0=Ready, 1=Writing)
HEADER_FORMAT = "QdBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Структура точки: ff -> x, y (float)
POINT_FORMAT = "ff"
POINT_SIZE = struct.calcsize(POINT_FORMAT)

MAX_MARKERS = 32
TOTAL_BUFFER_SIZE = HEADER_SIZE + (POINT_SIZE * MAX_MARKERS)

@dataclass
class ShmPacket:
    frame_id: int
    timestamp: float
    points: List[Tuple[float, float]]

class BinaryProtocol:
    """Упаковщик/Распаковщик данных для SharedMemory (struct)."""

    @staticmethod
    def pack(buffer: memoryview, frame_id: int, points: List[Tuple[float, float]]):
        count = min(len(points), MAX_MARKERS)
        timestamp = time.time()
        # Lock
        struct.pack_into("B", buffer, 16, 1)
        # Points
        offset = HEADER_SIZE
        for i in range(count):
            x, y = points[i]
            struct.pack_into(POINT_FORMAT, buffer, offset, x, y)
            offset += POINT_SIZE
        # Unlock & Header
        struct.pack_into(HEADER_FORMAT, buffer, 0, frame_id, timestamp, count, 0)

    @staticmethod
    def unpack(buffer: memoryview) -> ShmPacket:
        frame_id, timestamp, count, is_writing = struct.unpack_from(HEADER_FORMAT, buffer, 0)
        points = []
        if count > 0 and count <= MAX_MARKERS:
            offset = HEADER_SIZE
            try:
                for _ in range(count):
                    x, y = struct.unpack_from(POINT_FORMAT, buffer, offset)
                    points.append((x, y))
                    offset += POINT_SIZE
            except struct.error:
                pass
        return ShmPacket(frame_id, timestamp, points)