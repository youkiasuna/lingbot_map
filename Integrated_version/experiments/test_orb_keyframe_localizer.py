import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from Integrated_version.experiments.orb_keyframe_localizer import OrbKeyframeLocalizer, result_to_pose


class OrbKeyframeLocalizerTest(unittest.TestCase):
    def test_retrieves_identical_frame_and_publishes_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping_dir = Path(tmp) / "mapping"
            preprocessed = mapping_dir / "preprocessed"
            preprocessed.mkdir(parents=True)

            image = np.zeros((160, 220, 3), dtype=np.uint8)
            cv2.putText(image, "LAB", (35, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.7, (255, 255, 255), 3)
            cv2.circle(image, (150, 45), 22, (255, 255, 255), 2)
            cv2.line(image, (20, 130), (200, 125), (255, 255, 255), 3)
            cv2.imwrite(str(preprocessed / "000000.png"), image)
            query_path = Path(tmp) / "query.png"
            cv2.imwrite(str(query_path), image)

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
