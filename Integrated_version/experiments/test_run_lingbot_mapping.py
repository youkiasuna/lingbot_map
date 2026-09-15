import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

EXPERIMENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS_DIR))

from run_lingbot_mapping import write_prediction_archive


class PredictionArchiveTest(unittest.TestCase):
    def test_writes_frame_aligned_archive_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            archive_path, metadata_path = write_prediction_archive(
                {
                    "extrinsic": np.zeros((2, 3, 4), dtype=np.float32),
                    "intrinsic": np.repeat(np.eye(3, dtype=np.float32)[None], 2, axis=0),
                    "world_points": np.zeros((2, 4, 5, 3), dtype=np.float32),
                    "world_points_conf": np.ones((2, 4, 5), dtype=np.float32),
                },
                ["frame_000.png", "frame_001.png"],
                output_dir / "predictions.npz",
                output_dir / "preprocessed",
                lambda _: None,
            )

            self.assertTrue(metadata_path.is_file())
            with np.load(archive_path) as archive:
                self.assertEqual(archive["extrinsic_c2w"].shape, (2, 3, 4))
                self.assertEqual(archive["intrinsic"].shape, (2, 3, 3))
                self.assertEqual(archive["world_points"].shape, (2, 4, 5, 3))
                self.assertEqual(archive["frame_paths"].shape, (2,))
                self.assertEqual(int(archive["schema_version"]), 2)
                self.assertFalse(Path(str(archive["frame_paths"][0])).is_absolute())
                self.assertEqual((archive_path.parent / str(archive["frame_paths"][0])).resolve(), Path("frame_000.png").resolve())


if __name__ == "__main__":
    unittest.main()
