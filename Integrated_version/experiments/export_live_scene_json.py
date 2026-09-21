#!/usr/bin/env python3
"""Export a compact RGB point cloud JSON snapshot for the live demo viewer."""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import time
from pathlib import Path
from typing import BinaryIO


PLY_TYPES = {
    "char": "b", "int8": "b", "uchar": "B", "uint8": "B",
    "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
    "int": "i", "int32": "i", "uint": "I", "uint32": "I",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_header(handle: BinaryIO) -> tuple[str, int, list[tuple[str, str]]]:
    if handle.readline().decode("ascii", errors="strict").strip() != "ply":
        raise ValueError("Input is not a PLY file.")
    file_format = ""
    vertex_count = 0
    properties: list[tuple[str, str]] = []
    in_vertices = False
    while True:
        raw = handle.readline()
        if not raw:
            raise ValueError("PLY header ended before end_header.")
        line = raw.decode("ascii", errors="strict").strip()
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format":
            file_format = parts[1]
        elif parts[0] == "element":
            in_vertices = parts[1] == "vertex"
            if in_vertices:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertices:
            if len(parts) != 3 or parts[1] == "list" or parts[1] not in PLY_TYPES:
                raise ValueError("Only scalar binary PLY vertex properties are supported.")
            properties.append((parts[1], parts[2]))
        elif parts[0] == "end_header":
            break
    if file_format != "binary_little_endian":
        raise ValueError(f"Unsupported PLY format: {file_format}")
    names = {name for _, name in properties}
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError("PLY vertices must include x, y, z.")
    return file_format, vertex_count, properties


def read_points(path: Path, max_points: int) -> tuple[list[list[float | int]], int, int]:
    with path.open("rb") as handle:
        _, vertex_count, properties = read_header(handle)
        stride = max(1, math.ceil(vertex_count / max_points))
        indices = {name: index for index, (_, name) in enumerate(properties)}
        fmt = "<" + "".join(PLY_TYPES[data_type] for data_type, _ in properties)
        row = struct.Struct(fmt)
        points: list[list[float | int]] = []
        for vertex_index in range(vertex_count):
            raw = handle.read(row.size)
            if len(raw) != row.size:
                raise ValueError("PLY vertex data ended unexpectedly.")
            if vertex_index % stride:
                continue
            values = row.unpack(raw)
            red = int(values[indices["red"]]) if "red" in indices else 235
            green = int(values[indices["green"]]) if "green" in indices else 235
            blue = int(values[indices["blue"]]) if "blue" in indices else 235
            points.append([
                round(float(values[indices["x"]]), 4),
                round(float(values[indices["y"]]), 4),
                round(float(values[indices["z"]]), 4),
                max(0, min(255, red)),
                max(0, min(255, green)),
                max(0, min(255, blue)),
            ])
    return points, vertex_count, stride


def bounds(points: list[list[float | int]]) -> dict[str, float]:
    if not points:
        return {"minX": 0, "maxX": 1, "minY": 0, "maxY": 1, "minZ": 0, "maxZ": 1}
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    zs = [float(point[2]) for point in points]
    return {
        "minX": min(xs), "maxX": max(xs),
        "minY": min(ys), "maxY": max(ys),
        "minZ": min(zs), "maxZ": max(zs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ply", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-points", type=int, default=45000)
    parser.add_argument("--frame-count", type=int, default=0)
    parser.add_argument("--update-index", type=int, default=0)
    args = parser.parse_args()
    if args.max_points < 100:
        parser.error("--max-points must be at least 100")
    return args


def main() -> int:
    args = parse_args()
    points, source_vertices, stride = read_points(args.ply.resolve(), args.max_points)
    payload = {
        "schema_version": 1,
        "source": str(args.ply.resolve()),
        "generated_at_unix": time.time(),
        "frame_count": args.frame_count,
        "update_index": args.update_index,
        "source_vertices": source_vertices,
        "sample_stride": stride,
        "sampled_points": len(points),
        "coordinate_hint": "LingBot world coordinates from rebuilt_colored_map.ply; viewer treats -Y as vertical.",
        "bounds": bounds(points),
        "points": points,
    }
    atomic_json(args.output.resolve(), payload)
    print(f"Wrote {args.output.resolve()} ({len(points)} sampled points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
