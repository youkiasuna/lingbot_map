"""Backend interface for local point-cloud generation.

The interface separates point-cloud production from map fusion. The current
implemented backend replays verified world_points from predictions.npz.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol
import time
import numpy as np

from runtime.local_pointcloud_replay import PredictionPointCloudReplay, LocalWindow


@dataclass(frozen=True)
class LocalPointCloudResult:
    backend: str
    start_frame: int
    end_frame: int
    points_xyz: np.ndarray
    pose_xyz: tuple[float, float, float] | None
    yaw_deg: float | None
    confidence: float
    latency_ms: float
    source: str


class LocalPointCloudBackend(Protocol):
    def iter_generate(self, *, window_size: int, process_every: int, max_frames: int = 0, max_windows: int = 0) -> Iterator[LocalPointCloudResult]:
        ...


class PredictionNpzBackend:
    """Adapter exposing the existing predictions.npz replay as a backend."""

    name = "prediction_npz_replay"

    def __init__(self, package_path: str | Path, *, max_points_per_window: int = 100_000) -> None:
        self.package_path = Path(package_path)
        self.replay = PredictionPointCloudReplay(
            self.package_path,
            max_points_per_window=max_points_per_window,
        )

    def iter_generate(self, *, window_size: int, process_every: int, max_frames: int = 0) -> Iterator[LocalPointCloudResult]:
        for index, window in enumerate(self.replay.windows(
            window_size=window_size,
            process_every=process_every,
            max_frames=max_frames,
        )):
            if max_windows > 0 and index >= max_windows:
                break
            started = time.perf_counter()
            yield self._convert(window, (time.perf_counter() - started) * 1000.0)

    def generate(self, *, window_size: int, process_every: int, max_frames: int = 0) -> list[LocalPointCloudResult]:
        return list(self.iter_generate(window_size=window_size, process_every=process_every, max_frames=max_frames, max_windows=max_windows))

    def _convert(self, window: LocalWindow, latency_ms: float) -> LocalPointCloudResult:
        return LocalPointCloudResult(
            backend=self.name,
            start_frame=window.start_frame,
            end_frame=window.end_frame,
            points_xyz=window.points_xyz,
            pose_xyz=None,
            yaw_deg=None,
            confidence=1.0,
            latency_ms=round(latency_ms, 3),
            source=str(self.package_path),
        )
