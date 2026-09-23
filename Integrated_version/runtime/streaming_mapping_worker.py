"""Background persistent LingBot-MAP worker for live camera mapping."""
from __future__ import annotations

from dataclasses import dataclass
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from schemas import (
    CAMERA_FRAME,
    MappingWindowRecord,
    PointCloudRecord,
    FrameRecord,
)
from runtime.frame_queue import FramePacket

if TYPE_CHECKING:
    from runtime.lingbot_map_session import LingBotMapSession


@dataclass(frozen=True)
class StreamingMappingWorkerConfig:
    window_size: int = 10
    process_every: int = 10
    max_windows: int = 0

    def __post_init__(self) -> None:
        if self.window_size <= 0 or self.process_every <= 0:
            raise ValueError("window_size and process_every must be positive")
        if self.max_windows < 0:
            raise ValueError("max_windows cannot be negative")


class StreamingMappingWorker:
    """Consume camera frames and run persistent inference in a background thread."""

    def __init__(
        self,
        session: "LingBotMapSession",
        config: StreamingMappingWorkerConfig,
        on_result: Callable[[dict], None],
    ) -> None:
        self.session = session
        self.config = config
        self.on_result = on_result
        self._frames: list[FramePacket] = []
        self._submitted = 0
        self._last_processed = 0
        self._windows = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: Exception | None = None
        self.processed_windows = 0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("worker already started")
        self._thread = threading.Thread(
            target=self._run, name="live-lingbot-worker", daemon=True
        )
        self._thread.start()

    def submit(self, packet: FramePacket) -> None:
        with self._lock:
            self._frames.append(packet)
            self._submitted += 1
            if len(self._frames) > self.config.window_size:
                self._frames.pop(0)
        self._wake.set()

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)

    def _next_window(self) -> list[FramePacket] | None:
        with self._lock:
            if len(self._frames) < self.config.window_size:
                return None
            if self._submitted - self._last_processed < self.config.process_every:
                return None
            self._last_processed = self._submitted
            return list(self._frames)

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                packets = self._next_window()
                if packets is None:
                    self._wake.wait(timeout=0.05)
                    self._wake.clear()
                    continue
                self._process_window(packets)
                self.processed_windows += 1
                self._windows += 1
                if self.config.max_windows and self._windows >= self.config.max_windows:
                    return
        except Exception as exc:
            self.error = exc

    def _process_window(self, packets: list[FramePacket]) -> None:
        import cv2

        window_id = f"window_{packets[0].sequence:06d}_{packets[-1].sequence:06d}"
        with tempfile.TemporaryDirectory(prefix="live_frames_") as image_root:
            with tempfile.TemporaryDirectory(prefix="live_output_") as output_root:
                image_dir = Path(image_root)
                for index, packet in enumerate(packets):
                    image_path = image_dir / f"{index:06d}.jpg"
                    if not cv2.imwrite(str(image_path), packet.frame):
                        raise OSError(f"failed to write {image_path}")
                result = self.session.infer_image_folder(image_dir, Path(output_root))

        frame_records = [
            packet.to_record(source=CAMERA_FRAME) for packet in packets
        ]
        result["window_id"] = window_id
        result["start_sequence"] = packets[0].sequence
        result["end_sequence"] = packets[-1].sequence
        result["frame_records"] = [record.to_dict() for record in frame_records]

        points = result.get("points_xyz")
        pointcloud_record = None
        if points is not None:
            pointcloud_record = PointCloudRecord(
                points_file="in_memory_world_points",
                point_count=int(len(points)),
                map_version=0,
                source_frames=[record.frame_id for record in frame_records],
                has_rgb=False,
            )
        result["window_record"] = MappingWindowRecord(
            window_id=window_id,
            start_frame=packets[0].sequence,
            end_frame=packets[-1].sequence,
            backend="lingbot_map_streaming",
            latency_ms=float(result.get("timings_ms", {}).get("session_total", 0.0)),
            frame_records=frame_records,
            pointcloud_record=pointcloud_record,
        ).to_dict()
        self.on_result(result)
