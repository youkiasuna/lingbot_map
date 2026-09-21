from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from hardware.esp32_adapter import Esp32Adapter, Esp32Config
from localization.pose_gate import PoseGate, PoseGateConfig
from planner.pure_pursuit import PurePursuit, PurePursuitConfig, TwistCommand
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

    def test_esp32_adapter_rejects_hardware_mode(self) -> None:
        with self.assertRaises(ValueError):
            Esp32Adapter(Esp32Config(dry_run=False))

    def test_esp32_adapter_writes_dry_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "commands.jsonl"
            adapter = Esp32Adapter(Esp32Config(command_log_path=log_path))
            adapter.send(TwistCommand(0.1, 0.2, "tracking"))
            adapter.stop()
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["status"], "tracking")
        self.assertEqual(records[1]["status"], "safety_stop")
        self.assertTrue(all(record["dry_run"] for record in records))


if __name__ == "__main__":
    unittest.main()
