#!/usr/bin/env python3
"""Interactive pose simulation for checking the top-down map coordinate convention."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def write_pose(path: Path, x_m: float, y_m: float, yaw_deg: float, source: str) -> None:
    payload = {
        "x_m": round(x_m, 4),
        "y_m": round(y_m, 4),
        "yaw_deg": round(yaw_deg % 360, 2),
        "source": source,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate pose updates before connecting a real localizer.")
    parser.add_argument("--map-json", required=True, type=Path, help="map.json produced by build_topdown_map.py")
    parser.add_argument("--x", type=float, default=None, help="Initial world X coordinate in metres")
    parser.add_argument("--y", type=float, default=None, help="Initial world Y coordinate in metres")
    parser.add_argument("--yaw", type=float, default=0.0, help="Initial heading in degrees")
    parser.add_argument("--step-m", type=float, default=0.20, help="Distance moved by f or b")
    parser.add_argument("--turn-deg", type=float, default=15.0, help="Heading change for l or r")
    args = parser.parse_args()

    metadata = json.loads(args.map_json.read_text(encoding="utf-8"))
    origin_u = float(metadata["origin_u_m"])
    origin_v = float(metadata["origin_v_m"])
    resolution = float(metadata["meters_per_pixel"])
    width = int(metadata["width_px"])
    height = int(metadata["height_px"])
    x_m = args.x if args.x is not None else origin_u + width * resolution / 2
    y_m = args.y if args.y is not None else origin_v - height * resolution / 2
    yaw_deg = args.yaw % 360
    pose_path = args.map_json.parent / "current_pose.json"

    print("Mock pose tracker ready. Commands: f, b, l, r, p, q")
    print("Yaw 0 degrees points toward +X; yaw increases counter-clockwise.")
    while True:
        command = input("> ").strip().lower()
        if command == "q":
            break
        if command == "l":
            yaw_deg = (yaw_deg + args.turn_deg) % 360
        elif command == "r":
            yaw_deg = (yaw_deg - args.turn_deg) % 360
        elif command in {"f", "b"}:
            distance = args.step_m if command == "f" else -args.step_m
            yaw_rad = math.radians(yaw_deg)
            x_m += distance * math.cos(yaw_rad)
            y_m += distance * math.sin(yaw_rad)
        elif command != "p":
            print("Unknown command. Use f, b, l, r, p, or q.")
            continue

        write_pose(pose_path, x_m, y_m, yaw_deg, "mock_odometry")
        print(f"x={x_m:.2f} m, y={y_m:.2f} m, yaw={yaw_deg:.1f} deg -> {pose_path}")


if __name__ == "__main__":
    main()
