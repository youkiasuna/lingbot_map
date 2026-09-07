#!/usr/bin/env python3
"""Build a geometry-based 3D navigation map from a calibrated point cloud.

The input must already be floor-leveled. The signed vertical axis is preserved
per scan (20260818: -Y, 20260804: -Z). This stage does not claim semantic
knowledge of walls versus furniture: both become obstacle evidence for motion.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from pathlib import Path

ROW = struct.Struct("<fffBBBf")
FREE = 254
UNKNOWN = 205
OCCUPIED = 0


def read_ply(path: Path) -> list[tuple[float, float, float, int, int, int, float]]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError("The input is not a PLY file.")
        count = 0
        while True:
            line = handle.readline().decode("ascii", errors="strict").strip()
            if line.startswith("element vertex "):
                count = int(line.split()[2])
            if line == "end_header":
                break
        points = []
        for _ in range(count):
            raw = handle.read(ROW.size)
            if len(raw) != ROW.size:
                raise ValueError("PLY vertex data ended unexpectedly.")
            points.append(ROW.unpack(raw))
    return points


def write_ply(path: Path, points: list[tuple[float, float, float, int, int, int, float]]) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment classified by build_3d_navigation_map.py\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property float confidence\nend_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        for point in points:
            handle.write(ROW.pack(*point))


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def dilate(mask: list[bool], width: int, height: int, radius: int) -> list[bool]:
    result = mask[:]
    offsets = [(dx, dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1) if dx * dx + dy * dy <= radius * radius]
    for index, value in enumerate(mask):
        if not value:
            continue
        x, y = index % width, index // width
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                result[ny * width + nx] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build floor/obstacle/unknown navigation maps from calibrated 3D points.")
    parser.add_argument("--ply", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--vertical-axis", choices=("x", "-x", "y", "-y", "z", "-z"), required=True)
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--floor-band-m", type=float, default=0.08)
    parser.add_argument("--obstacle-min-height-m", type=float, default=0.10)
    parser.add_argument("--obstacle-max-height-m", type=float, default=2.0)
    parser.add_argument("--min-points-per-cell", type=int, default=1)
    parser.add_argument("--robot-radius-m", type=float, default=0.20)
    args = parser.parse_args()
    if args.resolution_m <= 0 or args.robot_radius_m < 0:
        raise SystemExit("resolution must be positive and robot radius cannot be negative")

    points = read_ply(args.ply)
    axis_index = "xyz".index(args.vertical_axis[-1])
    sign = -1.0 if args.vertical_axis.startswith("-") else 1.0
    horizontal_indices = [index for index in range(3) if index != axis_index]
    heights = [sign * point[axis_index] for point in points]
    floor_height = 0.0

    us = [point[horizontal_indices[0]] for point in points]
    vs = [point[horizontal_indices[1]] for point in points]
    min_u = math.floor(min(us) / args.resolution_m) * args.resolution_m
    max_u = math.ceil(max(us) / args.resolution_m) * args.resolution_m
    min_v = math.floor(min(vs) / args.resolution_m) * args.resolution_m
    max_v = math.ceil(max(vs) / args.resolution_m) * args.resolution_m
    width = max(1, math.ceil((max_u - min_u) / args.resolution_m) + 1)
    height = max(1, math.ceil((max_v - min_v) / args.resolution_m) + 1)
    floor_counts = [0] * (width * height)
    obstacle_counts = [0] * (width * height)
    floor_points = []
    obstacle_points = []
    unknown_points = []

    for point, raw_height in zip(points, heights):
        u, v = point[horizontal_indices[0]], point[horizontal_indices[1]]
        px = int((u - min_u) / args.resolution_m)
        py = int((max_v - v) / args.resolution_m)
        if not (0 <= px < width and 0 <= py < height):
            continue
        index = py * width + px
        if abs(raw_height - floor_height) <= args.floor_band_m:
            floor_counts[index] += 1
            floor_points.append(point)
        elif args.obstacle_min_height_m <= raw_height <= args.obstacle_max_height_m:
            obstacle_counts[index] += 1
            obstacle_points.append(point)
        else:
            unknown_points.append(point)

    free = [count >= args.min_points_per_cell for count in floor_counts]
    occupied = [count >= args.min_points_per_cell for count in obstacle_counts]
    inflation_pixels = math.ceil(args.robot_radius_m / args.resolution_m)
    inflated = dilate(occupied, width, height, inflation_pixels)
    pixels = bytearray([UNKNOWN] * (width * height))
    for index, value in enumerate(free):
        if value:
            pixels[index] = FREE
    for index, value in enumerate(inflated):
        if value:
            pixels[index] = OCCUPIED

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_ply(args.output_dir / "floor.ply", floor_points)
    write_ply(args.output_dir / "obstacle.ply", obstacle_points)
    write_ply(args.output_dir / "unknown.ply", unknown_points)
    write_pgm(args.output_dir / "navigation_map.pgm", width, height, pixels)
    write_pgm(args.output_dir / "map.pgm", width, height, pixels)
    metadata = {
        "format_version": 1,
        "source_ply": str(args.ply),
        "vertical_axis": args.vertical_axis,
        "horizontal_axes": "".join(axis.upper() for axis in "xyz" if axis != args.vertical_axis[-1]),
        "floor_height_m": floor_height,
        "resolution_m": args.resolution_m,
        "meters_per_pixel": args.resolution_m,
        "origin_u_m": min_u,
        "origin_v_m": max_v,
        "width_px": width,
        "height_px": height,
        "floor_band_m": args.floor_band_m,
        "obstacle_min_height_m": args.obstacle_min_height_m,
        "obstacle_max_height_m": args.obstacle_max_height_m,
        "robot_radius_m": args.robot_radius_m,
        "inflation_pixels": inflation_pixels,
        "counts": {"input": len(points), "floor": len(floor_points), "obstacle": len(obstacle_points), "unknown": len(unknown_points), "free_cells": sum(free), "occupied_cells": sum(inflated)},
        "pgm_values": "0=occupied inflated, 205=unknown, 254=free floor",
    }
    (args.output_dir / "navigation_map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built {width}x{height} navigation map from {len(points):,} points.")
    print(json.dumps(metadata["counts"], indent=2))
    print(f"Wrote {args.output_dir}")


if __name__ == "__main__":
    main()
