"""Runtime coordinator for gated localization and path following.

This module is simulation/dry-run only. It does not send motor commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from localization.pose_gate import GatedPose, PoseGate
from planner.pure_pursuit import PurePursuit, TwistCommand


@dataclass
class NavigationState:
    mode: str = "IDLE"
    reason: str = "not_started"
    pose: GatedPose | None = None
    command: TwistCommand = TwistCommand(0.0, 0.0, "idle")


class NavigationManager:
    def __init__(self, pose_gate: PoseGate, controller: PurePursuit) -> None:
        self.pose_gate = pose_gate
        self.controller = controller
        self.state = NavigationState()
        self._waypoints: list[tuple[float, float]] = []

    @property
    def waypoints(self) -> list[tuple[float, float]]:
        return list(self._waypoints)

    def set_path(self, waypoints: list[tuple[float, float]]) -> None:
        self._waypoints = list(waypoints)
        self.state.mode = "NAVIGATING" if self._waypoints else "IDLE"
        self.state.reason = "path_ready" if self._waypoints else "empty_path"

    def update(self, localization_result: dict[str, Any]) -> NavigationState:
        pose = self.pose_gate.evaluate(localization_result)
        self.state.pose = pose

        if not pose.accepted:
            self.state.mode = "LOCALIZATION_LOST"
            self.state.reason = pose.reason
            self.state.command = TwistCommand(0.0, 0.0, "safety_stop")
            return self.state

        if not self._waypoints:
            self.state.mode = "IDLE"
            self.state.reason = "no_path"
            self.state.command = TwistCommand(0.0, 0.0, "no_path")
            return self.state

        assert pose.position_xyz is not None
        assert pose.yaw_deg is not None
        # Navigation uses X/Z from the -Y-up reconstruction frame.
        pose_xy_yaw = (
            pose.position_xyz[0],
            pose.position_xyz[2],
            pose.yaw_deg * 3.141592653589793 / 180.0,
        )
        command = self.controller.compute(pose_xy_yaw, self._waypoints)
        self.state.command = command

        if command.status == "goal_reached":
            self.state.mode = "GOAL_REACHED"
            self.state.reason = "goal_tolerance"
        else:
            self.state.mode = "NAVIGATING"
            self.state.reason = command.status
        return self.state
