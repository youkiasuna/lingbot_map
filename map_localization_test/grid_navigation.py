#!/usr/bin/env python3
"""Plan paths on a PGM occupancy grid produced by build_topdown_map.py."""

from __future__ import annotations

import argparse
import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


OCCUPIED_MAX_VALUE = 100
UNKNOWN_VALUE = 205


@dataclass(frozen=True)
class GridMap:
    width: int
    height: int
    pixels: bytes
    metadata: dict[str, float | int | str]

    @property
    def resolution(self) -> float:
        return float(self.metadata["meters_per_pixel"])

    @property
    def origin_u(self) -> float:
        return float(self.metadata["origin_u_m"])

    @property
    def origin_v(self) -> float:
        return float(self.metadata["origin_v_m"])

    def world_to_pixel(self, x_m: float, y_m: float) -> tuple[int, int]:
        px = int((x_m - self.origin_u) / self.resolution)
        py = int((self.origin_v - y_m) / self.resolution)
        return px, py

    def pixel_to_world(self, px: int, py: int) -> tuple[float, float]:
        x_m = self.origin_u + (px + 0.5) * self.resolution
        y_m = self.origin_v - (py + 0.5) * self.resolution
        return x_m, y_m

    def in_bounds(self, px: int, py: int) -> bool:
        return 0 <= px < self.width and 0 <= py < self.height

    def value_at(self, px: int, py: int) -> int:
        return self.pixels[py * self.width + px]

    def is_traversable(self, px: int, py: int, allow_unknown: bool = False) -> bool:
        if not self.in_bounds(px, py):
            return False
        value = self.value_at(px, py)
        if value <= OCCUPIED_MAX_VALUE:
            return False
        if not allow_unknown and value == UNKNOWN_VALUE:
            return False
        return True


def read_pgm(path: Path) -> tuple[int, int, bytes]:
    with path.open("rb") as handle:
        magic = handle.readline().strip()
        if magic != b"P5":
            raise ValueError(f"{path} is not a binary P5 PGM file.")

        tokens: list[bytes] = []
        while len(tokens) < 3:
            line = handle.readline()
            if not line:
                raise ValueError("PGM header ended unexpectedly.")
            line = line.split(b"#", 1)[0]
            tokens.extend(line.split())

        width, height, max_value = (int(token) for token in tokens[:3])
        if max_value != 255:
            raise ValueError("Only 8-bit PGM files are supported.")

        pixels = handle.read(width * height)
        if len(pixels) != width * height:
            raise ValueError("PGM pixel data ended unexpectedly.")
        return width, height, pixels


def load_grid_map(map_dir: Path) -> GridMap:
    metadata_path = map_dir / "map.json"
    pgm_path = map_dir / "map.pgm"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    width, height, pixels = read_pgm(pgm_path)
    if width != int(metadata["width_px"]) or height != int(metadata["height_px"]):
        raise ValueError("map.pgm dimensions do not match map.json.")
    return GridMap(width=width, height=height, pixels=pixels, metadata=metadata)


def octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2.0) - 2.0) * min(dx, dy)


def neighbors(grid: GridMap, node: tuple[int, int], allow_unknown: bool) -> Iterable[tuple[tuple[int, int], float]]:
    x, y = node
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = x + dx
            ny = y + dy
            if not grid.is_traversable(nx, ny, allow_unknown):
                continue
            if dx != 0 and dy != 0:
                if not grid.is_traversable(x + dx, y, allow_unknown):
                    continue
                if not grid.is_traversable(x, y + dy, allow_unknown):
                    continue
                yield (nx, ny), math.sqrt(2.0)
            else:
                yield (nx, ny), 1.0


