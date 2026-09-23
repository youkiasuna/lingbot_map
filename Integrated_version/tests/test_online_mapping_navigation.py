from __future__ import annotations
import time
import unittest

from runtime.frame_queue import FramePacket, LatestFrameQueue


class LatestFrameQueueTests(unittest.TestCase):
    def test_queue_keeps_latest_and_counts_drops(self) -> None:
        queue = LatestFrameQueue()
        queue.put(FramePacket(1, "old", time.time()))
        queue.put(FramePacket(2, "new", time.time()))
        packet = queue.get_latest()
        self.assertIsNotNone(packet)
        self.assertEqual(packet.sequence, 2)
        self.assertEqual(queue.dropped_count, 1)
        self.assertIsNone(queue.get_latest())

    def test_packet_converts_to_shared_frame_record(self) -> None:
        packet = FramePacket(7, "image", 12.5)
        record = packet.to_record(source="rtsp")
        self.assertEqual(record.frame_id, 7)
        self.assertEqual(record.timestamp_ns, 12_500_000_000)
        self.assertEqual(record.source, "rtsp")

    def test_invalid_queue_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LatestFrameQueue(0)


if __name__ == "__main__":
    unittest.main()
