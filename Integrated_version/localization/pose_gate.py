"""Safety gate for visual localization poses."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any


@dataclass(frozen=True)
class PoseGateConfig:
    min_confidence: float = 0.5
    max_age_s: float = 0.5
    max_position_jump_m: float = 0.75
    max_yaw_jump_deg: float = 90.0


@dataclass
class GatedPose:
    status: str
    accepted: bool
    position_xyz: list[float] | None
    yaw_deg: float | None
    confidence: float
    reason: str
    timestamp_unix: float


class PoseGate:
    """Reject stale, low-confidence, invalid, or implausible pose updates."""

    def __init__(self, config: PoseGateConfig | None = None) -> None:
        self.config = config or PoseGateConfig()
        self._last_accepted: GatedPose | None = None

    def evaluate(
        self,
        result: dict[str, Any],
        *,
        now_unix: float | None = None,
    ) -> GatedPose:
        now = time.time() if now_unix is None else now_unix
        best = result.get("best")
        if not isinstance(best, dict):
            return self._reject("missing_pose", now)

        confidence = float(best.get("confidence", 0.0))
        position = best.get("position_xyz")
        yaw = best.get("yaw_deg")
        timestamp = float(result.get("timestamp_unix", now))

        if result.get("status") != "localized":
            return self._reject("localization_not_accepted", now, confidence)
        if not math.isfinite(timestamp) or now - timestamp > self.config.max_age_s:
            return self._reject("stale_pose", now, confidence)
        if not isinstance(position, list) or len(position) != 3:
            return self._reject("invalid_position", now, confidence)
        if yaw is None or not all(math.isfinite(float(v)) for v in position):
            return self._reject("invalid_pose_values", now, confidence)
        if not math.isfinite(float(yaw)):
            return self._reject("invalid_yaw", now, confidence)
        if confidence < self.config.min_confidence:
            return self._reject("low_confidence", now, confidence)

        pose = GatedPose(
            status="ok",
            accepted=True,
            position_xyz=[float(v) for v in position],
            yaw_deg=float(yaw) % 360.0,
            confidence=confidence,
            reason="accepted",
            timestamp_unix=timestamp,
        )
        if self._last_accepted is not None:
            if self._distance(pose.position_xyz, self._last_accepted.position_xyz) > self.config.max_position_jump_m:
                return self._reject("position_jump", now, confidence)
            if self._angle_delta(pose.yaw_deg, self._last_accepted.yaw_deg) > self.config.max_yaw_jump_deg:
                return self._reject("yaw_jump", now, confidence)

        self._last_accepted = pose
        return pose

    def reset(self) -> None:
        self._last_accepted = None

    @staticmethod
    def _distance(a: list[float] | None, b: list[float] | None) -> float:
        if a is None or b is None:
            return float("inf")
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    @staticmethod
    def _angle_delta(a: float | None, b: float | None) -> float:
        if a is None or b is None:
            return float("inf")
        return abs((a - b + 180.0) % 360.0 - 180.0)

    def _reject(self, reason: str, now: float, confidence: float = 0.0) -> GatedPose:
        return GatedPose(
            status="lost",
            accepted=False,
            position_xyz=None,
            yaw_deg=None,
            confidence=confidence,
            reason=reason,
            timestamp_unix=now,
        )
