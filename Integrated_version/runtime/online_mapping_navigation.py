#!/usr/bin/env python3
"""RTSP latest-frame visual navigation dry-run."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import threading
import time

from runtime.frame_queue import FramePacket, LatestFrameQueue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--waypoints", type=Path)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--queue-size", type=int, default=1)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--max-pose-age-s", type=float, default=0.5)
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--resize-mode", choices=("stretch", "letterbox", "cover_crop"), default="cover_crop")
    parser.add_argument("--live-map-dir", type=Path, default=Path("outputs/runtime/online_navigation"))
    parser.add_argument("--command-log", type=Path, default=Path("outputs/runtime/online_navigation_commands.jsonl"))
    return parser.parse_args()


def load_waypoints(path: Path | None) -> list[tuple[float, float]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["waypoints"] if isinstance(payload, dict) else payload
    return [(float(item[0]), float(item[1])) for item in raw]


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> int:
    import cv2
    from experiments.orb_keyframe_localizer import OrbRelocalizer
    from hardware.esp32_adapter import Esp32Adapter, Esp32Config
    from localization.pose_gate import PoseGate, PoseGateConfig
    from planner.pure_pursuit import PurePursuit
    from runtime.live_map_manager import LiveMapManager
    from runtime.live_viewer_state import LiveViewerState
    from runtime.navigation_manager import NavigationManager
    args = parse_args()
    if args.queue_size <= 0 or args.max_frames < 0:
        raise SystemExit("queue-size must be positive and max-frames cannot be negative")
    capture = cv2.VideoCapture(camera_source(args.url))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera source: {args.url}")

    localizer = OrbRelocalizer(args.mapping_dir, max_features=args.max_features, frame_stride=args.frame_stride)
    manager = NavigationManager(
        PoseGate(PoseGateConfig(min_confidence=args.min_confidence, max_age_s=args.max_pose_age_s)),
        PurePursuit(),
    )
    manager.set_path(load_waypoints(args.waypoints))
    live_manager = LiveMapManager(args.live_map_dir)
    viewer_state = LiveViewerState(live_manager)
    adapter = Esp32Adapter(Esp32Config(dry_run=True, command_log_path=args.command_log))
    queue = LatestFrameQueue(args.queue_size)
    stop_event = threading.Event()
    reader_error: list[str] = []

    def reader() -> None:
        sequence = 0
        while not stop_event.is_set():
            ok, frame = capture.read()
            if not ok:
                reader_error.append("camera_frame_unavailable")
                stop_event.set()
                return
            queue.put(FramePacket(sequence, frame, time.time()))
            sequence += 1

    reader_thread = threading.Thread(target=reader, name="rtsp-reader", daemon=True)
    reader_thread.start()
    processed = 0
    started = time.perf_counter()
    last_log = 0.0
    print(json.dumps({"event": "online_runtime_started", "url": args.url, "queue_size": args.queue_size, "mapping_dir": str(args.mapping_dir), "live_map_dir": str(args.live_map_dir), "dry_run": True}), flush=True)

    try:
        while not stop_event.is_set() and (args.max_frames == 0 or processed < args.max_frames):
            packet = queue.get_latest()
            if packet is None:
                time.sleep(0.001)
                continue
            result = localizer.localize_frame(packet.frame, query_id=f"rtsp_{packet.sequence:06d}", resize_mode=args.resize_mode)
            state = manager.update(result)
            pose = state.pose
            viewer_state.update(
                position_xyz=pose.position_xyz if pose and pose.accepted else None,
                yaw_deg=pose.yaw_deg if pose and pose.accepted else None,
                confidence=pose.confidence if pose else 0.0,
                localization_status=result.get("status", "unknown"),
                mode=state.mode,
                path_xz=manager.waypoints,
            )
            if state.command.status == "safety_stop":
                adapter.stop()
            else:
                adapter.send(state.command)
            processed += 1
            elapsed = max(time.perf_counter() - started, 1e-6)
            now = time.perf_counter()
            if now - last_log >= 1.0 or processed == 1:
                print(json.dumps({"event": "online_frame", "sequence": packet.sequence, "processed_frames": processed, "dropped_frames": queue.dropped_count, "frame_age_ms": round((time.time() - packet.timestamp_unix) * 1000.0, 3), "processing_fps": round(processed / elapsed, 3), "localization_status": result.get("status", "unknown"), "mode": state.mode, "command": state.command.status}), flush=True)
                last_log = now
    finally:
        stop_event.set()
        reader_thread.join(timeout=1.0)
        adapter.stop()
        capture.release()
        live_manager.publish_status(mode="STOPPED", reader_error=reader_error[0] if reader_error else None, processed_frames=processed, dropped_frames=queue.dropped_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
