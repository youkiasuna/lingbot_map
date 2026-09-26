from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from experiments.validate_level2_outputs import validate


class Level2OutputValidatorTests(unittest.TestCase):
    def _write_outputs(self, directory: Path, *, colors: bool = True) -> None:
        map_version = 3
        points = np.asarray([[0, 0, 0], [1, 0, 1]], dtype=np.float32)
        arrays = {"map_version": map_version, "points_xyz": points}
        if colors:
            arrays["colors_rgb"] = np.asarray([[10, 20, 30], [40, 50, 60]], dtype=np.uint8)
        np.savez_compressed(directory / "live_points.npz", **arrays)
        (directory / "live_map.json").write_text(json.dumps({
            "map_version": map_version,
            "quality": {"point_count": 2},
            "record": {"point_count": 2},
        }))
        (directory / "live_pose.json").write_text(json.dumps({
            "map_version": map_version,
            "position_xyz": [0.1, 0.2, 0.3],
            "status": "ok",
            "confidence": 0.9,
        }))
        (directory / "live_status.json").write_text(json.dumps({
            "map_version": map_version,
        }))

    def test_valid_rgb_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_outputs(Path(tmp))
            report = validate(Path(tmp), require_rgb=True)
            self.assertEqual(report["issues"], [])
            self.assertTrue(report["rgb_available"])
            self.assertTrue(report["pose_valid"])

    def test_geometry_only_output_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_outputs(Path(tmp), colors=False)
            report = validate(Path(tmp))
            self.assertEqual(report["issues"], [])
            self.assertFalse(report["rgb_available"])

if __name__ == "__main__":
    unittest.main()
