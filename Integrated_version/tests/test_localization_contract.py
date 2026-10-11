import json
from pathlib import Path
import tempfile
import unittest

from Integrated_version.localization.localizer_interface import FilePosePublisher, PoseSample


class LocalizationContractTests(unittest.TestCase):
    def test_pose_payload_round_trips_optional_localization_metrics(self):
        pose = PoseSample(
            x_m=1.23456,
            y_m=-2.0,
            yaw_deg=370.0,
            timestamp_unix=123.0,
            source="orb_pnp",
            confidence=0.87654,
            inlier_count=17,
            reprojection_error_px=1.25,
            frame_id="query_1",
        )

        restored = PoseSample.from_payload(pose.to_payload())

        self.assertEqual(restored.x_m, 1.2346)
        self.assertEqual(restored.yaw_deg, 10.0)
        self.assertEqual(restored.inlier_count, 17)
        self.assertEqual(restored.frame_id, "query_1")

    def test_file_publisher_creates_parent_and_writes_pose_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested/current_pose.json"
            pose = PoseSample(1.0, 2.0, 45.0, 123.0, "fixture", 0.9)

            FilePosePublisher(path).publish(pose)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), pose.to_payload())


if __name__ == "__main__":
    unittest.main()
