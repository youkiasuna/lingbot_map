from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
import numpy as np

from runtime.incremental_map_fusion import IncrementalVoxelMap
from runtime.local_pointcloud_replay import PredictionPointCloudReplay


class IncrementalMappingTests(unittest.TestCase):
    def test_voxel_fusion_increments_version_and_merges_duplicates(self) -> None:
        fusion = IncrementalVoxelMap(voxel_size_m=0.1, max_points=100)
        first = fusion.update(np.array([[0, 0, 0], [1, 0, 1]], dtype=np.float32))
        second = fusion.update(np.array([[0.01, 0, 0.01], [2, 0, 2]], dtype=np.float32))
        self.assertEqual(first.map_version, 1)
        self.assertEqual(second.map_version, 2)
        self.assertEqual(second.fused_points, 3)

    def test_replay_windows_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "predictions.npz"
            points = np.arange(24, dtype=np.float32).reshape(4, 2, 3)
            np.savez(package, world_points=points, frame_paths=np.array(["a", "b", "c", "d"]))
            replay = PredictionPointCloudReplay(package)
            windows = replay.windows(window_size=2, process_every=1)
            self.assertEqual([(w.start_frame, w.end_frame) for w in windows], [(0, 1), (1, 2), (2, 3)])
            self.assertEqual(windows[0].points_xyz.shape, (4, 3))


if __name__ == "__main__":
    unittest.main()
