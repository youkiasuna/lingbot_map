from __future__ import annotations

import time
import unittest

from localization.pose_gate import PoseGate, PoseGateConfig
from planner.pure_pursuit import PurePursuit, PurePursuitConfig
from runtime.navigation_manager import NavigationManager


class RealtimeNavigationCoreTests(unittest.TestCase):
    def test_low_confidence_causes_stop(self) -> None:
        manager = NavigationManager(
            PoseGate(PoseGateConfig(min_confidence=0.5)),
            PurePursuit(),
        )
        manager.set_path([(1.0, 0.0)])
        state = manager.update(
            {
                "status": "localized",
                "timestamp_unix": time.time(),
                "best": {
                    "confidence": 0.2,
                    "position_xyz": [0.0, 0.0, 0.0],
                    "yaw_deg": 0.0,
                },
            }
        )
        self.assertEqual(state.mode, "LOCALIZATION_LOST")
        self.assertEqual(state.command.status, "safety_stop")

    def test_valid_pose_produces_tracking_command(self) -> None:
        manager = NavigationManager(
            PoseGate(PoseGateConfig(min_confidence=0.5)),
            PurePursuit(PurePursuitConfig(max_speed_mps=0.1)),
        )
        manager.set_path([(1.0, 0.0)])
        state = manager.update(
            {
                "status": "localized",
                "timestamp_unix": time.time(),
                "best": {
                    "confidence": 0.9,
                    "position_xyz": [0.0, 0.0, 0.0],
                    "yaw_deg": 0.0,
                },
            }
        )
        self.assertEqual(state.mode, "NAVIGATING")
        self.assertEqual(state.command.status, "tracking")
        self.assertGreater(state.command.linear_mps, 0.0)

    def test_stale_pose_causes_stop(self) -> None:
        manager = NavigationManager(
            PoseGate(PoseGateConfig(max_age_s=0.1)),
            PurePursuit(),
        )
        manager.set_path([(1.0, 0.0)])
        state = manager.update(
            {
                "status": "localized",
                "timestamp_unix": time.time() - 1.0,
                "best": {
                    "confidence": 0.9,
                    "position_xyz": [0.0, 0.0, 0.0],
                    "yaw_deg": 0.0,
                },
            }
        )
        self.assertEqual(state.mode, "LOCALIZATION_LOST")
        self.assertEqual(state.command.status, "safety_stop")


if __name__ == "__main__":
    unittest.main()
