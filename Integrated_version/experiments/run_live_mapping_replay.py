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
from runtime.local_pointcloud_backend import PredictionNpzBackend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-package", type=Path, help="Existing predictions.npz for the prediction backend")
    parser.add_argument("--backend", choices=("prediction", "lingbot"), default="prediction")
    parser.add_argument("--source-dir", type=Path, help="Input image directory for the LingBot-MAP backend")
    parser.add_argument("--model-path", type=Path, help="LingBot-MAP model checkpoint")
    parser.add_argument("--lingbot-root", type=Path, default=Path("lingbot-map-main"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=10)
    parser.add_argument("--process-every", type=int, default=5)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--voxel-size-m", type=float, default=0.03)
    parser.add_argument("--max-points", type=int, default=250000)
    parser.add_argument("--max-points-per-window", type=int, default=100000)
    parser.add_argument("--resource-sample-every", type=int, default=1, help="Record resource metrics every N map updates")
    parser.add_argument("--benchmark-label", default="default")
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--keep-window-packages", action="store_true", help="Keep per-window LingBot predictions.npz packages")
    parser.add_argument("--persistent-worker", action="store_true", help="Keep one LingBot model session for all windows")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resource_sample_every <= 0:
        raise SystemExit("--resource-sample-every must be positive")
    if args.backend == "prediction":
        if args.mapping_package is None:
            raise SystemExit("--mapping-package is required for --backend prediction")
        backend = PredictionNpzBackend(args.mapping_package, max_points_per_window=args.max_points_per_window)
    else:
        from runtime.lingbot_map_backend import LingBotMapBackend, LingBotMapBackendConfig
        if args.source_dir is None or args.model_path is None:
            raise SystemExit("--source-dir and --model-path are required for --backend lingbot")
        backend = LingBotMapBackend(LingBotMapBackendConfig(
            source_dir=args.source_dir,
            model_path=args.model_path,
            lingbot_root=args.lingbot_root,
            output_root=args.output_dir / "lingbot_windows",
            max_points_per_window=args.max_points_per_window,
            keep_window_packages=args.keep_window_packages,
            persistent_session=args.persistent_worker,
        ))
    fusion = IncrementalVoxelMap(voxel_size_m=args.voxel_size_m, max_points=args.max_points)
    manager = LiveMapManager(args.output_dir, max_points=args.max_points)
    records = []
    started = time.perf_counter()
    latency_samples = []
    session_timings = {}

    def output_bytes() -> int:
        return sum(path.stat().st_size for path in args.output_dir.rglob("*") if path.is_file()) if args.output_dir.exists() else 0

    def rss_mb() -> float:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 3)

    for local_result in backend.iter_generate(
        window_size=args.window_size,
        process_every=args.process_every,
        max_frames=args.max_frames,
        max_windows=args.max_windows,
    ):
        update_started = time.perf_counter()
        result = fusion.update(local_result.points_xyz)
        accepted = manager.publish_map_update(
            fusion.points_xyz,
            frame_count=local_result.end_frame + 1,
            keyframe_count=local_result.end_frame - local_result.start_frame + 1,
            tracked_ratio=1.0,
            navigable=True,
        )
        backend_timings = dict(local_result.timings_ms)
        if "model_load" in backend_timings:
            session_timings["model_load_ms"] = backend_timings.pop("model_load")
        record = {
            "map_version": result.map_version,
            "backend": local_result.backend,
            "start_frame": local_result.start_frame,
            "end_frame": local_result.end_frame,
            "backend_latency_ms": local_result.latency_ms,
            "backend_timings_ms": backend_timings,
            "input_points": result.input_points,
            "fused_points": result.fused_points,
            "accepted": accepted,
            "latency_ms": round((time.perf_counter() - update_started) * 1000.0, 3),
        }
        latency_samples.append(record["latency_ms"])
        if result.map_version % args.resource_sample_every == 0:
            record.update({"rss_mb": rss_mb(), "output_bytes": output_bytes(), "voxel_count": result.fused_points})
        records.append(record)
        print(json.dumps(record), flush=True)

    summary = {
        "schema_version": 1,
        "source_package": str(args.mapping_package.resolve()) if args.mapping_package else None,
        "backend": args.backend,
        "session_timings_ms": session_timings,
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
        "final_voxel_count": int(fusion.points_xyz.shape[0]),
        "records": records,
        "note": (
            "Replay uses existing world_points from predictions.npz; it is not online RGB depth inference."
            if args.backend == "prediction"
            else "LingBot-MAP generated predictions.npz for selected windows; this is windowed offline inference, not streaming inference."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
