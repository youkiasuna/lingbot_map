"""Bounded voxel fusion for replayed local point clouds."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class FusionResult:
    map_version: int
    input_points: int
    fused_points: int
    voxel_size_m: float


class IncrementalVoxelMap:
    """Fuse local world-coordinate points while bounding map memory."""

    def __init__(self, *, voxel_size_m: float = 0.03, max_points: int = 250_000) -> None:
        if voxel_size_m <= 0 or max_points <= 0:
            raise ValueError("voxel_size_m and max_points must be positive")
        self.voxel_size_m = float(voxel_size_m)
        self.max_points = int(max_points)
        self.map_version = 0
        self._voxels: dict[tuple[int, int, int], np.ndarray] = {}

    @property
    def points_xyz(self) -> np.ndarray:
        if not self._voxels:
            return np.empty((0, 3), dtype=np.float32)
        return np.stack(list(self._voxels.values())).astype(np.float32)

    def update(self, points_xyz: np.ndarray) -> FusionResult:
        points = np.asarray(points_xyz, dtype=np.float32).reshape(-1, 3)
        points = points[np.isfinite(points).all(axis=1)]
        input_count = len(points)
        for point in points:
            key = tuple(np.floor(point / self.voxel_size_m).astype(np.int64).tolist())
            self._voxels[key] = point
        self._trim()
        self.map_version += 1
        return FusionResult(self.map_version, input_count, len(self._voxels), self.voxel_size_m)

    def _trim(self) -> None:
        if len(self._voxels) <= self.max_points:
            return
        keys = list(self._voxels)
        stride = max(1, len(keys) // self.max_points)
        self._voxels = {key: self._voxels[key] for key in keys[::stride][: self.max_points]}