def astar_pixels(
    grid: GridMap,
    start: tuple[int, int],
    goal: tuple[int, int],
    allow_unknown: bool = False,
) -> list[tuple[int, int]]:
    if not grid.is_traversable(*start, allow_unknown=allow_unknown):
        raise ValueError(f"Start pixel {start} is not traversable.")
    if not grid.is_traversable(*goal, allow_unknown=allow_unknown):
        raise ValueError(f"Goal pixel {goal} is not traversable.")

    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (octile_distance(start, goal), 0, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score = {start: 0.0}
    sequence = 0

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            return reconstruct_path(came_from, current)

        current_g = g_score[current]
        for next_node, step_cost in neighbors(grid, current, allow_unknown):
            tentative_g = current_g + step_cost
            if tentative_g >= g_score.get(next_node, math.inf):
                continue
            came_from[next_node] = current
            g_score[next_node] = tentative_g
            sequence += 1
            priority = tentative_g + octile_distance(next_node, goal)
            heapq.heappush(open_heap, (priority, sequence, next_node))

    raise ValueError("No path found between start and goal.")


def reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int]],
    current: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def line_pixels(a: tuple[int, int], b: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def has_line_of_sight(
    grid: GridMap,
    a: tuple[int, int],
    b: tuple[int, int],
    allow_unknown: bool,
) -> bool:
    return all(grid.is_traversable(px, py, allow_unknown) for px, py in line_pixels(a, b))


def simplify_path(
    grid: GridMap,
    path: list[tuple[int, int]],
    allow_unknown: bool = False,
) -> list[tuple[int, int]]:
    if len(path) <= 2:
        return path

    simplified = [path[0]]
    anchor = 0
    probe = 2
    while probe < len(path):
        if has_line_of_sight(grid, path[anchor], path[probe], allow_unknown):
            probe += 1
            continue
        simplified.append(path[probe - 1])
        anchor = probe - 1
        probe = anchor + 2
    simplified.append(path[-1])
    return simplified


def path_length_m(grid: GridMap, path: list[tuple[int, int]]) -> float:
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1]) * grid.resolution
    return total


def plan_path(
    map_dir: Path,
    start_x_m: float,
    start_y_m: float,
    goal_x_m: float,
    goal_y_m: float,
    allow_unknown: bool = False,
) -> dict[str, object]:
    grid = load_grid_map(map_dir)
    start_px = grid.world_to_pixel(start_x_m, start_y_m)
    goal_px = grid.world_to_pixel(goal_x_m, goal_y_m)
    raw_pixels = astar_pixels(grid, start_px, goal_px, allow_unknown)
    waypoint_pixels = simplify_path(grid, raw_pixels, allow_unknown)
    raw_world = [{"x_m": x, "y_m": y} for x, y in (grid.pixel_to_world(px, py) for px, py in raw_pixels)]
    waypoints = [{"x_m": x, "y_m": y} for x, y in (grid.pixel_to_world(px, py) for px, py in waypoint_pixels)]
    return {
        "status": "planned",
        "start": {"x_m": start_x_m, "y_m": start_y_m, "pixel": list(start_px)},
        "goal": {"x_m": goal_x_m, "y_m": goal_y_m, "pixel": list(goal_px)},
        "allow_unknown": allow_unknown,
        "raw_grid_points": len(raw_pixels),
        "waypoint_count": len(waypoints),
        "path_length_m": round(path_length_m(grid, raw_pixels), 4),
        "raw_path": raw_world,
        "waypoints": waypoints,
    }


def read_pose(map_dir: Path) -> dict[str, float | str]:
    pose_path = map_dir / "current_pose.json"
    if not pose_path.exists():
        raise FileNotFoundError(f"Pose file not found: {pose_path}")
    pose = json.loads(pose_path.read_text(encoding="utf-8"))
    return pose


def main() -> None:
    parser = argparse.ArgumentParser(description="Run A* between the current robot pose and a goal.")
    parser.add_argument("--map-dir", required=True, type=Path, help="Directory containing map.pgm and map.json")
    parser.add_argument("--goal-x", required=True, type=float, help="Goal X coordinate in metres")
    parser.add_argument("--goal-y", required=True, type=float, help="Goal Y coordinate in metres")
    parser.add_argument("--start-x", type=float, default=None, help="Start X coordinate in metres")
    parser.add_argument("--start-y", type=float, default=None, help="Start Y coordinate in metres")
    parser.add_argument("--allow-unknown", action="store_true", help="Allow planning through unknown cells")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    if args.start_x is None or args.start_y is None:
        pose = read_pose(args.map_dir)
        start_x = float(pose["x_m"])
        start_y = float(pose["y_m"])
    else:
        start_x = args.start_x
        start_y = args.start_y

    result = plan_path(
        args.map_dir,
        start_x,
        start_y,
        args.goal_x,
        args.goal_y,
        args.allow_unknown,
    )
    output_path = args.output or args.map_dir / "planned_path.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"Planned {result['path_length_m']} m path with "
        f"{result['raw_grid_points']} grid points and {result['waypoint_count']} waypoints."
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
