import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from demo_storage import discard_session, finish_session, new_session, save_session


class DemoStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pending = self.root / "tmp"
        self.saved = self.root / "saved"
        self.captures = self.root / "captures"

    def save(self, session):
        return save_session(session, self.saved, self.pending, self.captures)

    def test_save_separates_raw_frames_and_preserves_results(self):
        session = new_session("demo", self.pending)
        frames = session / "live/current/frames"
        frames.mkdir(parents=True)
        (frames / "000000.jpg").write_bytes(b"frame")
        (session / "result.json").write_text(json.dumps({"frames": str(frames)}))
        target = self.save(session)
        self.assertFalse(session.exists())
        self.assertTrue((target / "live/current/frames").is_symlink())
        self.assertEqual((target / "live/current/frames/000000.jpg").read_bytes(), b"frame")
        self.assertEqual(json.loads((target / "result.json").read_text())["frames"], str(target / "live/current/frames"))

    def test_failure_preserves_only_copy(self):
        session = new_session("demo", self.pending)
        (session / "result.json").write_text("invalid json")
        with self.assertRaises(ValueError):
            self.save(session)
        self.assertTrue(session.exists())
        self.assertFalse((self.saved / session.name).exists())

    def test_existing_destination_is_never_overwritten(self):
        session = new_session("demo", self.pending)
        (self.saved / session.name).mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.save(session)
        self.assertTrue(session.exists())

    def test_discard_cannot_delete_external_directory(self):
        external = self.root / "research"
        external.mkdir()
        with self.assertRaises(ValueError):
            discard_session(external, self.pending)
        self.assertTrue(external.exists())

    def test_discard_does_not_follow_links_to_raw_data(self):
        raw = self.root / "original.jpg"
        raw.write_bytes(b"original")
        session = new_session("demo", self.pending)
        (session / "image.jpg").symlink_to(raw)
        discard_session(session, self.pending)
        self.assertEqual(raw.read_bytes(), b"original")

    def test_running_session_cannot_be_discarded_externally(self):
        session = new_session("demo", self.pending)
        (session / "storage.json").write_text(json.dumps({"active_pid": os.getppid()}))
        with self.assertRaises(ValueError):
            discard_session(session, self.pending)

    def test_noninteractive_keeps_pending_result(self):
        session = new_session("demo", self.pending)
        with patch("sys.stdin.isatty", return_value=False):
            finish_session(session, self.saved, self.pending)
        self.assertTrue(session.exists())
        self.assertEqual(json.loads((session / "storage.json").read_text())["state"], "pending")

    def test_unique_sessions_and_invalid_names(self):
        self.assertNotEqual(new_session("demo", self.pending), new_session("demo", self.pending))
        with self.assertRaises(ValueError):
            new_session("../research", self.pending)


if __name__ == "__main__":
    unittest.main()
