#!/usr/bin/env python3
"""Pose sample and JSON publisher contract used by localization consumers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Integrated_version.shared.json_io import atomic_write_json


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


class FilePosePublisher:
    """Write pose samples into the JSON file contract consumed by the app."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def publish(self, pose: PoseSample) -> None:
        atomic_write_json(self.path, pose.to_payload(), indent=2)
