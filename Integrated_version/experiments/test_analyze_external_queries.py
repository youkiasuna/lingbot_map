import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from Integrated_version.experiments.analyze_external_queries import list_query_images, safe_stem


class AnalyzeExternalQueriesTest(unittest.TestCase):
    def test_lists_only_supported_query_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = np.zeros((16, 16, 3), dtype=np.uint8)
            cv2.imwrite(str(root / "b.png"), image)
            cv2.imwrite(str(root / "a.jpg"), image)
            (root / "note.txt").write_text("skip", encoding="utf-8")

            self.assertEqual([path.name for path in list_query_images(root)], ["a.jpg", "b.png"])

    def test_safe_stem_removes_unstable_characters(self):
        self.assertEqual(safe_stem(Path("query photo 01!.jpg")), "query_photo_01")


if __name__ == "__main__":
    unittest.main()
