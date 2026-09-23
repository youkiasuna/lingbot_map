import unittest
import tempfile
from pathlib import Path

from Integrated_version.schemas import (
    CAMERA_FRAME,
    NAVIGATION_XZ_FRAME,
    RECONSTRUCTION_FRAME,
    TIMESTAMP_ARRIVAL,
    FrameRecord,
    LocalizationResult,
    MapStatusRecord,
    MappingWindowRecord,
    NavigationCommand,
    PointCloudRecord,
    PoseRecord,
)
from Integrated_version.runtime.live_map_manager import LiveMapManager


class CoreSchemaTests(unittest.TestCase):
    def test_records_are_json_compatible(self):
        pose = PoseRecord(
            position_xyz=[1.0, 2.0, 3.0],
            rotation_quaternion_xyzw=[0.0, 0.0, 0.0, 1.0],
            coordinate_frame=RECONSTRUCTION_FRAME,
        )
        result = LocalizationResult(
            query_id="query_000025",
            method="orb_keyframe_pnp",
            status="accepted",
            pose=pose,
            match_count=20,
            inlier_count=12,
        )

        payload = result.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["pose"]["position_xyz"], [1.0, 2.0, 3.0])
        self.assertEqual(payload["pose"]["coordinate_frame"], RECONSTRUCTION_FRAME)

    def test_coordinate_and_timestamp_constants_are_explicit(self):
        self.assertEqual(CAMERA_FRAME, "camera")
        self.assertEqual(NAVIGATION_XZ_FRAME, "navigation_xz")
        self.assertEqual(TIMESTAMP_ARRIVAL, "arrival")

    def test_localization_record_contains_quality_metrics(self):
        result = LocalizationResult(
            query_id="frame_0001",
            method="orb_keyframe_pnp",
            status="low_confidence",
            match_count=20,
            inlier_count=0,
            inlier_ratio=0.0,
            reprojection_error_px=None,
        )

        payload = result.to_dict()

        self.assertEqual(payload["match_count"], 20)
        self.assertEqual(payload["inlier_ratio"], 0.0)
        self.assertIsNone(payload["reprojection_error_px"])

    def test_defaults_are_safe_for_live_pipeline(self):
        frame = FrameRecord(frame_id=0, timestamp_ns=123, source=CAMERA_FRAME)
        cloud = PointCloudRecord(
            points_file="live_points.npz", point_count=0, map_version=1
        )
        command = NavigationCommand(
            timestamp_ns=123, linear_mps=0.0, angular_rps=0.0
        )

        self.assertIsNone(frame.image_path)
        self.assertEqual(frame.timestamp_source, TIMESTAMP_ARRIVAL)
        self.assertFalse(cloud.has_rgb)
        self.assertIsNone(cloud.colors_file)
        self.assertIsNone(cloud.color_format)
        self.assertEqual(command.status, "safety_stop")
        self.assertEqual(command.source, "dry_run")

    def test_mapping_window_record_contains_nested_metadata(self):
        record = MappingWindowRecord(
            window_id="window_000000_000009",
            start_frame=0,
            end_frame=9,
            backend="lingbot_map_streaming",
            frame_records=[FrameRecord(0, 123, CAMERA_FRAME)],
            pointcloud_record=PointCloudRecord(
                points_file="in_memory_world_points",
                point_count=5,
                map_version=0,
                source_frames=list(range(10)),
            ),
        )
        payload = record.to_dict()
        self.assertEqual(payload["window_id"], "window_000000_000009")
        self.assertEqual(payload["frame_records"][0]["frame_id"], 0)
        self.assertEqual(payload["pointcloud_record"]["point_count"], 5)

    def test_navigation_command_adapts_existing_twist_shape(self):
        class ExistingTwist:
            linear_mps = 0.25
            angular_rps = -0.1
            status = "tracking"

        command = NavigationCommand.from_twist(
            ExistingTwist(), timestamp_ns=456, source="planner"
        )

        self.assertEqual(command.to_dict()["timestamp_ns"], 456)
        self.assertEqual(command.to_dict()["status"], "tracking")
        self.assertEqual(command.to_dict()["source"], "planner")

    def test_live_map_manager_keeps_legacy_fields_and_adds_records(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = LiveMapManager(Path(directory))
            accepted = manager.publish_map_update(
                [[1.0, 2.0, 3.0]],
                frame_count=1,
                keyframe_count=1,
                tracked_ratio=1.0,
                navigable=True,
            )
            payload = __import__("json").loads(
                (Path(directory) / "live_map.json").read_text(encoding="utf-8")
            )

        self.assertTrue(accepted)
        self.assertEqual(payload["map_version"], 1)
        self.assertEqual(payload["quality"]["point_count"], 1)
        self.assertEqual(payload["record"]["point_count"], 1)
        self.assertEqual(payload["record"]["points_file"], "live_points.npz")

    def test_live_status_keeps_legacy_fields_and_adds_record(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = LiveMapManager(Path(directory))
            manager.publish_status(mode="MAPPING_ONLY", map_ready=True)
            payload = __import__("json").loads(
                (Path(directory) / "live_status.json").read_text(encoding="utf-8")
            )

        self.assertEqual(payload["mode"], "MAPPING_ONLY")
        self.assertTrue(payload["map_ready"])
        self.assertEqual(payload["record"]["mode"], "MAPPING_ONLY")
        self.assertEqual(payload["record"]["map_version"], 0)


if __name__ == "__main__":
    unittest.main()
