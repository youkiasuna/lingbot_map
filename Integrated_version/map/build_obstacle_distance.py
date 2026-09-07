#!/usr/bin/env python3
"""Build a nearest-obstacle distance field from an occupancy map.

This is the small Python equivalent of the DDDMR perception layer's dynamic
graph value: every grid cell stores its distance to the closest occupied cell.
The field is written as float32 metres so the planner can apply a soft safety
penalty without treating every near-wall cell as immediately blocked.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import struct
from pathlib import Path

OCCUPIED_MAX_VALUE = 100


def read_pgm(path: Path) -> tuple[int, int, bytes]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"P5":
            raise ValueError(f"{path} is not a binary P5 PGM file.")
        tokens: list[bytes] = []
        while len(tokens) < 3:
            line = handle.readline()
            if not line:
                raise ValueError("PGM header ended unexpectedly.")
            tokens.extend(line.split(b"#", 1)[0].split())
        width, height, maximum = (int(token) for token in tokens[:3])
        if maximum != 255:
            raise ValueError("Only 8-bit PGM files are supported.")
        pixels = handle.read(width * height)
        if len(pixels) != width * height:
            raise ValueError("PGM pixel data ended unexpectedly.")
        return width, height, pixels


def build_distance_field(width: int, height: int, pixels: bytes, resolution: float) -> list[float]:
    distances = [math.inf] * (width * height)
    queue: list[tuple[float, int]] = []
    for index, value in enumerate(pixels):
        if value <= OCCUPIED_MAX_VALUE:
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
                nx = x + dx
                ny = y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                step = math.hypot(dx, dy) * resolution
                next_index = ny * width + nx
                next_distance = distance + step
                if next_distance < distances[next_index]:
                    distances[next_index] = next_distance
                    heapq.heappush(queue, (next_distance, next_index))
    return distances


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a nearest-obstacle distance field for an occupancy map.")
    parser.add_argument("--map-dir", required=True, type=Path, help="Directory containing map.pgm and map.json")
    parser.add_argument("--output", type=Path, default=None, help="Output float32 binary path")
    args = parser.parse_args()

    metadata_path = args.map_dir / "map.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    width, height, pixels = read_pgm(args.map_dir / "map.pgm")
    if width != int(metadata["width_px"]) or height != int(metadata["height_px"]):
        raise ValueError("map.pgm dimensions do not match map.json.")
    resolution = float(metadata["meters_per_pixel"])
    distances = build_distance_field(width, height, pixels, resolution)

    output = args.output or args.map_dir / "obstacle_distance.bin"
    output.write_bytes(struct.pack(f"<{len(distances)}f", *distances))
    distance_metadata = {
        "format_version": 1,
        "image": "obstacle_distance.bin",
        "width_px": width,
        "height_px": height,
        "meters_per_pixel": resolution,
        "value": "float32 metres to nearest occupied cell; inf means no occupied cell in map",
    }
    (output.parent / "obstacle_distance.json").write_text(
        json.dumps(distance_metadata, indent=2) + "\n", encoding="utf-8"
    )
    finite = [value for value in distances if math.isfinite(value)]
    print(f"Built distance field for {width}x{height} cells.")
    print(f"Finite distance range: {min(finite):.3f} to {max(finite):.3f} m")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()