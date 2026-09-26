from __future__ import annotations

import time
import unittest

import numpy as np

from runtime.live_orb_worker import LatestFrameOrbWorker


class FakeLocalizer:
    def localize_frame(self, frame, *, query_id, resize_mode):
        time.sleep(0.01)
        return {
            "status": "lost",
            "query_image": query_id,
            "best": None,
            "latency_ms": 10.0,
        }


class LatestFrameOrbWorkerTests(unittest.TestCase):
    def test_worker_drops_stale_frames_and_stops(self) -> None:
        results = []
        worker = LatestFrameOrbWorker(FakeLocalizer(), results.append)
        worker.start()
        for index in range(20):
            worker.submit(np.zeros((4, 4, 3), dtype=np.uint8), f"frame_{index}")
        deadline = time.time() + 2.0
        while worker.processed_frames == 0 and time.time() < deadline:
            time.sleep(0.01)
        worker.stop()
        self.assertIsNone(worker.error)
        self.assertGreaterEqual(worker.processed_frames, 1)
        self.assertGreater(worker.dropped_frames, 0)
        self.assertEqual(worker.processed_frames, len(results))


if __name__ == "__main__":
    unittest.main()
