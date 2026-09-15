#!/usr/bin/env python3
"""Replay saved LingBot predictions as an online incremental mapping stream."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Integrated_version.map.incremental_voxel_map import (
    IncrementalVoxelMap,
    estimate_floor_height,
)


DEFAULT_ARCHIVE = ROOT / "outputs/scenes/scene_20260818/mapping/predictions.npz"
DEFAULT_OUTPUT = ROOT / "outputs/scenes/scene_20260818/online_replay"


def frame_points(
    world_points: np.ndarray,
    confidence: np.ndarray | None,
    frame_index: int,
    sample_stride: int,
    conf_threshold: float,
) -> tuple[np.ndarray, np.ndarray | None]:
    points = world_points[frame_index][::sample_stride, ::sample_stride].reshape(-1, 3)
    conf = None
    if confidence is not None:
        conf = confidence[frame_index][::sample_stride, ::sample_stride].reshape(-1)
        keep = conf >= conf_threshold
        points = points[keep]
        conf = conf[keep]
    keep = np.isfinite(points).all(axis=1)
    points = points[keep].astype(np.float32, copy=False)
    if conf is not None:
        conf = conf[keep].astype(np.float32, copy=False)
    return points, conf


def collect_bootstrap_points(
    world_points: np.ndarray,
    confidence: np.ndarray | None,
    bootstrap_frames: int,
    sample_stride: int,
    conf_threshold: float,
) -> np.ndarray:
    frames = min(bootstrap_frames, world_points.shape[0])
    chunks = []
    for frame_index in range(frames):
        points, _ = frame_points(world_points, confidence, frame_index, sample_stride, conf_threshold)
        chunks.append(points)
    if not chunks:
        raise ValueError("No bootstrap frames were available.")
    points = np.concatenate(chunks, axis=0)
    if points.size == 0:
        raise ValueError("No valid bootstrap points passed the confidence filter.")
    return points


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vertical-axis", choices=("x", "-x", "y", "-y", "z", "-z"), default="-y")
    parser.add_argument("--bootstrap-frames", type=int, default=8)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--sample-stride", type=int, default=8)
    parser.add_argument("--conf-threshold", type=float, default=1.5)
    parser.add_argument("--write-every", type=int, default=5)
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--voxel-size-m", type=float, default=0.04)
    parser.add_argument("--voxel-min-points", type=int, default=2)
    parser.add_argument("--floor-band-m", type=float, default=0.10)
    parser.add_argument("--floor-min-points-per-cell", type=int, default=2)
    parser.add_argument("--obstacle-min-height-m", type=float, default=0.18)
    parser.add_argument("--obstacle-max-height-m", type=float, default=2.0)
    parser.add_argument("--obstacle-min-points-per-cell", type=int, default=4)
    parser.add_argument("--min-obstacle-component-cells", type=int, default=4)
    parser.add_argument("--robot-radius-m", type=float, default=0.08)
    args = parser.parse_args()
    if args.bootstrap_frames < 1:
        parser.error("--bootstrap-frames must be at least 1")
    if args.sample_stride < 1 or args.write_every < 1:
        parser.error("--sample-stride and --write-every must be positive")
    if args.sleep_sec < 0:
        parser.error("--sleep-sec cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    archive_path = args.archive.resolve()
    output_dir = args.output_dir.resolve()
    data = np.load(archive_path, allow_pickle=True)
    world_points = data["world_points"]
    confidence = data["depth_conf"] if "depth_conf" in data.files else None
    frame_paths = data["frame_paths"] if "frame_paths" in data.files else np.arange(world_points.shape[0]).astype(str)
    frame_count = world_points.shape[0] if args.max_frames is None else min(args.max_frames, world_points.shape[0])

    bootstrap_points = collect_bootstrap_points(
        world_points,
        confidence,
        args.bootstrap_frames,
        args.sample_stride,
        args.conf_threshold,
    )
    floor_height = estimate_floor_height(bootstrap_points, args.vertical_axis)
    runtime_map = IncrementalVoxelMap(
        floor_height_m=floor_height,
        vertical_axis=args.vertical_axis,
        resolution_m=args.resolution_m,
        voxel_size_m=args.voxel_size_m,
        voxel_min_points=args.voxel_min_points,
        floor_band_m=args.floor_band_m,
        floor_min_points_per_cell=args.floor_min_points_per_cell,
        obstacle_min_height_m=args.obstacle_min_height_m,
        obstacle_max_height_m=args.obstacle_max_height_m,
        obstacle_min_points_per_cell=args.obstacle_min_points_per_cell,
        min_obstacle_component_cells=args.min_obstacle_component_cells,
        robot_radius_m=args.robot_radius_m,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    timeline = []
    started_at = time.perf_counter()
    for frame_index in range(frame_count):
        points, conf = frame_points(
            world_points,
            confidence,
            frame_index,
            args.sample_stride,
            args.conf_threshold,
        )
        update = runtime_map.update(points, conf)
        should_write = (frame_index + 1) % args.write_every == 0 or frame_index + 1 == frame_count
        metadata = None
        if should_write:
            snapshot_dir = output_dir / f"frame_{frame_index + 1:06d}"
            metadata = runtime_map.write(snapshot_dir)
            runtime_map.write(output_dir)
        entry = {
            "frame_index": frame_index,
            "frame_number": frame_index + 1,
            "source": str(frame_paths[frame_index]),
            "accepted_points": update["accepted_points"],
            "floor_points": update["floor_points"],
            "obstacle_points": update["obstacle_points"],
            "unknown_points": update["unknown_points"],
        }
        if metadata is not None:
            entry["map"] = {
                "width_px": metadata["width_px"],
                "height_px": metadata["height_px"],
                "free_cells": metadata["counts"]["free_cells"],
                "occupied_cells": metadata["counts"]["occupied_cells"],
                "largest_free_component_cells": metadata["counts"].get("largest_free_component_cells", 0),
                "snapshot_dir": str(snapshot_dir.relative_to(ROOT)),
            }
        timeline.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if args.sleep_sec:
            time.sleep(args.sleep_sec)

    summary = {
        "schema_version": 1,
        "mode": "online_replay_from_saved_predictions",
        "archive": str(archive_path),
        "output_dir": str(output_dir),
        "frames_integrated": frame_count,
        "bootstrap_frames": args.bootstrap_frames,
        "sample_stride": args.sample_stride,
        "conf_threshold": args.conf_threshold,
        "floor_height_m": floor_height,
        "elapsed_sec": round(time.perf_counter() - started_at, 3),
        "latest_map": str(output_dir / "map.pgm"),
        "latest_snapshot": str(output_dir / "snapshot.ply"),
        "timeline": timeline,
    }
    (output_dir / "online_replay_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_dir / 'online_replay_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
