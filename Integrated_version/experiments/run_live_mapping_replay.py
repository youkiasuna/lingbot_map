#!/usr/bin/env python3
"""Replay an existing mapping package as an incremental local-map update."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from runtime.incremental_map_fusion import IncrementalVoxelMap
from runtime.live_map_manager import LiveMapManager
from runtime.local_pointcloud_replay import PredictionPointCloudReplay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-package", type=Path, required=True, help="Existing predictions.npz")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=10)
    parser.add_argument("--process-every", type=int, default=5)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--voxel-size-m", type=float, default=0.03)
    parser.add_argument("--max-points", type=int, default=250000)
    parser.add_argument("--max-points-per-window", type=int, default=100000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    replay = PredictionPointCloudReplay(args.mapping_package, max_points_per_window=args.max_points_per_window)
    fusion = IncrementalVoxelMap(voxel_size_m=args.voxel_size_m, max_points=args.max_points)
    manager = LiveMapManager(args.output_dir, max_points=args.max_points)
    records = []
    started = time.perf_counter()

    for window in replay.windows(
        window_size=args.window_size,
        process_every=args.process_every,
        max_frames=args.max_frames,
    ):
        update_started = time.perf_counter()
        result = fusion.update(window.points_xyz)
        accepted = manager.publish_map_update(
            fusion.points_xyz,
            frame_count=window.end_frame + 1,
            keyframe_count=window.end_frame - window.start_frame + 1,
            tracked_ratio=1.0,
            navigable=True,
        )
        record = {
            "map_version": result.map_version,
            "start_frame": window.start_frame,
            "end_frame": window.end_frame,
            "input_points": result.input_points,
            "fused_points": result.fused_points,
            "accepted": accepted,
            "latency_ms": round((time.perf_counter() - update_started) * 1000.0, 3),
        }
        records.append(record)
        print(json.dumps(record), flush=True)

    summary = {
        "schema_version": 1,
        "source_package": str(args.mapping_package.resolve()),
        "window_size": args.window_size,
        "process_every": args.process_every,
        "map_updates": len(records),
        "total_latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "records": records,
        "note": "Replay uses existing world_points from predictions.npz; it is not online RGB depth inference.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
