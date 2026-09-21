#!/usr/bin/env python3
"""Replay an existing mapping package as an incremental local-map update."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import resource
import statistics
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
    parser.add_argument("--resource-sample-every", type=int, default=1, help="Record resource metrics every N map updates")
    parser.add_argument("--benchmark-label", default="default")
    parser.add_argument("--resource-sample-every", type=int, default=1, help="Record resource metrics every N map updates")
    parser.add_argument("--benchmark-label", default="default")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resource_sample_every <= 0:
        raise SystemExit("--resource-sample-every must be positive")
    replay = PredictionPointCloudReplay(args.mapping_package, max_points_per_window=args.max_points_per_window)
    fusion = IncrementalVoxelMap(voxel_size_m=args.voxel_size_m, max_points=args.max_points)
    manager = LiveMapManager(args.output_dir, max_points=args.max_points)
    records = []
    started = time.perf_counter()
    latency_samples = []

    def output_bytes() -> int:
        return sum(path.stat().st_size for path in args.output_dir.rglob("*") if path.is_file()) if args.output_dir.exists() else 0

    def rss_mb() -> float:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 3)

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
        latency_samples.append(record["latency_ms"])
        if result.map_version % args.resource_sample_every == 0:
            record.update({"rss_mb": rss_mb(), "output_bytes": output_bytes(), "voxel_count": result.fused_points})
        latency_samples.append(record["latency_ms"])
        if result.map_version % args.resource_sample_every == 0:
            record.update({"rss_mb": rss_mb(), "output_bytes": output_bytes(), "voxel_count": result.fused_points})
        records.append(record)
        print(json.dumps(record), flush=True)

    summary = {
        "schema_version": 1,
        "source_package": str(args.mapping_package.resolve()),
        "benchmark_label": args.benchmark_label,
        "window_size": args.window_size,
        "process_every": args.process_every,
        "map_updates": len(records),
        "total_latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "latency_mean_ms": round(statistics.fmean(latency_samples), 3) if latency_samples else None,
        "latency_p50_ms": round(statistics.median(latency_samples), 3) if latency_samples else None,
        "latency_p95_ms": round(sorted(latency_samples)[max(0, int(len(latency_samples) * 0.95) - 1)], 3) if latency_samples else None,
        "peak_rss_mb": rss_mb(),
        "final_output_bytes": output_bytes(),
        "final_voxel_count": fusion.points_xyz.shape[0],
        "records": records,
        "note": "Replay uses existing world_points from predictions.npz; it is not online RGB depth inference.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
