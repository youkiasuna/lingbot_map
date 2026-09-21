"""Pure Pursuit controller for a planar differential-drive robot."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PurePursuitConfig:
    lookahead_m: float = 0.35
    max_speed_mps: float = 0.15
    max_angular_speed_rps: float = 0.7
    goal_tolerance_m: float = 0.12
    min_forward_speed_mps: float = 0.03


@dataclass(frozen=True)
class TwistCommand:
    linear_mps: float
    angular_rps: float
    status: str


class PurePursuit:
    def __init__(self, config: PurePursuitConfig | None = None) -> None:
        self.config = config or PurePursuitConfig()

    def compute(
        self,
        pose_xy_yaw: tuple[float, float, float],
        waypoints: list[tuple[float, float]],
    ) -> TwistCommand:
        if not waypoints:
            return TwistCommand(0.0, 0.0, "no_path")

        x, y, yaw = pose_xy_yaw
        goal_x, goal_y = waypoints[-1]
        if math.hypot(goal_x - x, goal_y - y) <= self.config.goal_tolerance_m:
            return TwistCommand(0.0, 0.0, "goal_reached")

        target = self._lookahead((x, y), waypoints)
        if target is None:
            return TwistCommand(0.0, 0.0, "path_exhausted")

        dx = target[0] - x
        dy = target[1] - y
        local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
        local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
        distance_sq = max(local_x * local_x + local_y * local_y, 1e-9)
        curvature = 2.0 * local_y / distance_sq

        speed = self.config.max_speed_mps
        if local_x < 0.0:
            speed = 0.0
        else:
            speed = max(self.config.min_forward_speed_mps, speed)

        angular = max(
            -self.config.max_angular_speed_rps,
            min(self.config.max_angular_speed_rps, curvature * speed),
        )
        return TwistCommand(speed, angular, "tracking")

    def _lookahead(
        self,
        position: tuple[float, float],
        waypoints: list[tuple[float, float]],
    ) -> tuple[float, float] | None:
        x, y = position
        for waypoint in waypoints:
            if math.hypot(waypoint[0] - x, waypoint[1] - y) >= self.config.lookahead_m:
                return waypoint
        return waypoints[-1] if waypoints else None
