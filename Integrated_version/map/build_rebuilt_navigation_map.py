#!/usr/bin/env python3
"""Build a less-fragmented 2D navigation map from rebuilt_colored_map.ply.

This is a lightweight OctoMap-inspired pipeline for the current demo data.  It
does not require ROS: points are voxel-filtered, classified by height relative
to an estimated floor level, projected into a 2D grid, and cleaned with simple
connected-component filters before robot-radius inflation.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import struct
from collections import deque
from pathlib import Path

import numpy as np

FREE = 254
UNKNOWN = 205
OCCUPIED = 0


PLY_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
        ("confidence", "<f4"),
    ]
)


def read_rebuilt_ply(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError("The input is not a PLY file.")
        vertex_count = 0
        while True:
            line = handle.readline().decode("ascii", errors="strict").strip()
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[2])
            if line == "end_header":
                break
        points = np.fromfile(handle, dtype=PLY_DTYPE, count=vertex_count)
    if len(points) != vertex_count:
        raise ValueError("PLY vertex data ended unexpectedly.")
    return points


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_classified_ply(path: Path, xyzrgbc: np.ndarray) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment classified by build_rebuilt_navigation_map.py\n"
        f"element vertex {len(xyzrgbc)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property float confidence\nend_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        xyzrgbc.tofile(handle)


def axis_indices(vertical_axis: str) -> tuple[int, float, list[int]]:
    axis = vertical_axis[-1]
    axis_index = "xyz".index(axis)
    sign = -1.0 if vertical_axis.startswith("-") else 1.0
    horizontal = [index for index in range(3) if index != axis_index]
    return axis_index, sign, horizontal


def estimate_floor_height(heights: np.ndarray, low_percentile: float, high_percentile: float, bin_size: float) -> float:
    low, high = np.percentile(heights, [low_percentile, high_percentile])
    sample = heights[(heights >= low) & (heights <= high)]
    if sample.size == 0:
        return float(np.percentile(heights, 10.0))
    bins = max(8, int(math.ceil((float(sample.max()) - float(sample.min())) / bin_size)))
    counts, edges = np.histogram(sample, bins=bins)
    peak = int(np.argmax(counts))
    return float((edges[peak] + edges[peak + 1]) * 0.5)


def voxel_keep_mask(coords: np.ndarray, voxel_size: float, min_points: int) -> np.ndarray:
    if min_points <= 1:
        return np.ones(coords.shape[0], dtype=bool)
    q = np.floor(coords / voxel_size).astype(np.int32)
    _, inverse, counts = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    return counts[inverse] >= min_points


def remove_small_components(mask: np.ndarray, min_cells: int) -> tuple[np.ndarray, int, int]:
    if min_cells <= 1:
        return mask, int(mask.sum()), int(mask.sum())
    height, width = mask.shape
    result = mask.copy()
    visited = np.zeros_like(mask, dtype=bool)
    component_count = 0
    removed_cells = 0
    for sy in range(height):
        for sx in range(width):
            if visited[sy, sx] or not mask[sy, sx]:
                continue
            component_count += 1
            queue: deque[tuple[int, int]] = deque([(sx, sy)])
            visited[sy, sx] = True
            cells: list[tuple[int, int]] = []
            while queue:
                x, y = queue.popleft()
                cells.append((x, y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] and mask[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
            if len(cells) < min_cells:
                removed_cells += len(cells)
                for x, y in cells:
                    result[y, x] = False
    return result, component_count, removed_cells


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    height, width = mask.shape
    result = mask.copy()
    offsets = [
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    ]
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                result[ny, nx] = True
    return result


def component_stats(free: np.ndarray) -> dict[str, int]:
    height, width = free.shape
    visited = np.zeros_like(free, dtype=bool)
    sizes: list[int] = []
    for sy in range(height):
        for sx in range(width):
            if visited[sy, sx] or not free[sy, sx]:
                continue
            queue: deque[tuple[int, int]] = deque([(sx, sy)])
            visited[sy, sx] = True
            size = 0
            while queue:
                x, y = queue.popleft()
                size += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] and free[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            sizes.append(size)
    return {
        "free_components": len(sizes),
        "largest_free_component_cells": max(sizes) if sizes else 0,
    }


def build_distance_field(width: int, height: int, pixels: bytes, resolution: float) -> list[float]:
    distances = [math.inf] * (width * height)
    queue: list[tuple[float, int]] = []
    for index, value in enumerate(pixels):
        if value <= 100:
            distances[index] = 0.0
            heapq.heappush(queue, (0.0, index))
    while queue:
        distance, index = heapq.heappop(queue)
        if distance != distances[index]:
            continue
        x = index % width
        y = index // width
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                next_index = ny * width + nx
                next_distance = distance + math.hypot(dx, dy) * resolution
                if next_distance < distances[next_index]:
                    distances[next_index] = next_distance
                    heapq.heappush(queue, (next_distance, next_index))
    return distances


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a cleaned rebuilt 3D-to-2D navigation map.")
    parser.add_argument("--ply", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--vertical-axis", choices=("x", "-x", "y", "-y", "z", "-z"), default="-y")
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--voxel-size-m", type=float, default=0.04)
    parser.add_argument("--voxel-min-points", type=int, default=2)
    parser.add_argument("--floor-band-m", type=float, default=0.10)
    parser.add_argument("--floor-low-percentile", type=float, default=1.0)
    parser.add_argument("--floor-high-percentile", type=float, default=35.0)
    parser.add_argument("--floor-hist-bin-m", type=float, default=0.015)
    parser.add_argument("--floor-min-points-per-cell", type=int, default=2)
    parser.add_argument("--obstacle-min-height-m", type=float, default=0.18)
    parser.add_argument("--obstacle-max-height-m", type=float, default=2.0)
    parser.add_argument("--obstacle-min-points-per-cell", type=int, default=4)
    parser.add_argument("--min-obstacle-component-cells", type=int, default=4)
    parser.add_argument("--robot-radius-m", type=float, default=0.08)
    args = parser.parse_args()

    if args.resolution_m <= 0 or args.voxel_size_m <= 0 or args.robot_radius_m < 0:
        raise SystemExit("resolution, voxel size, and robot radius parameters are invalid.")

    points = read_rebuilt_ply(args.ply)
    xyz = np.column_stack([points["x"], points["y"], points["z"]]).astype(np.float32)
    axis_index, sign, horizontal = axis_indices(args.vertical_axis)
    heights = sign * xyz[:, axis_index]
    floor_height = estimate_floor_height(
        heights,
        args.floor_low_percentile,
        args.floor_high_percentile,
        args.floor_hist_bin_m,
    )

    keep = voxel_keep_mask(xyz, args.voxel_size_m, args.voxel_min_points)
    filtered = points[keep]
    filtered_xyz = xyz[keep]
    filtered_heights = heights[keep]

    us = filtered_xyz[:, horizontal[0]]
    vs = filtered_xyz[:, horizontal[1]]
    min_u = math.floor(float(us.min()) / args.resolution_m) * args.resolution_m
    max_u = math.ceil(float(us.max()) / args.resolution_m) * args.resolution_m
    min_v = math.floor(float(vs.min()) / args.resolution_m) * args.resolution_m
    max_v = math.ceil(float(vs.max()) / args.resolution_m) * args.resolution_m
    width = max(1, math.ceil((max_u - min_u) / args.resolution_m) + 1)
    height = max(1, math.ceil((max_v - min_v) / args.resolution_m) + 1)

    px = np.floor((us - min_u) / args.resolution_m).astype(np.int32)
    py = np.floor((max_v - vs) / args.resolution_m).astype(np.int32)
    valid = (px >= 0) & (px < width) & (py >= 0) & (py < height)
    px = px[valid]
    py = py[valid]
    cell_indices = py * width + px
    relative_heights = filtered_heights[valid] - floor_height

    floor_point_mask = np.abs(relative_heights) <= args.floor_band_m
    obstacle_point_mask = (
        (relative_heights >= args.obstacle_min_height_m)
        & (relative_heights <= args.obstacle_max_height_m)
    )
    floor_counts = np.bincount(cell_indices[floor_point_mask], minlength=width * height)
    obstacle_counts = np.bincount(cell_indices[obstacle_point_mask], minlength=width * height)

    free = (floor_counts.reshape(height, width) >= args.floor_min_points_per_cell)
    occupied_raw = obstacle_counts.reshape(height, width) >= args.obstacle_min_points_per_cell
    occupied_clean, obstacle_components, removed_obstacle_cells = remove_small_components(
        occupied_raw,
        args.min_obstacle_component_cells,
    )
    inflation_pixels = math.ceil(args.robot_radius_m / args.resolution_m)
    occupied = dilate(occupied_clean, inflation_pixels)

    pixels = np.full((height, width), UNKNOWN, dtype=np.uint8)
    pixels[free] = FREE
    pixels[occupied] = OCCUPIED
    free_after_inflation = pixels == FREE
    stats = component_stats(free_after_inflation)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_pgm(args.output_dir / "map.pgm", width, height, pixels.tobytes())
    write_pgm(args.output_dir / "navigation_map.pgm", width, height, pixels.tobytes())

    filtered_valid = filtered[valid]
    floor_out = filtered_valid[floor_point_mask]
    obstacle_out = filtered_valid[obstacle_point_mask]
    unknown_mask = ~(floor_point_mask | obstacle_point_mask)
    unknown_out = filtered_valid[unknown_mask]
    write_classified_ply(args.output_dir / "floor.ply", floor_out)
    write_classified_ply(args.output_dir / "obstacle.ply", obstacle_out)
    write_classified_ply(args.output_dir / "unknown.ply", unknown_out)

    metadata = {
        "format_version": 2,
        "source_ply": str(args.ply),
        "method": "rebuilt_voxel_height_component_filter",
        "vertical_axis": args.vertical_axis,
        "horizontal_axes": "".join(axis.upper() for axis in "xyz" if axis != args.vertical_axis[-1]),
        "floor_height_m": floor_height,
        "resolution_m": args.resolution_m,
        "meters_per_pixel": args.resolution_m,
        "origin_u_m": min_u,
        "origin_v_m": max_v,
        "width_px": width,
        "height_px": height,
        "voxel_size_m": args.voxel_size_m,
        "voxel_min_points": args.voxel_min_points,
        "floor_band_m": args.floor_band_m,
        "floor_min_points_per_cell": args.floor_min_points_per_cell,
        "obstacle_min_height_m": args.obstacle_min_height_m,
        "obstacle_max_height_m": args.obstacle_max_height_m,
        "obstacle_min_points_per_cell": args.obstacle_min_points_per_cell,
        "min_obstacle_component_cells": args.min_obstacle_component_cells,
        "robot_radius_m": args.robot_radius_m,
        "inflation_pixels": inflation_pixels,
        "counts": {
            "input": int(len(points)),
            "after_voxel_filter": int(len(filtered)),
            "floor_points": int(floor_point_mask.sum()),
            "obstacle_points": int(obstacle_point_mask.sum()),
            "unknown_points": int(unknown_mask.sum()),
            "free_cells_before_inflation": int(free.sum()),
            "occupied_cells_raw": int(occupied_raw.sum()),
            "occupied_cells_after_component_filter": int(occupied_clean.sum()),
            "occupied_cells_after_inflation": int(occupied.sum()),
            "removed_small_obstacle_cells": int(removed_obstacle_cells),
            "obstacle_components_raw": int(obstacle_components),
            "free_cells_after_inflation": int(free_after_inflation.sum()),
            **stats,
        },
        "pgm_values": "0=occupied inflated, 205=unknown, 254=free floor",
    }
    (args.output_dir / "map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "navigation_map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    distances = build_distance_field(width, height, pixels.tobytes(), args.resolution_m)
    (args.output_dir / "obstacle_distance.bin").write_bytes(struct.pack(f"<{len(distances)}f", *distances))
    (args.output_dir / "obstacle_distance.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "image": "obstacle_distance.bin",
                "width_px": width,
                "height_px": height,
                "meters_per_pixel": args.resolution_m,
                "value": "float32 metres to nearest occupied cell; inf means no occupied cell in map",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Built {width}x{height} rebuilt navigation map from {len(points):,} points.")
    print(json.dumps(metadata["counts"], indent=2))
    print(f"Estimated floor height: {floor_height:.4f} m")
    print(f"Wrote {args.output_dir}")


if __name__ == "__main__":
    main()
