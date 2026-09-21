from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from runtime.live_map_manager import LiveMapManager
from runtime.mapping_state_machine import MappingReadiness, MappingStateMachine, RuntimeMode

class LiveMappingArchitectureTests(unittest.TestCase):
    def test_map_update_is_versioned_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp, max_points=2)
            self.assertTrue(manager.publish_map_update([[0,0,0],[1,0,1],[2,0,2]], frame_count=30, keyframe_count=20, tracked_ratio=0.8, navigable=True))
            self.assertEqual(manager.map_version, 1)
            payload = json.loads((Path(tmp) / "live_points.json").read_text())
            self.assertEqual(len(payload["points_xyz"]), 2)

    def test_invalid_update_keeps_previous_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp)
            self.assertTrue(manager.publish_map_update([[0,0,0]], frame_count=1, keyframe_count=1, tracked_ratio=1.0, navigable=True))
            self.assertFalse(manager.publish_map_update([], frame_count=2, keyframe_count=2, tracked_ratio=1.0, navigable=True))
            self.assertEqual(manager.map_version, 1)

    def test_navigation_requires_ready_map(self) -> None:
        machine = MappingStateMachine(min_keyframes=2, min_points=3)
        self.assertEqual(machine.start(), RuntimeMode.MAPPING_ONLY)
        with self.assertRaises(RuntimeError):
            machine.begin_navigation()
        machine.update_map_quality(MappingReadiness(2, 3, 0.8, True))
        self.assertEqual(machine.begin_navigation(), RuntimeMode.NAVIGATING)
        self.assertEqual(machine.localization_lost(), RuntimeMode.LOCALIZATION_LOST)
        self.assertEqual(machine.begin_recovery(), RuntimeMode.RECOVERY_MAPPING)

if __name__ == "__main__":
    unittest.main()
