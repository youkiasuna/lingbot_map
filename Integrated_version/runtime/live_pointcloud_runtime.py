#!/usr/bin/env python3
"""Run RTSP-only live 3D mapping without visual localization or motor control."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import threading
import time

from runtime.frame_queue import FramePacket
from runtime.incremental_map_fusion import IncrementalVoxelMap
from runtime.lingbot_map_session import LingBotMapSession, LingBotMapSessionConfig
from runtime.live_map_manager import LiveMapManager
from runtime.streaming_mapping_worker import (
    StreamingMappingWorker,
    StreamingMappingWorkerConfig,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="RTSP URL or camera index")
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--lingbot-root", required=True, type=Path)
    parser.add_argument("--live-map-dir", type=Path, default=Path("outputs/runtime/online_navigation"))
    parser.add_argument("--window-size", type=int, default=10)
    parser.add_argument("--process-every", type=int, default=10)
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--voxel-size-m", type=float, default=0.03)
    parser.add_argument("--max-points", type=int, default=250000)
    return parser.parse_args()


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> int:
    import cv2

    args = parse_args()
    if args.max_frames < 0 or args.max_windows < 0:
        raise SystemExit("max-frames and max-windows cannot be negative")
    if args.window_size <= 0 or args.process_every <= 0:
        raise SystemExit("window-size and process-every must be positive")

    capture = cv2.VideoCapture(camera_source(args.url))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera source: {args.url}")

    live_manager = LiveMapManager(args.live_map_dir, max_points=args.max_points)
    fusion = IncrementalVoxelMap(
        voxel_size_m=args.voxel_size_m,
        max_points=args.max_points,
    )
    session = LingBotMapSession(LingBotMapSessionConfig(
        model_path=args.model_path.resolve(),
        lingbot_root=args.lingbot_root.resolve(),
        write_archive=False,
    ))
    stop_event = threading.Event()
    reader_error: list[str] = []
    submitted = 0

    def on_result(result: dict) -> None:
        fusion_result = fusion.update(result["points_xyz"])
        live_manager.publish_map_update(
            fusion.points_xyz,
            frame_count=int(result["end_sequence"]) + 1,
            keyframe_count=args.window_size,
            tracked_ratio=1.0,
            navigable=True,
        )
        live_manager.publish_status(
            mode="MAPPING",
            mapping_backend="lingbot",
            mapping_window_id=result["window_id"],
            mapping_map_version=fusion_result.map_version,
            mapping_input_points=fusion_result.input_points,
            mapping_fused_points=fusion_result.fused_points,
            mapping_timings_ms=result.get("timings_ms", {}),
            worker_error=None,
        )
        print(json.dumps({
            "event": "map_update",
            "window_id": result["window_id"],
            "map_version": fusion_result.map_version,
            "input_points": fusion_result.input_points,
            "fused_points": fusion_result.fused_points,
            "timings_ms": result.get("timings_ms", {}),
        }), flush=True)

    worker = StreamingMappingWorker(
        session,
        StreamingMappingWorkerConfig(
            window_size=args.window_size,
            process_every=args.process_every,
            max_windows=args.max_windows,
        ),
        on_result,
    )
    worker.start()
    print(json.dumps({
        "event": "live_mapping_started",
        "url": args.url,
        "live_map_dir": str(args.live_map_dir),
        "model_load_ms": session.model_load_ms,
        "mode": "MAPPING_ONLY",
    }), flush=True)

    try:
        while not stop_event.is_set() and (args.max_frames == 0 or submitted < args.max_frames):
            ok, frame = capture.read()
            if not ok:
                reader_error.append("camera_frame_unavailable")
                break
            worker.submit(FramePacket(submitted, frame, time.time()))
            submitted += 1
            if args.max_windows and worker.processed_windows >= args.max_windows:
                break
    finally:
        worker.stop(timeout_s=30.0)
        capture.release()
        live_manager.publish_status(
            mode="STOPPED",
            mapping_only=True,
            submitted_frames=submitted,
            processed_windows=worker.processed_windows,
            reader_error=reader_error[0] if reader_error else None,
            worker_error=str(worker.error) if worker.error else None,
        )
    if worker.error:
        raise worker.error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
