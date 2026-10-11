"""Versioned live local-map storage for incremental mapping prototypes."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Iterable, Sequence

import numpy as np
from Integrated_version.shared.npz_io import atomic_write_npz
from Integrated_version.shared.json_io import atomic_write_json

@dataclass(frozen=True)
class CoordinateConvention:
    vertical_axis: str = "-y"
    navigation_plane: str = "XZ"
    position_mapping: str = "x_m=position_xyz[0], y_m=position_xyz[2]"

@dataclass(frozen=True)
class MapQuality:
    frame_count: int
    keyframe_count: int
    point_count: int
    tracked_ratio: float
    navigable: bool

class LiveMapManager:
    """Publish accepted live-map snapshots without destroying the last valid map."""

    def __init__(self, output_dir: str | Path, *, convention: CoordinateConvention | None = None, max_points: int = 250_000, publish_json_points: bool = False) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.convention = convention or CoordinateConvention()
        self.max_points = max_points
        self.publish_json_points = publish_json_points
        self.map_version = self._read_version()
        self._status: dict = {}

    def publish_map_update(self, points_xyz: Iterable[Sequence[float]], *, frame_count: int, keyframe_count: int, tracked_ratio: float, navigable: bool) -> bool:
        points = [[float(v) for v in point[:3]] for point in points_xyz]
        if any(len(point) != 3 for point in points):
            raise ValueError("every point must contain exactly three coordinates")
        if not points or not navigable or not 0.0 <= tracked_ratio <= 1.0:
            return False
        if len(points) > self.max_points:
            step = max(1, len(points) // self.max_points)
            points = points[::step][:self.max_points]
        quality = MapQuality(int(frame_count), int(keyframe_count), len(points), float(tracked_ratio), bool(navigable))
        next_version = self.map_version + 1
        points_array = np.asarray(points, dtype=np.float32)
        atomic_write_npz(
            self.output_dir / "live_points.npz",
            {"map_version": next_version, "points_xyz": points_array},
        )
        if self.publish_json_points:
            atomic_write_json(self.output_dir / "live_points.json", {"map_version": next_version, "points_xyz": points}, indent=2, ensure_ascii=False)
        atomic_write_json(self.output_dir / "live_map.json", {
            "schema_version": 1,
            "map_version": next_version,
            "updated_at_unix": time.time(),
            "coordinate_convention": asdict(self.convention),
            "quality": asdict(quality),
        }, indent=2, ensure_ascii=False)
        self.map_version = next_version
        self._status.update({"map_version": self.map_version, "pointcloud_file": "live_points.json" if self.publish_json_points else "live_points.npz"})
        self.publish_status()
        return True

    def publish_pose(self, position_xyz: Sequence[float] | None, yaw_deg: float | None, *, confidence: float, status: str, timestamp_unix: float | None = None) -> None:
        atomic_write_json(self.output_dir / "live_pose.json", {
            "schema_version": 1,
            "timestamp_unix": time.time() if timestamp_unix is None else float(timestamp_unix),
            "position_xyz": None if position_xyz is None else [float(v) for v in position_xyz],
            "yaw_deg": None if yaw_deg is None else float(yaw_deg),
            "confidence": float(confidence),
            "status": str(status),
            "map_version": self.map_version,
            "coordinate_convention": asdict(self.convention),
        }, indent=2, ensure_ascii=False)

    def publish_path(self, waypoints_xz: Iterable[Sequence[float]]) -> None:
        atomic_write_json(self.output_dir / "live_path.json", {
            "schema_version": 1,
            "map_version": self.map_version,
            "waypoints_xz": [[float(v) for v in point[:2]] for point in waypoints_xz],
        }, indent=2, ensure_ascii=False)

    def publish_status(self, **fields: object) -> None:
        self._status.update(fields)
        atomic_write_json(self.output_dir / "live_status.json", {
            "schema_version": 1,
            "timestamp_unix": time.time(),
            "map_version": self.map_version,
            "coordinate_convention": asdict(self.convention),
            **self._status,
        }, indent=2, ensure_ascii=False)

    def _read_version(self) -> int:
        path = self.output_dir / "live_map.json"
        if not path.exists():
            return 0
        try:
            return int(json.loads(path.read_text(encoding="utf-8")).get("map_version", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0
