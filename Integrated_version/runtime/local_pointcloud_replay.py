"""Replay local 3D point clouds from an existing LingBot-MAP package.

This module uses world_points from predictions.npz as a verified geometry source.
It does not claim to infer new depth from RGB frames.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class LocalWindow:
    start_frame: int
    end_frame: int
    frame_paths: list[str]
    points_xyz: np.ndarray


class PredictionPointCloudReplay:
    """Expose fixed-size frame windows from a mapping predictions.npz package."""

    def __init__(self, package_path: str | Path, *, max_points_per_window: int = 100_000) -> None:
        self.package_path = Path(package_path)
        data = np.load(self.package_path, allow_pickle=True)
        required = {"world_points", "frame_paths"}
        missing = required.difference(data.files)
        if missing:
            raise ValueError(f"mapping package missing fields: {sorted(missing)}")
        self.world_points = data["world_points"]
        self.frame_paths = [str(item) for item in data["frame_paths"].tolist()]
        self.max_points_per_window = max_points_per_window
        if len(self.frame_paths) != len(self.world_points):
            raise ValueError("frame_paths and world_points must have equal length")

    def windows(self, *, window_size: int, process_every: int, max_frames: int = 0) -> list[LocalWindow]:
        if window_size <= 0 or process_every <= 0:
            raise ValueError("window_size and process_every must be positive")
        limit = len(self.frame_paths) if max_frames <= 0 else min(max_frames, len(self.frame_paths))
        windows: list[LocalWindow] = []
        for end in range(window_size, limit + 1, process_every):
            start = end - window_size
            points = self._flatten_points(self.world_points[start:end])
            windows.append(LocalWindow(start, end - 1, self.frame_paths[start:end], points))
        return windows

    def _flatten_points(self, batch: np.ndarray) -> np.ndarray:
        points = np.asarray(batch, dtype=np.float32).reshape(-1, 3)
        finite = np.isfinite(points).all(axis=1)
        points = points[finite]
        if len(points) > self.max_points_per_window:
            step = max(1, len(points) // self.max_points_per_window)
            points = points[::step][: self.max_points_per_window]
        return points
