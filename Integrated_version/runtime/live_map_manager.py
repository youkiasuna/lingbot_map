"""Versioned live local-map storage for incremental mapping prototypes."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Sequence

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

    def __init__(self, output_dir: str | Path, *, convention: CoordinateConvention | None = None, max_points: int = 250_000) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.convention = convention or CoordinateConvention()
        self.max_points = max_points
        self.map_version = self._read_version()
        self._status: dict = {}

    @property
    def map_ready(self) -> bool:
        return bool(self._status.get("map_ready", False))

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
        self.map_version += 1
        self._write_json("live_points.json", {"map_version": self.map_version, "points_xyz": points})
        self._write_json("live_map.json", {
            "schema_version": 1,
            "map_version": self.map_version,
            "updated_at_unix": time.time(),
            "coordinate_convention": asdict(self.convention),
            "quality": asdict(quality),
        })
        self._status.update({"map_ready": True, "map_version": self.map_version})
        self.publish_status()
        return True

    def publish_pose(self, position_xyz: Sequence[float] | None, yaw_deg: float | None, *, confidence: float, status: str, timestamp_unix: float | None = None) -> None:
        self._write_json("live_pose.json", {
            "schema_version": 1,
            "timestamp_unix": time.time() if timestamp_unix is None else float(timestamp_unix),
            "position_xyz": None if position_xyz is None else [float(v) for v in position_xyz],
            "yaw_deg": None if yaw_deg is None else float(yaw_deg),
            "confidence": float(confidence),
            "status": str(status),
            "map_version": self.map_version,
            "coordinate_convention": asdict(self.convention),
        })

    def publish_path(self, waypoints_xz: Iterable[Sequence[float]]) -> None:
        self._write_json("live_path.json", {
            "schema_version": 1,
            "map_version": self.map_version,
            "waypoints_xz": [[float(v) for v in point[:2]] for point in waypoints_xz],
        })

    def publish_status(self, **fields: object) -> None:
        self._status.update(fields)
        self._write_json("live_status.json", {
            "schema_version": 1,
            "timestamp_unix": time.time(),
            "map_version": self.map_version,
            "coordinate_convention": asdict(self.convention),
            **self._status,
        })

    def _read_version(self) -> int:
        path = self.output_dir / "live_map.json"
        if not path.exists():
            return 0
        try:
            return int(json.loads(path.read_text(encoding="utf-8")).get("map_version", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0

    def _write_json(self, filename: str, payload: dict) -> None:
        destination = self.output_dir / filename
        fd, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", dir=self.output_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
