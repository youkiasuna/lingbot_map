#!/usr/bin/env python3
"""Project a PLY point cloud into a 2D PGM map."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator


PLY_TYPES = {
    "char": "b", "int8": "b", "uchar": "B", "uint8": "B",
    "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
    "int": "i", "int32": "i", "uint": "I", "uint32": "I",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
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


def read_vertices(ply_path: Path, max_points: int | None) -> list[tuple[float, float, float]]:
    result = list(iter_vertices(ply_path, max_points))
    if not result:
        raise ValueError("No vertices were read from the PLY file.")
    return result


def select_plane_values(point: tuple[float, float, float], up_axis: str) -> tuple[float, float, float]:
    x, y, z = point
    if up_axis == "z":
        return x, y, z
    if up_axis == "y":
        return x, z, y
    return y, z, x


def select_plane(point: tuple[float, float, float], up_axis: str) -> tuple[float, float]:
    u, v, _ = select_plane_values(point, up_axis)
    return u, v


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot compute percentile of an empty sample.")
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return values[index]


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
        raise ValueError(
            f"Map would be {width}x{height} pixels. Increase --meters-per-pixel."
        )
    return {
        "format_version": 2,
        "image": "map.pgm",
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


def make_density_map(
    points: Iterable[tuple[float, float, float]],
    up_axis: str,
    meters_per_pixel: float,
    padding_m: float,
    min_points_per_pixel: int,
) -> tuple[bytes, dict[str, float | int | str]]:
    plane_points = [select_plane(point, up_axis) for point in points]
    if not plane_points:
        raise ValueError("No vertices were read from the PLY file.")
    min_u = min(point[0] for point in plane_points) - padding_m
    max_u = max(point[0] for point in plane_points) + padding_m
    min_v = min(point[1] for point in plane_points) - padding_m
    max_v = max(point[1] for point in plane_points) + padding_m
    metadata = make_grid_metadata(min_u, max_u, min_v, max_v, up_axis, meters_per_pixel)
    width = int(metadata["width_px"])
    height = int(metadata["height_px"])

    density = [0] * (width * height)
    for u, v in plane_points:
        index = point_to_index(u, v, metadata)
        if index is not None:
            density[index] += 1

    max_density = max(density)
    pixels = bytearray(width * height)
    if max_density > 0:
        for index, count in enumerate(density):
            if count >= min_points_per_pixel:
                pixels[index] = min(255, round(255 * math.log1p(count) / math.log1p(max_density)))
    metadata["mode"] = "density"
    metadata["min_points_per_pixel"] = min_points_per_pixel
    return bytes(pixels), metadata


def scan_bounds_and_floor(
    ply_path: Path,
    up_axis: str,
    padding_m: float,
    floor_side: str,
    max_points: int | None,
    max_floor_samples: int,
) -> tuple[dict[str, float | int | str], float, int]:
    min_u = min_v = math.inf
    max_u = max_v = -math.inf
    height_samples: list[float] = []
    sample_step = 1
    count = 0

    for count, point in enumerate(iter_vertices(ply_path, max_points), start=1):
        u, v, h = select_plane_values(point, up_axis)
        min_u = min(min_u, u)
        max_u = max(max_u, u)
        min_v = min(min_v, v)
        max_v = max(max_v, v)
        if len(height_samples) < max_floor_samples:
            height_samples.append(h)
        elif count % sample_step == 0:
            height_samples[count // sample_step % max_floor_samples] = h
        if count == max_floor_samples:
            sample_step = max(1, count // max_floor_samples)

    if count == 0:
        raise ValueError("No vertices were read from the PLY file.")

    floor_fraction = 0.05 if floor_side == "lower" else 0.95
    floor_level = percentile(height_samples, floor_fraction)
    metadata = make_grid_metadata(
        min_u - padding_m,
        max_u + padding_m,
        min_v - padding_m,
        max_v + padding_m,
        up_axis,
        float(metadata_resolution_placeholder := 1.0),
    )
    metadata["meters_per_pixel"] = metadata_resolution_placeholder
    return metadata, floor_level, count


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


def make_occupancy_map(
    ply_path: Path,
    up_axis: str,
    meters_per_pixel: float,
    padding_m: float,
    min_points_per_pixel: int,
    floor_min_points_per_pixel: int,
    floor_side: str,
    floor_level_arg: float | None,
    floor_thickness: float,
    obstacle_min_height: float,
    obstacle_max_height: float,
    occupied_dilate_pixels: int,
    max_points: int | None,
) -> tuple[bytes, dict[str, float | int | str]]:
    min_u = min_v = math.inf
    max_u = max_v = -math.inf
    height_samples: list[float] = []
    count = 0
    max_floor_samples = 200_000

    print("Scanning point cloud bounds and floor level...")
    for count, point in enumerate(iter_vertices(ply_path, max_points), start=1):
        u, v, h = select_plane_values(point, up_axis)
        min_u = min(min_u, u)
        max_u = max(max_u, u)
        min_v = min(min_v, v)
        max_v = max(max_v, v)
        if len(height_samples) < max_floor_samples:
            height_samples.append(h)
        else:
            slot = count % max_floor_samples
            height_samples[slot] = h

    if count == 0:
        raise ValueError("No vertices were read from the PLY file.")

    if floor_level_arg is None:
        floor_fraction = 0.05 if floor_side == "lower" else 0.95
        floor_level = percentile(height_samples, floor_fraction)
    else:
        floor_level = floor_level_arg

    metadata = make_grid_metadata(
        min_u - padding_m,
        max_u + padding_m,
        min_v - padding_m,
        max_v + padding_m,
        up_axis,
        meters_per_pixel,
    )
    width = int(metadata["width_px"])
    height = int(metadata["height_px"])
    floor_counts = [0] * (width * height)
    obstacle_counts = [0] * (width * height)

    print(
        f"Classifying floor and walls: floor_level={floor_level:.4f}, "
        f"floor_side={floor_side}, grid={width}x{height}"
    )
    used = 0
    floor_points = 0
    obstacle_points = 0
    for point in iter_vertices(ply_path, max_points):
        u, v, h = select_plane_values(point, up_axis)
        index = point_to_index(u, v, metadata)
        if index is None:
            continue
        used += 1
        height_from_floor = h - floor_level if floor_side == "lower" else floor_level - h
        if abs(h - floor_level) <= floor_thickness:
            floor_counts[index] += 1
            floor_points += 1
        if obstacle_min_height <= height_from_floor <= obstacle_max_height:
            obstacle_counts[index] += 1
            obstacle_points += 1

    floor_mask = [count >= floor_min_points_per_pixel for count in floor_counts]
    occupied_mask = [count >= min_points_per_pixel for count in obstacle_counts]
    occupied_mask = dilate_occupied(occupied_mask, width, height, occupied_dilate_pixels)

    pixels = bytearray([UNKNOWN_VALUE] * (width * height))
    for index, is_floor in enumerate(floor_mask):
        if is_floor:
            pixels[index] = FREE_VALUE
    for index, is_occupied in enumerate(occupied_mask):
        if is_occupied:
            pixels[index] = OCCUPIED_VALUE

    metadata.update({
        "mode": "occupancy",
        "floor_side": floor_side,
        "floor_level_m": floor_level,
        "floor_thickness_m": floor_thickness,
        "obstacle_min_height_m": obstacle_min_height,
        "obstacle_max_height_m": obstacle_max_height,
        "min_points_per_pixel": min_points_per_pixel,
        "floor_min_points_per_pixel": floor_min_points_per_pixel,
        "occupied_dilate_pixels": occupied_dilate_pixels,
        "input_points": count,
        "used_points": used,
        "floor_points": floor_points,
        "obstacle_points": obstacle_points,
        "pgm_values": "0=occupied, 205=unknown, 254=free floor",
    })
    return bytes(pixels), metadata


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def write_preview_png(pgm_path: Path, output_path: Path, scale: int) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for --preview-png") from exc
    image = Image.open(pgm_path).convert("L")
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    image.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a PLY point cloud into a 2D map.")
    parser.add_argument("--ply", required=True, type=Path, help="Input ASCII or binary-little-endian PLY file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for map.pgm and map.json")
    parser.add_argument("--mode", choices=("density", "occupancy"), default="density", help="Map generation mode")
    parser.add_argument("--up-axis", choices=("x", "y", "z"), default="z", help="Vertical axis of the point cloud")
    parser.add_argument("--meters-per-pixel", type=float, default=0.05, help="Map resolution")
    parser.add_argument("--padding-m", type=float, default=0.5, help="Map border around the cloud")
    parser.add_argument("--min-points-per-pixel", type=int, default=1, help="Density/obstacle points needed per cell")
    parser.add_argument("--max-points", type=int, default=None, help="Read only the first N vertices for a quick test")
    parser.add_argument("--floor-side", choices=("lower", "upper"), default="upper", help="Which side of the up axis is the floor")
    parser.add_argument("--floor-level", type=float, default=None, help="Explicit floor coordinate on the up axis")
    parser.add_argument("--floor-thickness", type=float, default=0.06, help="Floor band thickness around floor level")
    parser.add_argument("--floor-min-points-per-pixel", type=int, default=1, help="Floor points needed to mark a free cell")
    parser.add_argument("--obstacle-min-height", type=float, default=0.10, help="Minimum obstacle height above floor")
    parser.add_argument("--obstacle-max-height", type=float, default=1.40, help="Maximum obstacle height above floor")
    parser.add_argument("--occupied-dilate-pixels", type=int, default=1, help="Thicken occupied cells by this radius")
    parser.add_argument("--preview-png", action="store_true", help="Also write map_preview.png")
    parser.add_argument("--preview-scale", type=int, default=6, help="Nearest-neighbour preview scale")
    args = parser.parse_args()

    if args.meters_per_pixel <= 0:
        parser.error("--meters-per-pixel must be positive")
    if args.padding_m < 0:
        parser.error("--padding-m must not be negative")
    if args.min_points_per_pixel < 1:
        parser.error("--min-points-per-pixel must be at least 1")
    if args.floor_min_points_per_pixel < 1:
        parser.error("--floor-min-points-per-pixel must be at least 1")
    if args.preview_scale < 1:
        parser.error("--preview-scale must be at least 1")

    if args.mode == "density":
        points = read_vertices(args.ply, args.max_points)
        pixels, metadata = make_density_map(
            points,
            args.up_axis,
            args.meters_per_pixel,
            args.padding_m,
            args.min_points_per_pixel,
        )
        read_count = len(points)
    else:
        pixels, metadata = make_occupancy_map(
            args.ply,
            args.up_axis,
            args.meters_per_pixel,
            args.padding_m,
            args.min_points_per_pixel,
            args.floor_min_points_per_pixel,
            args.floor_side,
            args.floor_level,
            args.floor_thickness,
            args.obstacle_min_height,
            args.obstacle_max_height,
            args.occupied_dilate_pixels,
            args.max_points,
        )
        read_count = int(metadata["input_points"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pgm_path = args.output_dir / "map.pgm"
    write_pgm(pgm_path, int(metadata["width_px"]), int(metadata["height_px"]), pixels)
    (args.output_dir / "map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Read {read_count} vertices from {args.ply}")
    print(f"Wrote {metadata['width_px']}x{metadata['height_px']} map to {args.output_dir}")

    if args.preview_png:
        preview_path = args.output_dir / "map_preview.png"
        write_preview_png(pgm_path, preview_path, args.preview_scale)
        print(f"Wrote preview PNG to {preview_path}")


if __name__ == "__main__":
    main()
