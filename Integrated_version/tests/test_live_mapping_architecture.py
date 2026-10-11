from __future__ import annotations
import json
import numpy as np
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Integrated_version.runtime.live_map_manager import LiveMapManager
from Integrated_version.runtime.mapping_state_machine import MappingReadiness, MappingStateMachine, RuntimeMode

class LiveMappingArchitectureTests(unittest.TestCase):
    def test_map_update_is_versioned_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp, max_points=2)
            self.assertTrue(manager.publish_map_update([[0,0,0],[1,0,1],[2,0,2]], frame_count=30, keyframe_count=20, tracked_ratio=0.8, navigable=True))
            self.assertEqual(manager.map_version, 1)
            with np.load(Path(tmp) / "live_points.npz") as payload:
                self.assertEqual(payload["map_version"].item(), 1)
                self.assertEqual(payload["points_xyz"].shape, (2, 3))

    def test_invalid_update_keeps_previous_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp)
            self.assertTrue(manager.publish_map_update([[0,0,0]], frame_count=1, keyframe_count=1, tracked_ratio=1.0, navigable=True))
            self.assertFalse(manager.publish_map_update([], frame_count=2, keyframe_count=2, tracked_ratio=1.0, navigable=True))
            self.assertEqual(manager.map_version, 1)

    def test_failed_archive_write_keeps_published_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LiveMapManager(tmp)
            self.assertTrue(manager.publish_map_update([[0, 0, 0]], frame_count=1, keyframe_count=1, tracked_ratio=1.0, navigable=True))
            with patch("Integrated_version.runtime.live_map_manager.atomic_write_npz", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    manager.publish_map_update([[1, 0, 1]], frame_count=2, keyframe_count=2, tracked_ratio=1.0, navigable=True)

            self.assertEqual(manager.map_version, 1)
            with np.load(Path(tmp) / "live_points.npz") as archive:
                self.assertEqual(int(archive["map_version"]), 1)
            self.assertEqual(json.loads((Path(tmp) / "live_map.json").read_text(encoding="utf-8"))["map_version"], 1)

    def test_navigation_requires_ready_map(self) -> None:
        machine = MappingStateMachine(min_keyframes=2, min_points=3)
        self.assertEqual(machine.start(), RuntimeMode.MAPPING_ONLY)
        with self.assertRaises(RuntimeError):
            machine.begin_navigation()
        machine.update_map_quality(MappingReadiness(2, 3, 0.8, True))
        self.assertEqual(machine.begin_navigation(), RuntimeMode.NAVIGATING)
        self.assertEqual(machine.localization_lost(), RuntimeMode.LOCALIZATION_LOST)
        self.assertEqual(machine.begin_recovery(), RuntimeMode.RECOVERY_MAPPING)
        self.assertEqual(
            machine.recover_map(MappingReadiness(3, 4, 0.9, True)),
            RuntimeMode.MAP_READY,
        )
        machine.begin_recovery()
        self.assertEqual(machine.recover_map(MappingReadiness()), RuntimeMode.MAPPING_ONLY)

if __name__ == "__main__":
    unittest.main()
