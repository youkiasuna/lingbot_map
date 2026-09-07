#!/usr/bin/env python3
"""Simulate a differential-drive vehicle following a planned grid path."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "planner") not in sys.path:
    sys.path.insert(0, str(ROOT / "planner"))

from grid_navigation import GridMap, astar_pixels, load_grid_map, load_obstacle_distance, simplify_path


def choose_endpoints(grid: GridMap) -> tuple[tuple[int, int], tuple[int, int]]:
    free = [(x, y) for y in range(grid.height) for x in range(grid.width) if grid.is_traversable(x, y)]
    if len(free) < 2:
        raise ValueError("Navigation map has fewer than two free cells.")
    start = free[len(free) // 2]
    reachable = {start}
    queue = [start]
    while queue:
        x, y = queue.pop(0)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            node = (x + dx, y + dy)
            if node in reachable or not grid.is_traversable(*node):
                continue
            reachable.add(node)
            queue.append(node)
    goal = max(reachable, key=lambda node: (node[0] - start[0]) ** 2 + (node[1] - start[1]) ** 2)
    return start, goal


def footprint_clear(grid: GridMap, x_m: float, y_m: float, radius_m: float, allow_unknown: bool) -> bool:
    px, py = grid.world_to_pixel(x_m, y_m)
    if radius_m <= 0:
        return grid.is_traversable(px, py, allow_unknown)
    radius_px = max(1, math.ceil(radius_m / grid.resolution))
    for dy in range(-radius_px, radius_px + 1):
        for dx in range(-radius_px, radius_px + 1):
            if dx * dx + dy * dy > radius_px * radius_px:
                continue
            if not grid.is_traversable(px + dx, py + dy, allow_unknown):
                return False
    return True


def simulate(
    grid: GridMap,
    waypoints: list[tuple[float, float]],
    radius_m: float,
    max_speed_mps: float,
    max_angular_speed_radps: float,
    dt_s: float,
    goal_tolerance_m: float,
    allow_unknown: bool,
) -> tuple[list[dict[str, float]], bool, str]:
    x, y = waypoints[0]
    yaw = math.atan2(waypoints[min(1, len(waypoints) - 1)][1] - y, waypoints[min(1, len(waypoints) - 1)][0] - x)
    trajectory = [{"x_m": x, "y_m": y, "yaw_rad": yaw, "time_s": 0.0}]
    elapsed = 0.0
    waypoint_index = 1
    max_steps = 20_000

    for _ in range(max_steps):
        if waypoint_index >= len(waypoints):
            return trajectory, True, "goal_reached"
        target_x, target_y = waypoints[waypoint_index]
        distance = math.hypot(target_x - x, target_y - y)
        if distance <= goal_tolerance_m:
            waypoint_index += 1
            continue
        desired_yaw = math.atan2(target_y - y, target_x - x)
        yaw_error = (desired_yaw - yaw + math.pi) % (2 * math.pi) - math.pi
        angular = max(-max_angular_speed_radps, min(max_angular_speed_radps, 2.0 * yaw_error))
        if abs(yaw_error) > 0.35:
            linear = 0.0
        else:
            speed_scale = max(0.0, 1.0 - min(abs(yaw_error) / 0.35, 1.0))
            linear = max_speed_mps * speed_scale
        next_yaw = yaw + angular * dt_s
        next_x = x + linear * math.cos(next_yaw) * dt_s
        next_y = y + linear * math.sin(next_yaw) * dt_s
        if not footprint_clear(grid, next_x, next_y, radius_m, allow_unknown):
            return trajectory, False, "collision_or_unknown"
        x, y, yaw = next_x, next_y, next_yaw
        elapsed += dt_s
        trajectory.append({"x_m": x, "y_m": y, "yaw_rad": yaw, "time_s": elapsed})
    return trajectory, False, "simulation_timeout"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a differential-drive vehicle on a navigation map.")
    parser.add_argument("--map-dir", required=True, type=Path)
    parser.add_argument("--start-x", type=float, default=None)
    parser.add_argument("--start-y", type=float, default=None)
    parser.add_argument("--goal-x", type=float, default=None)
    parser.add_argument("--goal-y", type=float, default=None)
    parser.add_argument("--robot-radius-m", type=float, default=None)
    parser.add_argument("--max-speed-mps", type=float, default=0.15)
    parser.add_argument("--max-angular-speed-radps", type=float, default=0.7)
    parser.add_argument("--dt-s", type=float, default=0.05)
    parser.add_argument("--goal-tolerance-m", type=float, default=0.10)
    parser.add_argument("--allow-unknown", action="store_true")
    parser.add_argument("--use-obstacle-distance", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    metadata = json.loads((args.map_dir / "navigation_map.json").read_text(encoding="utf-8"))
    grid = load_grid_map(args.map_dir)
    radius = args.robot_radius_m if args.robot_radius_m is not None else float(metadata.get("robot_radius_m", 0.2))
    map_radius = float(metadata.get("robot_radius_m", 0.0))
    collision_radius = max(0.0, radius - map_radius)
    if args.start_x is None or args.start_y is None or args.goal_x is None or args.goal_y is None:
        start_px, goal_px = choose_endpoints(grid)
        start = grid.pixel_to_world(*start_px)
        goal = grid.pixel_to_world(*goal_px)
    else:
        start = (args.start_x, args.start_y)
        goal = (args.goal_x, args.goal_y)
    start_px = grid.world_to_pixel(*start)
    goal_px = grid.world_to_pixel(*goal)
    distances = load_obstacle_distance(args.map_dir, grid) if args.use_obstacle_distance else None
    raw = astar_pixels(grid, start_px, goal_px, False, distances, radius * 2.0, 1.0)
    simplified = simplify_path(grid, raw, False)
    waypoints = [grid.pixel_to_world(*pixel) for pixel in simplified]
    trajectory, success, reason = simulate(
        grid, waypoints, collision_radius, args.max_speed_mps, args.max_angular_speed_radps,
        args.dt_s, args.goal_tolerance_m, args.allow_unknown,
    )
    output = args.output or args.map_dir / "simulated_vehicle_path.json"
    result = {
        "status": "completed" if success else "failed",
        "reason": reason,
        "vehicle": {"type": "differential_drive_unicycle", "radius_m": radius, "map_inflation_radius_m": map_radius, "additional_collision_radius_m": collision_radius, "max_speed_mps": args.max_speed_mps, "max_angular_speed_radps": args.max_angular_speed_radps},
        "start": {"x_m": start[0], "y_m": start[1], "pixel": list(start_px)},
        "goal": {"x_m": goal[0], "y_m": goal[1], "pixel": list(goal_px)},
        "planner_waypoints": [{"x_m": x, "y_m": y} for x, y in waypoints],
        "trajectory": trajectory,
        "trajectory_point_count": len(trajectory),
        "simulation_time_s": trajectory[-1]["time_s"],
    }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Simulation {result['status']}: {reason}")
    print(f"Start={start}, goal={goal}, trajectory_points={len(trajectory)}, time={trajectory[-1]['time_s']:.2f}s")
    print(f"Wrote {output}")
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
