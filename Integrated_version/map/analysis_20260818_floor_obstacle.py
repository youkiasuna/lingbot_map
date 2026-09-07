#!/usr/bin/env python3
"""20260818-specific 3D-to-2D floor/obstacle analysis.

This script reads the 20260818 dense PLY, estimates the dominant floor height,
projects the point cloud to a 2D occupancy map, and labels cells as:

- 254: floor / traversable
- 0: obstacle / non-traversable
- 205: unknown

The output is intended for quick inspection before connecting the map to the web
UI and path planner.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import BinaryIO, Iterator

PLY_TYPES = {
    "char": "b",
    "int8": "b",
    "uchar": "B",
    "uint8": "B",
    "short": "h",
    "int16": "h",
    "ushort": "H",
    "uint16": "H",
    "int": "i",
    "int32": "i",
    "uint": "I",
    "uint32": "I",
    "float": "f",
    "float32": "f",
    "double": "d",
    "float64": "d",
}

FREE_VALUE = 254
OCCUPIED_VALUE = 0
UNKNOWN_VALUE = 205


def read_header(handle: BinaryIO) -> tuple[str, int, list[tuple[str, str]]]:
    first_line = handle.readline().decode("ascii", errors="strict").strip()
    if first_line != "ply":
        raise ValueError("The input is not a PLY file.")

    file_format = ""
    vertex_count = 0
    vertex_properties: list[tuple[str, str]] = []
    in_vertex_element = False

    while True:
        line = handle.readline().decode("ascii", errors="strict").strip()
        if not line:
            raise ValueError("PLY header ended unexpectedly.")
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format" and len(parts) >= 2:
            file_format = parts[1]
        elif parts[0] == "element" and len(parts) == 3:
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertex_element:
            if len(parts) != 3 or parts[1] == "list":
                raise ValueError("Only scalar vertex properties are supported.")
            if parts[1] not in PLY_TYPES:
                raise ValueError(f"Unsupported PLY property type: {parts[1]}")
            vertex_properties.append((parts[1], parts[2]))
        elif parts[0] == "end_header":
            break

    names = {name for _, name in vertex_properties}
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError("PLY vertices must contain x, y, and z properties.")
    if file_format not in {"ascii", "binary_little_endian"}:
        raise ValueError("Only ASCII and binary_little_endian PLY files are supported.")
    return file_format, vertex_count, vertex_properties


def iter_vertices(ply_path: Path, max_points: int | None = None) -> Iterator[tuple[float, float, float]]:
    with ply_path.open("rb") as handle:
        file_format, vertex_count, properties = read_header(handle)
        point_limit = min(vertex_count, max_points) if max_points else vertex_count
        name_to_index = {name: index for index, (_, name) in enumerate(properties)}

        if file_format == "ascii":
            for _ in range(point_limit):
                parts = handle.readline().decode("ascii", errors="strict").split()
                if len(parts) < len(properties):
                    raise ValueError("Unexpected end of ASCII vertex data.")
                yield (
                    float(parts[name_to_index["x"]]),
                    float(parts[name_to_index["y"]]),
                    float(parts[name_to_index["z"]]),
                )
        else:
            fmt = "<" + "".join(PLY_TYPES[data_type] for data_type, _ in properties)
            row_size = struct.calcsize(fmt)
            unpack = struct.Struct(fmt).unpack
            for _ in range(point_limit):
                raw = handle.read(row_size)
                if len(raw) != row_size:
                    raise ValueError("Unexpected end of binary vertex data.")
                values = unpack(raw)
                yield (
                    float(values[name_to_index["x"]]),
                    float(values[name_to_index["y"]]),
                    float(values[name_to_index["z"]]),
                )


def select_plane_values(point: tuple[float, float, float], up_axis: str) -> tuple[float, float, float]:
    x, y, z = point
    if up_axis == "z":
        return x, y, z
    if up_axis == "y":
        return x, z, y
    return y, z, x


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot compute percentile of an empty sample.")
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return values[idx]


def make_grid_metadata(
    min_u: float,
    max_u: float,
    min_v: float,
    max_v: float,
    up_axis: str,
    meters_per_pixel: float,
) -> dict[str, float | int | str]:
    width = max(1, math.ceil((max_u - min_u) / meters_per_pixel) + 1)
    height = max(1, math.ceil((max_v - min_v) / meters_per_pixel) + 1)
    if width * height > 64_000_000:
        raise ValueError(f"Map would be {width}x{height} pixels. Increase --meters-per-pixel.")
    return {
        "format_version": 3,
        "image": "map_20260818_floor_obstacle.pgm",
        "up_axis": up_axis,
        "meters_per_pixel": meters_per_pixel,
        "origin_u_m": min_u,
        "origin_v_m": max_v,
        "width_px": width,
        "height_px": height,
        "world_to_pixel": "px=(u-origin_u)/meters_per_pixel; py=(origin_v-v)/meters_per_pixel",
    }


def point_to_index(u: float, v: float, metadata: dict[str, float | int | str]) -> int | None:
    width = int(metadata["width_px"])
    height = int(metadata["height_px"])
    origin_u = float(metadata["origin_u_m"])
    origin_v = float(metadata["origin_v_m"])
    resolution = float(metadata["meters_per_pixel"])
    pixel_x = int((u - origin_u) / resolution)
    pixel_y = int((origin_v - v) / resolution)
    if pixel_x < 0 or pixel_x >= width or pixel_y < 0 or pixel_y >= height:
        return None
    return pixel_y * width + pixel_x


def dilate_occupied(occupied: list[bool], width: int, height: int, radius: int) -> list[bool]:
    if radius <= 0:
        return occupied
    result = occupied[:]
    offsets = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                offsets.append((dx, dy))
    for index, value in enumerate(occupied):
        if not value:
            continue
        x = index % width
        y = index // width
        for dx, dy in offsets:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height:
                result[ny * width + nx] = True
    return result


def build_floor_obstacle_map(
    ply_path: Path,
    up_axis: str,
    meters_per_pixel: float,
    padding_m: float,
    floor_thickness: float,
    obstacle_min_height: float,
    obstacle_max_height: float,
    floor_min_points_per_pixel: int,
    obstacle_min_points_per_pixel: int,
    occupied_dilate_pixels: int,
    max_points: int | None,
) -> tuple[bytes, dict[str, float | int | str], float, int]:
    points = list(iter_vertices(ply_path, max_points))
    if not points:
        raise ValueError("No vertices were read from the PLY file.")

    h_values = [select_plane_values(point, up_axis)[2] for point in points]
    floor_level = percentile(h_values, 0.05)

    plane_points = [select_plane_values(point, up_axis)[:2] for point in points]
    min_u = min(p[0] for p in plane_points) - padding_m
    max_u = max(p[0] for p in plane_points) + padding_m
    min_v = min(p[1] for p in plane_points) - padding_m
    max_v = max(p[1] for p in plane_points) + padding_m

    metadata = make_grid_metadata(min_u, max_u, min_v, max_v, up_axis, meters_per_pixel)
    width = int(metadata["width_px"])
    height = int(metadata["height_px"])

    floor_counts = [0] * (width * height)
    obstacle_counts = [0] * (width * height)
    processed = 0

    for point in points:
        u, v, h = select_plane_values(point, up_axis)
        index = point_to_index(u, v, metadata)
        if index is None:
            continue
        processed += 1
        if abs(h - floor_level) <= floor_thickness:
            floor_counts[index] += 1
        height_above_floor = abs(h - floor_level)
        if obstacle_min_height <= height_above_floor <= obstacle_max_height:
            obstacle_counts[index] += 1

    floor_mask = [count >= floor_min_points_per_pixel for count in floor_counts]
    occupied_mask = [count >= obstacle_min_points_per_pixel for count in obstacle_counts]
    occupied_mask = dilate_occupied(occupied_mask, width, height, occupied_dilate_pixels)

    pixels = bytearray([UNKNOWN_VALUE] * (width * height))
    for index, is_floor in enumerate(floor_mask):
        if is_floor:
            pixels[index] = FREE_VALUE
    for index, is_occupied in enumerate(occupied_mask):
        if is_occupied:
            pixels[index] = OCCUPIED_VALUE

    metadata.update({
        "mode": "floor_obstacle",
        "floor_level_m": round(float(floor_level), 4),
        "floor_thickness_m": floor_thickness,
        "obstacle_min_height_m": obstacle_min_height,
        "obstacle_max_height_m": obstacle_max_height,
        "floor_min_points_per_pixel": floor_min_points_per_pixel,
        "obstacle_min_points_per_pixel": obstacle_min_points_per_pixel,
        "occupied_dilate_pixels": occupied_dilate_pixels,
        "input_points": len(points),
        "processed_points": processed,
        "pgm_values": "0=occupied, 205=unknown, 254=free floor",
    })
    return bytes(pixels), metadata, float(floor_level), processed


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_preview_png(pgm_path: Path, output_path: Path, scale: int) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for PNG preview") from exc
    image = Image.open(pgm_path).convert("L")
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    image.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the 20260818 PLY and project floor vs obstacle cells into a 2D map.")
    parser.add_argument("--ply", type=Path, default=Path("map_localization_test/outputs/20260818_dense.ply"), help="Input PLY file")
    parser.add_argument("--output-dir", type=Path, default=Path("map_localization_test/outputs/20260818_floor_obstacle"), help="Output directory")
    parser.add_argument("--up-axis", choices=("x", "y", "z"), default="z", help="Vertical axis of the point cloud")
    parser.add_argument("--meters-per-pixel", type=float, default=0.05, help="Map resolution in metres per pixel")
    parser.add_argument("--padding-m", type=float, default=0.5, help="Map border around the point cloud")
    parser.add_argument("--floor-thickness", type=float, default=0.08, help="Threshold around the floor estimate that counts as floor")
    parser.add_argument("--obstacle-min-height", type=float, default=0.10, help="Minimum height above floor for obstacle pixels")
    parser.add_argument("--obstacle-max-height", type=float, default=2.00, help="Maximum height above floor for obstacle pixels")
    parser.add_argument("--floor-min-points-per-pixel", type=int, default=2, help="How many floor points are needed to mark a free cell")
    parser.add_argument("--obstacle-min-points-per-pixel", type=int, default=2, help="How many obstacle points are needed to mark an occupied cell")
    parser.add_argument("--occupied-dilate-pixels", type=int, default=1, help="Expand occupied cells by this many pixels")
    parser.add_argument("--max-points", type=int, default=None, help="Short read for quick testing")
    parser.add_argument("--preview-png", action="store_true", help="Also save a PNG preview")
    parser.add_argument("--preview-scale", type=int, default=6, help="Zoom factor for the PNG preview")
    args = parser.parse_args()

    if not args.ply.exists():
        raise SystemExit(f"PLY file not found: {args.ply}")
    if args.meters_per_pixel <= 0:
        raise SystemExit("--meters-per-pixel must be positive")
    if args.preview_scale < 1:
        raise SystemExit("--preview-scale must be >= 1")

    pixels, metadata, floor_level, processed = build_floor_obstacle_map(
        ply_path=args.ply,
        up_axis=args.up_axis,
        meters_per_pixel=args.meters_per_pixel,
        padding_m=args.padding_m,
        floor_thickness=args.floor_thickness,
        obstacle_min_height=args.obstacle_min_height,
        obstacle_max_height=args.obstacle_max_height,
        floor_min_points_per_pixel=args.floor_min_points_per_pixel,
        obstacle_min_points_per_pixel=args.obstacle_min_points_per_pixel,
        occupied_dilate_pixels=args.occupied_dilate_pixels,
        max_points=args.max_points,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pgm_path = args.output_dir / "map_20260818_floor_obstacle.pgm"
    write_pgm(pgm_path, int(metadata["width_px"]), int(metadata["height_px"]), pixels)
    (args.output_dir / "map_20260818_floor_obstacle.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Detected floor level: {floor_level:.4f} m on {args.up_axis}-axis")
    print(f"Processed points: {processed}")
    print(f"Wrote map to {pgm_path}")
    print(f"Wrote metadata to {args.output_dir / 'map_20260818_floor_obstacle.json'}")

    if args.preview_png:
        preview_path = args.output_dir / "map_20260818_floor_obstacle_preview.png"
        write_preview_png(pgm_path, preview_path, args.preview_scale)
        print(f"Wrote preview PNG to {preview_path}")


if __name__ == "__main__":
    main()
