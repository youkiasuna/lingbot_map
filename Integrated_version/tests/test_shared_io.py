from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from Integrated_version.map.pgm_io import write_pgm
from Integrated_version.runtime.video_source import camera_source
from Integrated_version.shared.json_io import atomic_write_json
from Integrated_version.shared.npz_io import atomic_write_npz


class SharedIoTests(unittest.TestCase):
    def test_pgm_writer_emits_binary_header_and_exact_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.pgm"
            write_pgm(path, 2, 1, b"\x00\xfe")

            self.assertEqual(path.read_bytes(), b"P5\n2 1\n255\n\x00\xfe")

    def test_camera_index_is_numeric_but_stream_url_stays_text(self):
        self.assertEqual(camera_source("0"), 0)
        self.assertEqual(camera_source("12"), 12)
        self.assertEqual(camera_source("rtsp://camera/live"), "rtsp://camera/live")

    def test_atomic_json_writer_replaces_destination_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested/result.json"
            path.parent.mkdir()
            path.write_text('{"old":true}', encoding="utf-8")

            atomic_write_json(path, {"new": True})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"new":true}\n')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_atomic_json_writer_preserves_requested_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "formatted.json"
            atomic_write_json(path, {"label": "繁體中文"}, indent=2, ensure_ascii=False)

            content = path.read_text(encoding="utf-8")
            self.assertIn('  "label": "繁體中文"', content)

    def test_atomic_json_writer_keeps_old_file_and_cleans_temp_on_replace_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            path.write_text('{"old":true}\n', encoding="utf-8")
            with patch("Integrated_version.shared.json_io.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {"new": True})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"old":true}\n')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_atomic_npz_writer_preserves_old_archive_and_cleans_temp_on_replace_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.npz"
            np.savez_compressed(path, value=np.array([1]))
            with patch("Integrated_version.shared.npz_io.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    atomic_write_npz(path, {"value": np.array([2])})

            with np.load(path) as archive:
                np.testing.assert_array_equal(archive["value"], [1])
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
