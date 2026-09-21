from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
import numpy as np

from runtime.local_pointcloud_backend import PredictionNpzBackend


class LocalPointCloudBackendTests(unittest.TestCase):
    def test_prediction_backend_returns_standard_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "predictions.npz"
            points = np.arange(36, dtype=np.float32).reshape(6, 2, 3)
            np.savez(package, world_points=points, frame_paths=np.array([str(i) for i in range(6)]))
            backend = PredictionNpzBackend(package, max_points_per_window=100)
            results = backend.generate(window_size=2, process_every=2)
            self.assertEqual(len(results), 3)
            self.assertEqual(results[0].backend, "prediction_npz_replay")
            self.assertEqual(results[0].points_xyz.shape, (4, 3))
            self.assertEqual(results[0].start_frame, 0)
            self.assertEqual(results[-1].end_frame, 5)
            self.assertEqual(results[0].confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
