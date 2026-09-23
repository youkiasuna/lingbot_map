"""Versioned, JSON-compatible records shared by research and runtime code.

These records are intentionally small. They define the interchange contract
without changing any existing producer or consumer yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


SCHEMA_VERSION = 1
RECONSTRUCTION_FRAME = "reconstruction"
NAVIGATION_XZ_FRAME = "navigation_xz"
CAMERA_FRAME = "camera"
TIMESTAMP_CAPTURE = "capture"
TIMESTAMP_ARRIVAL = "arrival"
TIMESTAMP_SYNTHETIC = "synthetic"


def _record_dict(record: Any) -> dict[str, Any]:
    data = asdict(record)
    data["schema_version"] = SCHEMA_VERSION
    return data


@dataclass(slots=True)
class FrameRecord:
    """One camera frame and its capture/arrival metadata."""

    frame_id: int
    timestamp_ns: int
    source: str
    image_path: str | None = None
    width: int | None = None
    height: int | None = None
    timestamp_source: str = TIMESTAMP_ARRIVAL
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _record_dict(self)


@dataclass(slots=True)
class PoseRecord:
    """A pose expressed in a named reconstruction or navigation frame."""

    position_xyz: list[float] | None = None
    rotation_quaternion_xyzw: list[float] | None = None
    yaw_deg: float | None = None
    coordinate_frame: str = RECONSTRUCTION_FRAME
    timestamp_ns: int | None = None
    confidence: float = 0.0
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _record_dict(self)


@dataclass(slots=True)
class PointCloudRecord:
    """Metadata for a point-cloud snapshot stored outside the JSON record."""

    points_file: str
    point_count: int
    map_version: int
    coordinate_frame: str = RECONSTRUCTION_FRAME
    timestamp_ns: int | None = None
    source_frames: list[int] = field(default_factory=list)
    has_rgb: bool = False
    colors_file: str | None = None
    color_format: str | None = None
    registration_method: str = "none"
    registration_status: str = "not_applied"
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        has_color_metadata = self.colors_file is not None or self.color_format is not None
        if self.has_rgb and not (self.colors_file and self.color_format):
            raise ValueError("RGB point clouds require colors_file and color_format")
        if not self.has_rgb and has_color_metadata:
            raise ValueError("colors_file and color_format require has_rgb=True")

    def to_dict(self) -> dict[str, Any]:
        return _record_dict(self)


@dataclass(slots=True)
class LocalizationResult:
    """Result of a query-image localization attempt."""

    query_id: str
    method: str
    status: str
    pose: PoseRecord | None = None
    match_count: int = 0
    inlier_count: int = 0
    confidence: float = 0.0
    latency_ms: float = 0.0
    inlier_ratio: float = 0.0
    reprojection_error_px: float | None = None
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = _record_dict(self)
        if self.pose is not None:
            data["pose"] = self.pose.to_dict()
        return data


@dataclass(slots=True)
class NavigationCommand:
    """Velocity command sent to a simulator or vehicle adapter."""

    timestamp_ns: int
    linear_mps: float
    angular_rps: float
    status: str = "safety_stop"
    source: str = "dry_run"
    schema_version: ClassVar[int] = SCHEMA_VERSION

    @classmethod
    def from_twist(cls, command: Any, *, timestamp_ns: int | None = None, source: str = "dry_run") -> "NavigationCommand":
        """Adapt the existing planner TwistCommand without importing planner code."""
        return cls(
            timestamp_ns=0 if timestamp_ns is None else int(timestamp_ns),
            linear_mps=float(command.linear_mps),
            angular_rps=float(command.angular_rps),
            status=str(command.status),
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return _record_dict(self)


@dataclass(slots=True)
class MapStatusRecord:
    """Stable status contract for a live mapping/navigation session."""

    map_version: int
    map_ready: bool
    mode: str = "MAPPING"
    localization_status: str = "unavailable"
    pointcloud_file: str | None = None
    viewer_pointcloud: str | None = None
    viewer_pose: str | None = None
    viewer_path: str | None = None
    timestamp_ns: int | None = None
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _record_dict(self)


@dataclass(slots=True)
class MappingWindowRecord:
    """Metadata for one bounded mapping inference window."""

    window_id: str
    start_frame: int
    end_frame: int
    backend: str
    latency_ms: float = 0.0
    frame_records: list[FrameRecord] = field(default_factory=list)
    pointcloud_record: PointCloudRecord | None = None
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = _record_dict(self)
        if self.pointcloud_record is not None:
            data["pointcloud_record"] = self.pointcloud_record.to_dict()
        return data
