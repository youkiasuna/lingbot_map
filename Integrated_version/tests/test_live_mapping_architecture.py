from __future__ import annotations
import json
import numpy as np
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
            payload = np.load(Path(tmp) / "live_points.npz")
            self.assertEqual(payload["map_version"].item(), 1)
            self.assertEqual(payload["points_xyz"].shape, (2, 3))

    def test_rgb_snapshot_keeps_point_color_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp, max_points=2)
            colors = np.asarray([[10, 20, 30], [40, 50, 60], [70, 80, 90]], dtype=np.uint8)
            self.assertTrue(manager.publish_map_update(
                [[0, 0, 0], [1, 0, 1], [2, 0, 2]],
                colors_rgb=colors,
                frame_count=3,
                keyframe_count=3,
                tracked_ratio=1.0,
                navigable=True,
            ))
            with np.load(Path(tmp) / "live_points.npz") as payload:
                self.assertEqual(payload["points_xyz"].shape, (2, 3))
                self.assertEqual(payload["colors_rgb"].shape, (2, 3))
                self.assertEqual(payload["colors_rgb"][0].tolist(), [10, 20, 30])
            record = json.loads((Path(tmp) / "live_map.json").read_text())
            self.assertTrue(record["record"]["has_rgb"])
            self.assertEqual(record["record"]["color_format"], "rgb_uint8")

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
