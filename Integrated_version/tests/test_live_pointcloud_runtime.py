from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from runtime.live_pointcloud_runtime import resolve_source_mode


class LivePointcloudRuntimeSourceModeTests(unittest.TestCase):
    def test_auto_treats_existing_file_as_video(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4") as handle:
            self.assertEqual(resolve_source_mode(handle.name, "auto"), "video")

    def test_auto_treats_camera_index_as_live(self) -> None:
        self.assertEqual(resolve_source_mode("0", "auto"), "live")

    def test_auto_treats_rtsp_url_as_live(self) -> None:
        self.assertEqual(resolve_source_mode("rtsp://192.168.50.51:8554/live", "auto"), "live")

    def test_explicit_mode_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames"
            path.mkdir()
            self.assertEqual(resolve_source_mode(str(path), "live"), "live")
            self.assertEqual(resolve_source_mode(str(path), "video"), "video")


if __name__ == "__main__":
    unittest.main()
