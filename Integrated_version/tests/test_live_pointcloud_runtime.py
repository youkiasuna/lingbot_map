from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from Integrated_version.runtime.live_pointcloud_runtime import write_live_frame


class LivePointcloudRuntimeTests(unittest.TestCase):
    def test_live_frame_uses_jpg_temp_and_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            destination = output_dir / "live_frame.jpg"
            destination.write_bytes(b"old")
            frame = np.full((4, 6, 3), 100, dtype=np.uint8)

            write_live_frame(cv2, frame, output_dir)

            decoded = cv2.imread(str(destination))
            self.assertEqual(decoded.shape, frame.shape)
            self.assertEqual(list(output_dir.iterdir()), [destination])

    def test_failed_encode_preserves_previous_frame_and_cleans_temp(self):
        class FailedCv:
            @staticmethod
            def imwrite(path, _frame):
                if not path.endswith(".jpg"):
                    raise AssertionError(f"expected JPEG suffix: {path}")
                return False

        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            destination = output_dir / "live_frame.jpg"
            destination.write_bytes(b"old")

            with self.assertRaises(OSError):
                write_live_frame(FailedCv, b"new", output_dir)

            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual(list(output_dir.iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
