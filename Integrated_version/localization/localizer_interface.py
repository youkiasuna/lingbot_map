#!/usr/bin/env python3
"""Pose provider interface for replacing the mock tracker with a live localizer.

The goal is to keep map generation, web UI, and path planning independent from
how the robot pose is produced. Both the mock tracker and a real visual
localizer should satisfy the same interface and expose the same pose schema.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class PoseSample:
    """A unified pose record that can be published by either mock or live systems."""

    x_m: float
    y_m: float
    yaw_deg: float
    timestamp_unix: float
    source: str
    confidence: float
    status: str = "ok"
    inlier_count: int | None = None
    reprojection_error_px: float | None = None
    frame_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "x_m": round(self.x_m, 4),
            "y_m": round(self.y_m, 4),
            "yaw_deg": round(self.yaw_deg % 360.0, 2),
            "timestamp_unix": self.timestamp_unix,
            "source": self.source,
            "confidence": round(float(self.confidence), 4),
            "status": self.status,
        }
        if self.inlier_count is not None:
            payload["inlier_count"] = self.inlier_count
        if self.reprojection_error_px is not None:
            payload["reprojection_error_px"] = round(float(self.reprojection_error_px), 4)
        if self.frame_id is not None:
            payload["frame_id"] = self.frame_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PoseSample":
        return cls(
            x_m=float(payload["x_m"]),
            y_m=float(payload["y_m"]),
            yaw_deg=float(payload["yaw_deg"]),
            timestamp_unix=float(payload.get("timestamp_unix", time.time())),
            source=str(payload.get("source", "unknown")),
            confidence=float(payload.get("confidence", 0.0)),
            status=str(payload.get("status", "ok")),
            inlier_count=payload.get("inlier_count"),
            reprojection_error_px=payload.get("reprojection_error_px"),
            frame_id=payload.get("frame_id"),
        )


class LocalizationProvider(Protocol):
    """Small interface all pose sources must support."""

    def start(self) -> None:
        """Start the localization worker or camera stream."""

    def stop(self) -> None:
        """Stop background workers and release resources."""

    def get_pose(self) -> PoseSample | None:
        """Return the latest pose or None when localization is not ready."""

    def get_status(self) -> dict[str, Any]:
        """Return human-readable status info for the UI or logs."""


class FilePosePublisher:
    """Compatibility layer: write the pose into the current file contract used by the demo."""

    def __init__(self, path: Path, source_name: str = "live_localization") -> None:
        self.path = path
        self.source_name = source_name

    def publish(self, pose: PoseSample) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(pose.to_payload(), indent=2) + "\n", encoding="utf-8")


class LiveLocalizationAdapter:
    """Bridge between a real visual localizer and the existing JSON-based demo."""

    def __init__(self, provider: LocalizationProvider, pose_file: Path) -> None:
        self.provider = provider
        self.publisher = FilePosePublisher(pose_file, source_name="live_localization")
        self._last_pose: PoseSample | None = None

    def refresh(self) -> PoseSample | None:
        pose = self.provider.get_pose()
        if pose is None:
            return None
        self._last_pose = pose
        self.publisher.publish(pose)
        return pose

    def status(self) -> dict[str, Any]:
        status = self.provider.get_status()
        status["last_pose_available"] = self._last_pose is not None
        return status


class MockPoseProvider:
    """Reference mock implementation. The real visual localizer should match this contract."""

    def __init__(self, x_m: float, y_m: float, yaw_deg: float, source: str = "mock_odometry") -> None:
        self.x_m = x_m
        self.y_m = y_m
        self.yaw_deg = yaw_deg
        self.source = source
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def get_pose(self) -> PoseSample | None:
        if not self._running:
            return None
        return PoseSample(
            x_m=self.x_m,
            y_m=self.y_m,
            yaw_deg=self.yaw_deg,
            timestamp_unix=time.time(),
            source=self.source,
            confidence=1.0,
            status="ok",
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "running": self._running,
            "status": "ok",
        }


if __name__ == "__main__":
    mock = MockPoseProvider(1.0, 2.0, 30.0)
    mock.start()
    pose = mock.get_pose()
    print(json.dumps(pose.to_payload(), indent=2))
    mock.stop()
