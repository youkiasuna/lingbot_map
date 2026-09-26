#!/usr/bin/env python3
"""Run persistent RTSP-only live 3D mapping without localization or motor control."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import threading
import time

from runtime.frame_queue import FramePacket
from experiments.orb_keyframe_localizer import OrbRelocalizer
from runtime.incremental_map_fusion import IncrementalVoxelMap
from runtime.lingbot_map_session import LingBotMapSession, LingBotMapSessionConfig
from runtime.live_orb_worker import LatestFrameOrbWorker
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
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--read-timeout-ms", type=int, default=10000)
    parser.add_argument("--reconnect-delay-s", type=float, default=1.0)
    parser.add_argument("--max-reconnects", type=int, default=0)
    parser.add_argument("--voxel-size-m", type=float, default=0.03)
    parser.add_argument("--max-points", type=int, default=250000)
    parser.add_argument("--extract-rgb", action="store_true", help="Persist aligned RGB colors in the live point-cloud snapshot")
    parser.add_argument("--localization-mapping-dir", type=Path, help="Optional ORB mapping package for same-frame relocalization")
    parser.add_argument("--localization-min-confidence", type=float, default=0.5)
    parser.add_argument("--localization-frame-stride", type=int, default=1)
    parser.add_argument("--localization-max-features", type=int, default=2000)
    return parser.parse_args()


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def write_live_frame(cv2, frame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / ".live_frame.jpg.tmp"
    destination = output_dir / "live_frame.jpg"
    if not cv2.imwrite(str(temporary), frame):
        raise OSError(f"failed to write {temporary}")
    os.replace(temporary, destination)


def open_capture(cv2, source: int | str, timeout_ms: int):
    capture = cv2.VideoCapture(
        source,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            timeout_ms,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            timeout_ms,
        ],
    )
    if not capture.isOpened():
        capture.release()
        return None
    return capture


def main() -> int:
    import cv2

    args = parse_args()
    if args.max_frames < 0 or args.max_windows < 0 or args.max_reconnects < 0:
        raise SystemExit("max-frames, max-windows, and max-reconnects cannot be negative")
    if args.window_size <= 0 or args.process_every <= 0 or args.fps <= 0:
        raise SystemExit("window-size, process-every, and fps must be positive")
    if args.read_timeout_ms <= 0 or args.reconnect_delay_s < 0:
        raise SystemExit("read-timeout-ms must be positive and reconnect-delay-s cannot be negative")
    if not 0.0 <= args.localization_min_confidence <= 1.0 or args.localization_frame_stride <= 0 or args.localization_max_features <= 0:
        raise SystemExit("localization confidence must be in [0, 1]; stride and max-features must be positive")

    live_manager = LiveMapManager(args.live_map_dir, max_points=args.max_points)
    fusion = IncrementalVoxelMap(
        voxel_size_m=args.voxel_size_m,
        max_points=args.max_points,
    )
    session = LingBotMapSession(LingBotMapSessionConfig(
        model_path=args.model_path.resolve(),
        lingbot_root=args.lingbot_root.resolve(),
        write_archive=False,
        extract_rgb=args.extract_rgb,
    ))
    localizer = None
    if args.localization_mapping_dir is not None:
        localizer = OrbRelocalizer(
            args.localization_mapping_dir.resolve(),
            max_features=args.localization_max_features,
            frame_stride=args.localization_frame_stride,
        )
    def on_localization(result: dict) -> None:
        best = result.get("best")
        accepted = (
            result.get("status") == "localized"
            and isinstance(best, dict)
            and isinstance(best.get("position_xyz"), list)
            and len(best["position_xyz"]) >= 3
            and best.get("yaw_deg") is not None
            and float(best.get("confidence", 0.0)) >= args.localization_min_confidence
        )
        confidence = float(best.get("confidence", 0.0)) if isinstance(best, dict) else 0.0
        live_manager.publish_pose(
            best["position_xyz"] if accepted else None,
            float(best["yaw_deg"]) if accepted else None,
            confidence=confidence,
            status="ok" if accepted else str(result.get("status", "lost")),
            timestamp_unix=float(result.get("timestamp_unix", time.time())),
        )
        live_manager.publish_status(
            localization_enabled=True,
            localization_status="localized" if accepted else str(result.get("status", "lost")),
            localization_confidence=confidence,
            localization_latency_ms=float(result.get("latency_ms", 0.0)),
        )

    orb_worker = (
        LatestFrameOrbWorker(localizer, on_localization)
        if localizer is not None else None
    )
    if orb_worker is not None:
        orb_worker.start()

    stop_event = threading.Event()
    reader_error: list[str] = []
    submitted = 0
    reconnects = 0

    def on_result(result: dict) -> None:
        fusion_result = fusion.update(
            result["points_xyz"],
            colors_rgb=result.get("colors_rgb"),
        )
        live_manager.publish_map_update(
            fusion.points_xyz,
            colors_rgb=fusion.colors_rgb,
            frame_count=int(result["end_sequence"]) + 1,
            keyframe_count=args.window_size,
            tracked_ratio=1.0,
            navigable=True,
        )
        live_manager.publish_status(
            mode="MAPPING",
            mapping_only=True,
            camera_connected=True,
            mapping_backend="lingbot",
            mapping_window_id=result["window_id"],
            mapping_map_version=fusion_result.map_version,
            mapping_input_points=fusion_result.input_points,
            mapping_fused_points=fusion_result.fused_points,
            rgb_available=fusion.colors_rgb is not None,
            rgb_source=result.get("rgb_source") if fusion.colors_rgb is not None else None,
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

    source = camera_source(args.url)
    capture = None
    next_submit = 0.0
    print(json.dumps({
        "event": "live_mapping_started",
        "url": args.url,
        "live_map_dir": str(args.live_map_dir),
        "model_load_ms": session.model_load_ms,
        "mode": "MAPPING_WITH_OPTIONAL_LOCALIZATION" if localizer is not None else "MAPPING_ONLY",
        "fps": args.fps,
        "localization_enabled": localizer is not None,
    }), flush=True)

    try:
        while not stop_event.is_set() and (args.max_frames == 0 or submitted < args.max_frames):
            if args.max_windows and worker.processed_windows >= args.max_windows:
                break
            if capture is None:
                capture = open_capture(cv2, source, args.read_timeout_ms)
                if capture is None:
                    reconnects += 1
                    live_manager.publish_status(
                        mode="RECONNECTING",
                        mapping_only=True,
                        camera_connected=False,
                        reconnect_count=reconnects,
                        reader_error="camera_open_failed",
                    )
                    if args.max_reconnects and reconnects >= args.max_reconnects:
                        reader_error.append("camera_open_failed")
                        break
                    time.sleep(args.reconnect_delay_s)
                    continue
                reconnects = 0
                live_manager.publish_status(
                    mode="MAPPING",
                    mapping_only=True,
                    camera_connected=True,
                    reconnect_count=0,
                    reader_error=None,
                )

            ok, frame = capture.read()
            if not ok or frame is None:
                capture.release()
                capture = None
                reconnects += 1
                live_manager.publish_status(
                    mode="RECONNECTING",
                    mapping_only=True,
                    camera_connected=False,
                    reconnect_count=reconnects,
                    reader_error="camera_read_failed",
                )
                if args.max_reconnects and reconnects >= args.max_reconnects:
                    reader_error.append("camera_read_failed")
                    break
                time.sleep(args.reconnect_delay_s)
                continue

            now = time.perf_counter()
            if now < next_submit:
                continue
            next_submit = now + 1.0 / args.fps
            write_live_frame(cv2, frame, args.live_map_dir)
            worker.submit(FramePacket(submitted, frame, time.time()))
            submitted += 1
            if orb_worker is not None:
                orb_worker.submit(
                    frame,
                    query_id=f"camera_{submitted - 1:06d}",
                )
            live_manager.publish_status(
                mode="MAPPING",
                mapping_only=True,
                camera_connected=True,
                last_frame_unix=time.time(),
                submitted_frames=submitted,
                processed_windows=worker.processed_windows,
                reconnect_count=reconnects,
            )
    except KeyboardInterrupt:
        print("\nStopping live mapping.", flush=True)
    finally:
        stop_event.set()
        if capture is not None:
            capture.release()
        if orb_worker is not None:
            orb_worker.stop(timeout_s=10.0)
        worker.stop(timeout_s=30.0)
        live_manager.publish_status(
            mode="STOPPED",
            mapping_only=True,
            camera_connected=False,
            submitted_frames=submitted,
            processed_windows=worker.processed_windows,
            reconnect_count=reconnects,
            reader_error=reader_error[0] if reader_error else None,
            worker_error=str(worker.error) if worker.error else None,
        )

    if orb_worker is not None and orb_worker.error:
        raise orb_worker.error
    if worker.error:
        raise worker.error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
