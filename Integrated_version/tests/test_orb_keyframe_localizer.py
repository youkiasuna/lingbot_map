import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from Integrated_version.localization.orb_keyframe_localizer import OrbKeyframeLocalizer, result_to_pose


class OrbKeyframeLocalizerTest(unittest.TestCase):
    def test_retrieves_identical_frame_and_publishes_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping_dir = Path(tmp) / "mapping"
            preprocessed = mapping_dir / "preprocessed"
            preprocessed.mkdir(parents=True)

            image = Image.new("RGB", (220, 160), "black")
            draw = ImageDraw.Draw(image)
            draw.text((35, 55), "LAB", fill="white")
            draw.ellipse((128, 23, 172, 67), outline="white", width=2)
            draw.line((20, 130, 200, 125), fill="white", width=3)
            image.save(preprocessed / "000000.png")
            query_path = Path(tmp) / "query.png"
            image.save(query_path)

            yy, xx = np.indices((160, 220), dtype=np.float32)
            world_points = np.stack([xx / 100.0, yy / 100.0, np.ones_like(xx) * 3.0], axis=-1)[None]
            intrinsic = np.asarray([[[180.0, 0.0, 110.0], [0.0, 180.0, 80.0], [0.0, 0.0, 1.0]]], dtype=np.float32)
            extrinsic = np.asarray([[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]], dtype=np.float32)
            np.savez_compressed(
                mapping_dir / "predictions.npz",
                schema_version=np.asarray(1, dtype=np.int32),
                frame_paths=np.asarray(["source.png"]),
                world_points=world_points.astype(np.float32),
                intrinsic=intrinsic,
                extrinsic_c2w=extrinsic,
            )

            localizer = OrbKeyframeLocalizer(mapping_dir, frame_stride=1, min_matches=4, min_inliers=4)
            result = localizer.localize(query_path)

            self.assertIn(result["status"], {"localized", "retrieved_only"})
            self.assertIsNotNone(result["best"])
            self.assertEqual(result["best"]["frame_index"], 0)
            self.assertGreater(result["best"]["match_count"], 0)

            pose = result_to_pose(result, min_confidence=0.0)
            self.assertIn(pose.status, {"ok", "low_confidence"})


if __name__ == "__main__":
    unittest.main()
