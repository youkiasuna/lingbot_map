from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from runtime.exploration_recorder import ExplorationFrameRecorder


class ExplorationRecorderTests(unittest.TestCase):
    def test_records_selected_frames_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recorder = ExplorationFrameRecorder(tmp, frame_every=2)
            frame = np.zeros((8, 12, 3), dtype=np.uint8)
            self.assertFalse(recorder.record(cv2, frame, frame_id=1, timestamp_unix=1.0))
            self.assertTrue(recorder.record(cv2, frame, frame_id=2, timestamp_unix=2.0))
            self.assertFalse(recorder.record(cv2, frame, frame_id=2, timestamp_unix=3.0))
            self.assertEqual(recorder.saved_frames, 1)
            self.assertTrue((Path(tmp) / "frames/000002.jpg").exists())
            manifest = (Path(tmp) / "frames.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(manifest), 1)
            self.assertEqual(json.loads(manifest[0])["frame_id"], 2)
            session = json.loads((Path(tmp) / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["saved_frames"], 1)


if __name__ == "__main__":
    unittest.main()
