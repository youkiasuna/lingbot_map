"""Dry-run real-time visual navigation loop.

This connects a camera stream to ORB relocalization and Pure Pursuit.
It does not enable motor output unless --enable-esp32 is explicitly used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import cv2

from hardware.esp32_adapter import Esp32Adapter, Esp32Config
from localization.pose_gate import PoseGate, PoseGateConfig
from planner.pure_pursuit import PurePursuit, PurePursuitConfig
from planner.grid_navigation import plan_path
from experiments.orb_keyframe_localizer import OrbRelocalizer
from runtime.navigation_manager import NavigationManager


def load_waypoints(path: Path) -> list[tuple[float, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["waypoints"] if isinstance(payload, dict) else payload
    return [(float(item[0]), float(item[1])) for item in raw]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--waypoints", type=Path, help="Optional precomputed waypoint JSON")
    parser.add_argument("--map-dir", type=Path, help="Navigation map directory for runtime A*")
    parser.add_argument("--goal-x", type=float, help="Goal X coordinate in the navigation frame")
    parser.add_argument("--goal-y", type=float, help="Goal Y coordinate in the navigation frame")
    parser.add_argument("--url", required=True, help="Camera URL or device index")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--max-pose-age-s", type=float, default=0.5)
    parser.add_argument("--esp32-ip", default="192.168.4.1")
    parser.add_argument("--esp32-port", type=int, default=8888)
    parser.add_argument("--enable-esp32", action="store_true")
    return parser.parse_args()


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> int:
    args = parse_args()
    source = camera_source(args.url)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera source: {args.url}")

    localizer = OrbRelocalizer(args.mapping_dir)
    gate = PoseGate(PoseGateConfig(
        min_confidence=args.min_confidence,
        max_age_s=args.max_pose_age_s,
    ))
    controller = PurePursuit()
    manager = NavigationManager(gate, controller)
    static_waypoints = load_waypoints(args.waypoints) if args.waypoints else None
    dynamic_goal = args.map_dir is not None and args.goal_x is not None and args.goal_y is not None
    if static_waypoints is None and not dynamic_goal:
        raise SystemExit("Provide --waypoints or --map-dir with --goal-x and --goal-y")
    if static_waypoints is not None and dynamic_goal:
        raise SystemExit("Use either --waypoints or runtime A* goal arguments, not both")
    if static_waypoints is not None:
        manager.set_path(static_waypoints)
    planned_once = False

    adapter = Esp32Adapter(Esp32Config(
        host=args.esp32_ip,
        port=args.esp32_port,
        dry_run=not args.enable_esp32,
    ))

    frame_count = 0
    started = time.perf_counter()

    try:
        while args.max_frames == 0 or frame_count < args.max_frames:
            ok, frame = capture.read()
            if not ok:
                print("Camera frame unavailable; stopping.", flush=True)
                break

            result = localizer.localize_frame(
                frame,
                query_id=f"camera_{frame_count:06d}",
            )
            state = manager.update(result)

            if dynamic_goal and not planned_once and state.pose is not None and state.pose.accepted:
                assert state.pose.position_xyz is not None
                planned = plan_path(
                    args.map_dir,
                    state.pose.position_xyz[0],
                    state.pose.position_xyz[2],
                    args.goal_x,
                    args.goal_y,
                    use_obstacle_distance=True,
                )
                waypoints = [
                    (float(item["x_m"]), float(item["y_m"]))
                    for item in planned["waypoints"]
                ]
                manager.set_path(waypoints)
                planned_once = True
                state = manager.update(result)
                print(json.dumps({
                    "event": "astar_planned",
                    "waypoint_count": len(waypoints),
                    "path_length_m": planned["path_length_m"],
                }), flush=True)

            if state.mode == "LOCALIZATION_LOST":
                adapter.stop()
            else:
                adapter.send(state.command)

            if frame_count % 10 == 0:
                elapsed = max(time.perf_counter() - started, 1e-6)
                fps = (frame_count + 1) / elapsed
                print(
                    json.dumps({
                        "frame": frame_count,
                        "mode": state.mode,
                        "reason": state.reason,
                        "command": state.command.status,
                        "confidence": state.pose.confidence if state.pose else 0.0,
                        "fps": round(fps, 2),
                    }),
                    flush=True,
                )

            frame_count += 1
    finally:
        adapter.stop()
        capture.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
