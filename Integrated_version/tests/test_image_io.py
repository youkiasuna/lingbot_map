import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from Integrated_version.shared.image_io import read_bgr_image


class ImageIoTests(unittest.TestCase):
    def test_reads_image_from_unicode_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "測試影像.png"
            Image.new("RGB", (12, 8), (20, 40, 60)).save(path)

            image = read_bgr_image(path)

            self.assertIsNotNone(image)
            self.assertEqual(image.shape, (8, 12, 3))
            np.testing.assert_array_equal(image[0, 0], [60, 40, 20])


if __name__ == "__main__":
    unittest.main()
