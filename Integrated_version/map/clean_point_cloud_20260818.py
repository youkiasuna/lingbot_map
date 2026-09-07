#!/usr/bin/env python3
"""Clean and compact the 20260818 LingBot-MAP point cloud.

This first-stage pass deliberately does not classify walls or obstacles yet.
It removes low-confidence samples, uses a deterministic input stride to keep
memory bounded, merges points inside voxels, and drops isolated voxels.
The signed vertical convention for the 20260818 scan is recorded as -Y.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
import re

ROW = struct.Struct("<fffBBBf")


@dataclass
class Voxel:
    count: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0
    confidence: float = 0.0

    def add(self, x: float, y: float, z: float, red: int, green: int, blue: int, confidence: float) -> None:
        self.count += 1
        self.x += x
        self.y += y
        self.z += z
        self.red += red
        self.green += green
        self.blue += blue
        self.confidence += confidence


def read_header(handle) -> int:
    if handle.readline().strip() != b"ply":
        raise ValueError("The input is not a PLY file.")
    vertex_count = 0
    while True:
        line = handle.readline().decode("ascii", errors="strict").strip()
        if not line:
            raise ValueError("PLY header ended unexpectedly.")
        parts = line.split()
        if parts[:2] == ["format", "binary_little_endian"]:
            continue
        if parts[:2] == ["element", "vertex"]:
            vertex_count = int(parts[2])
        if parts[0] == "end_header":
            break
    if ROW.size != 19:
        raise AssertionError("Unexpected PLY row size.")
    return vertex_count


def read_voxels(
    path: Path,
    confidence_threshold: float,
    voxel_size_m: float,
    max_input_points: int,
) -> tuple[dict[tuple[int, int, int], Voxel], dict[str, int | float]]:
    voxels: dict[tuple[int, int, int], Voxel] = {}
    stats = {"source_points": 0, "sampled_points": 0, "confidence_points": 0}
    with path.open("rb") as handle:
        source_count = read_header(handle)
        stride = max(1, math.ceil(source_count / max_input_points))
        stats["source_points"] = source_count
        stats["input_stride"] = stride
        for index in range(source_count):
            raw = handle.read(ROW.size)
            if len(raw) != ROW.size:
                raise ValueError("PLY vertex data ended unexpectedly.")
            if index % stride != 0:
                continue
            stats["sampled_points"] += 1
            x, y, z, red, green, blue, confidence = ROW.unpack(raw)
            if not math.isfinite(confidence) or confidence < confidence_threshold:
                continue
            stats["confidence_points"] += 1
            key = (math.floor(x / voxel_size_m), math.floor(y / voxel_size_m), math.floor(z / voxel_size_m))
            voxel = voxels.setdefault(key, Voxel())
            voxel.add(x, y, z, red, green, blue, confidence)
    return voxels, stats


def write_ply(path: Path, voxels: dict[tuple[int, int, int], Voxel], min_points: int) -> tuple[int, int]:
    selected = [voxel for voxel in voxels.values() if voxel.count >= min_points]
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment cleaned by clean_point_cloud_20260818.py\n"
        f"element vertex {len(selected)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property float confidence\nend_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        for voxel in selected:
            count = float(voxel.count)
            handle.write(ROW.pack(
                voxel.x / count,
                voxel.y / count,
                voxel.z / count,
                round(voxel.red / count),
                round(voxel.green / count),
                round(voxel.blue / count),
                voxel.confidence / count,
            ))
    removed_voxels = len(voxels) - len(selected)
    return len(selected), removed_voxels


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean the 20260818 dense PLY without classifying surfaces yet.")
    parser.add_argument("--ply", type=Path, default=Path("map_localization_test/outputs/20260818_dense.ply"))
    parser.add_argument("--output-dir", type=Path, default=Path("map_localization_test/outputs/20260818_clean"))
    parser.add_argument("--confidence-threshold", type=float, default=1.0)
    parser.add_argument("--voxel-size-m", type=float, default=0.03)
    parser.add_argument("--min-points-per-voxel", type=int, default=2)
    parser.add_argument("--max-input-points", type=int, default=5_000_000)
    args = parser.parse_args()
    if not args.ply.exists():
        raise SystemExit(f"PLY file not found: {args.ply}")
    if args.voxel_size_m <= 0 or args.max_input_points < 1 or args.min_points_per_voxel < 1:
        raise SystemExit("voxel size and point limits must be positive")

    print(f"Reading {args.ply} with confidence >= {args.confidence_threshold}...")
    voxels, stats = read_voxels(args.ply, args.confidence_threshold, args.voxel_size_m, args.max_input_points)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    date_match = re.search(r"20\d{6}", args.ply.stem)
    output_name = f"{date_match.group(0)}_clean.ply" if date_match else "cleaned.ply"
    output_ply = args.output_dir / output_name
    output_count, removed_voxels = write_ply(output_ply, voxels, args.min_points_per_voxel)
    stats.update({
        "voxel_size_m": args.voxel_size_m,
        "min_points_per_voxel": args.min_points_per_voxel,
        "confidence_threshold": args.confidence_threshold,
        "voxel_count": len(voxels),
        "output_points": output_count,
        "removed_isolated_voxels": removed_voxels,
        "vertical_axis": "-Y",
        "stage": "quality_cleaning_only",
    })
    (args.output_dir / "cleaning_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"Sampled {stats['sampled_points']:,} / {stats['source_points']:,} source points (stride {stats['input_stride']}).")
    print(f"Kept {stats['confidence_points']:,} points before voxel merge.")
    print(f"Wrote {output_count:,} cleaned voxels to {output_ply}")
    print(f"Wrote {args.output_dir / 'cleaning_stats.json'}")


if __name__ == "__main__":
    main()