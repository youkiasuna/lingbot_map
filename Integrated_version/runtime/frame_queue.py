"""Bounded latest-frame queue for real-time camera processing."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock

from schemas import CAMERA_FRAME, FrameRecord, TIMESTAMP_ARRIVAL


@dataclass(frozen=True)
class FramePacket:
    sequence: int
    frame: object
    timestamp_unix: float

    def to_record(
        self,
        *,
        source: str = CAMERA_FRAME,
        timestamp_source: str = TIMESTAMP_ARRIVAL,
    ) -> FrameRecord:
        """Return shared metadata without copying the image."""
        return FrameRecord(
            frame_id=int(self.sequence),
            timestamp_ns=int(float(self.timestamp_unix) * 1_000_000_000),
            source=source,
            timestamp_source=timestamp_source,
        )


class LatestFrameQueue:
    """Keep only the newest frame and count stale frames dropped."""

    def __init__(self, maxsize: int = 1) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize = maxsize
        self._packet: FramePacket | None = None
        self._lock = Lock()
        self._dropped = 0

    def put(self, packet: FramePacket) -> None:
        with self._lock:
            if self._packet is not None:
                self._dropped += 1
            self._packet = packet

    def get_latest(self) -> FramePacket | None:
        with self._lock:
            packet = self._packet
            self._packet = None
            return packet

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped
