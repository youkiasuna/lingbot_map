#!/usr/bin/env python3
"""Build a navigation grid from a TSDF triangle mesh.

This is the mesh-based replacement for the earlier point-cloud projection
navigation map. It detects walkable floor from triangle normals, rasterizes
floor triangles into free cells, marks raised geometry as obstacle evidence,
and writes the same ``map.pgm`` / ``map.json`` format used by the existing A*
planner.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import trimesh


FREE = 254
UNKNOWN = 205
OCCUPIED = 0


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def axis_info(vertical_axis: str) -> tuple[int, float, np.ndarray, list[int]]:
    axis_index = "xyz".index(vertical_axis[-1])
    sign = -1.0 if vertical_axis.startswith("-") else 1.0
    up = np.zeros(3, dtype=np.float64)
    up[axis_index] = sign
    horizontal = [index for index in range(3) if index != axis_index]
    return axis_index, sign, up, horizontal


def point_in_triangle(point, a, b, c) -> bool:
    v0 = c - a
    v1 = b - a
    v2 = point - a
    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-12:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= -1e-6 and v >= -1e-6 and u + v <= 1.0 + 1e-6


def dilate(mask: np.ndarray, width: int, height: int, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    result = mask.copy()
    offsets = [
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    ]
    ys, xs = np.nonzero(mask.reshape(height, width))
    for x, y in zip(xs, ys):
        for dx, dy in offsets:
            nx, ny = int(x + dx), int(y + dy)
            if 0 <= nx < width and 0 <= ny < height:
                result[ny * width + nx] = True
    return result


def rasterize_triangle(mask: np.ndarray, width: int, height: int, tri_uv: np.ndarray, min_u: float, max_v: float, resolution: float) -> None:
    px = np.floor((tri_uv[:, 0] - min_u) / resolution).astype(int)
    py = np.floor((max_v - tri_uv[:, 1]) / resolution).astype(int)
    x0, x1 = max(0, int(px.min()) - 1), min(width - 1, int(px.max()) + 1)
    y0, y1 = max(0, int(py.min()) - 1), min(height - 1, int(py.max()) + 1)
    if x0 > x1 or y0 > y1:
        return
    a, b, c = tri_uv
    for y in range(y0, y1 + 1):
        v = max_v - (y + 0.5) * resolution
        row = y * width
        for x in range(x0, x1 + 1):
            u = min_u + (x + 0.5) * resolution
            if point_in_triangle(np.asarray([u, v]), a, b, c):
                mask[row + x] = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--vertical-axis", choices=("x", "-x", "y", "-y", "z", "-z"), default="-y")
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--max-slope-deg", type=float, default=18.0)
    parser.add_argument("--floor-band-m", type=float, default=0.12)
    parser.add_argument("--obstacle-min-height-m", type=float, default=0.15)
    parser.add_argument("--obstacle-max-height-m", type=float, default=1.6)
    parser.add_argument("--robot-radius-m", type=float, default=0.12)
    args = parser.parse_args()
    if args.resolution_m <= 0 or args.robot_radius_m < 0:
        parser.error("resolution must be positive and robot radius cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    mesh = trimesh.load_mesh(args.mesh, process=False)
    if mesh.vertices.size == 0 or mesh.faces.size == 0:
        raise SystemExit("Input mesh has no vertices or faces.")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    axis_index, sign, up, horizontal = axis_info(args.vertical_axis)
    heights = sign * vertices[:, axis_index]
    uv = vertices[:, horizontal]
    min_u = math.floor(float(uv[:, 0].min()) / args.resolution_m) * args.resolution_m
    max_u = math.ceil(float(uv[:, 0].max()) / args.resolution_m) * args.resolution_m
    min_v = math.floor(float(uv[:, 1].min()) / args.resolution_m) * args.resolution_m
    max_v = math.ceil(float(uv[:, 1].max()) / args.resolution_m) * args.resolution_m
    width = max(1, math.ceil((max_u - min_u) / args.resolution_m) + 1)
    height = max(1, math.ceil((max_v - min_v) / args.resolution_m) + 1)

    face_heights = heights[faces].mean(axis=1)
    normal_alignment = np.abs(normals @ up)
    walkable_alignment = math.cos(math.radians(args.max_slope_deg))
    horizontal_faces = normal_alignment >= walkable_alignment
    if not np.any(horizontal_faces):
        raise SystemExit("No nearly-horizontal mesh faces found; cannot build navigation grid.")
    floor_height = float(np.percentile(face_heights[horizontal_faces], 10))
    floor_faces = horizontal_faces & (np.abs(face_heights - floor_height) <= args.floor_band_m)
    obstacle_faces = (
        (face_heights >= floor_height + args.obstacle_min_height_m)
        & (face_heights <= floor_height + args.obstacle_max_height_m)
    )

    free = np.zeros(width * height, dtype=bool)
    occupied = np.zeros(width * height, dtype=bool)
    for face in faces[floor_faces]:
        rasterize_triangle(free, width, height, uv[face], min_u, max_v, args.resolution_m)
    for face in faces[obstacle_faces]:
        tri = uv[face]
        samples = np.vstack([tri, tri.mean(axis=0, keepdims=True)])
        for point in samples:
            px = int(math.floor((float(point[0]) - min_u) / args.resolution_m))
            py = int(math.floor((max_v - float(point[1])) / args.resolution_m))
            if 0 <= px < width and 0 <= py < height:
                occupied[py * width + px] = True

    inflation_pixels = math.ceil(args.robot_radius_m / args.resolution_m)
    inflated = dilate(occupied, width, height, inflation_pixels)
    pixels = np.full(width * height, UNKNOWN, dtype=np.uint8)
    pixels[free] = FREE
    pixels[inflated] = OCCUPIED

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_pgm(args.output_dir / "map.pgm", width, height, pixels.tobytes())
    write_pgm(args.output_dir / "navigation_map.pgm", width, height, pixels.tobytes())
    metadata = {
        "format_version": 2,
        "source": "tsdf_mesh",
        "source_mesh": str(args.mesh.resolve()),
        "vertical_axis": args.vertical_axis,
        "horizontal_axes": "".join(axis.upper() for axis in "xyz" if axis != args.vertical_axis[-1]),
        "floor_height_m": floor_height,
        "max_slope_deg": args.max_slope_deg,
        "floor_band_m": args.floor_band_m,
        "obstacle_min_height_m": args.obstacle_min_height_m,
        "obstacle_max_height_m": args.obstacle_max_height_m,
        "resolution_m": args.resolution_m,
        "meters_per_pixel": args.resolution_m,
        "origin_u_m": min_u,
        "origin_v_m": max_v,
        "width_px": width,
        "height_px": height,
        "robot_radius_m": args.robot_radius_m,
        "inflation_pixels": inflation_pixels,
        "counts": {
            "vertices": int(len(vertices)),
            "faces": int(len(faces)),
            "floor_faces": int(floor_faces.sum()),
            "obstacle_faces": int(obstacle_faces.sum()),
            "free_cells": int(free.sum()),
            "occupied_cells": int(inflated.sum()),
        },
        "pgm_values": "0=occupied inflated, 205=unknown, 254=walkable mesh floor",
    }
    (args.output_dir / "map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "navigation_map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Built mesh navigation map: {width}x{height}")
    print(json.dumps(metadata["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
