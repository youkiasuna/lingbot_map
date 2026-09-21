"""Dry-run real-time visual navigation loop.

This connects a camera stream to ORB relocalization, A* planning, and Pure
Pursuit. Hardware motor output is intentionally disabled in this prototype.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import cv2

from hardware.esp32_adapter import Esp32Adapter, Esp32Config
from localization.pose_gate import PoseGate, PoseGateConfig
from planner.pure_pursuit import PurePursuit, PurePursuitConfig, TwistCommand
from planner.grid_navigation import plan_path
from experiments.orb_keyframe_localizer import OrbRelocalizer
from runtime.navigation_manager import NavigationManager
from runtime.live_map_manager import LiveMapManager
from runtime.live_viewer_state import LiveViewerState


def load_waypoints(path: Path) -> list[tuple[float, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["waypoints"] if isinstance(payload, dict) else payload
    return [(float(item[0]), float(item[1])) for item in raw]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--waypoints", type=Path, help="Optional precomputed waypoint JSON in X/Z navigation coordinates")
    parser.add_argument("--map-dir", type=Path, help="Navigation map directory for runtime A*")
    parser.add_argument("--goal-x", type=float, help="Goal X coordinate in the X/Z navigation frame")
    parser.add_argument("--goal-y", type=float, help="Goal Y coordinate in the X/Z navigation frame")
    parser.add_argument("--url", required=True, help="Camera URL or device index")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--max-pose-age-s", type=float, default=0.5)
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--frame-stride", type=int, default=1, help="Reference frame stride for ORB matching; 1 loads every mapping frame")
    parser.add_argument("--resize-mode", choices=("stretch", "letterbox", "cover_crop"), default="cover_crop")
    parser.add_argument("--ratio", type=float, default=0.75)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-matches", type=int, default=25)
    parser.add_argument("--min-inliers", type=int, default=12)
    parser.add_argument("--max-pnp-points", type=int, default=300)
    parser.add_argument("--reprojection-error-px", type=float, default=5.0)
    parser.add_argument("--pnp-iterations", type=int, default=200)
    parser.add_argument("--esp32-ip", default="dry-run-only", help="Retained for CLI compatibility; hardware output is disabled")
    parser.add_argument("--esp32-port", type=int, default=8888)
    parser.add_argument("--enable-esp32", action="store_true", help="Disabled: real motor output is not available in this prototype")
    parser.add_argument(
        "--command-log",
        type=Path,
        default=Path("outputs/runtime/realtime_navigation_commands.jsonl"),
        help="Append dry-run velocity commands to this JSONL file",
    )
    return parser.parse_args()


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def reconstruction_xyz_to_navigation_xy(position_xyz: list[float]) -> tuple[float, float]:
    """Convert LingBot -Y-up reconstruction coordinates to planar navigation X/Y."""
    return float(position_xyz[0]), float(position_xyz[2])


def best_value(result: dict[str, Any], key: str, default: Any = None) -> Any:
    best = result.get("best")
    if isinstance(best, dict):
        return best.get(key, default)
    return default


def localization_summary(
    frame_count: int,
    frame: Any,
    result: dict[str, Any],
    state_mode: str,
    state_reason: str,
    command_status: str,
    fps: float,
    astar_status: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "event": "frame_summary",
        "frame": frame_count,
        "frame_resolution": [int(frame.shape[1]), int(frame.shape[0])],
        "query_keypoints": int(result.get("query_keypoint_count", 0)),
        "reference_count": int(result.get("reference_count", 0)),
        "match_count": int(best_value(result, "match_count", 0) or 0),
        "inlier_count": int(best_value(result, "inlier_count", 0) or 0),
        "confidence": float(best_value(result, "confidence", 0.0) or 0.0),
        "localization_status": result.get("status", "unknown"),
        "mode": state_mode,
        "reason": state_reason,
        "fps": round(fps, 2),
        "astar": astar_status,
        "pure_pursuit_command": command_status,
        "safety_stop": command_status == "safety_stop",
    }


def main() -> int:
    args = parse_args()
    if args.enable_esp32:
        raise SystemExit("--enable-esp32 is disabled for this prototype; dry-run is mandatory.")

    source = camera_source(args.url)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera source: {args.url}")

    localizer = OrbRelocalizer(
        args.mapping_dir,
        max_features=args.max_features,
        frame_stride=args.frame_stride,
        ratio=args.ratio,
        top_k=args.top_k,
        min_matches=args.min_matches,
        min_inliers=args.min_inliers,
        max_pnp_points=args.max_pnp_points,
        reprojection_error_px=args.reprojection_error_px,
        pnp_iterations=args.pnp_iterations,
    )
    gate = PoseGate(PoseGateConfig(
        min_confidence=args.min_confidence,
        max_age_s=args.max_pose_age_s,
    ))
    controller = PurePursuit(PurePursuitConfig())
    manager = NavigationManager(gate, controller)
    live_map = LiveMapManager(args.live_map_dir)
    viewer_state = LiveViewerState(live_map)
    static_waypoints = load_waypoints(args.waypoints) if args.waypoints else None
    dynamic_goal = args.map_dir is not None and args.goal_x is not None and args.goal_y is not None
    if static_waypoints is None and not dynamic_goal:
        raise SystemExit("Provide --waypoints or --map-dir with --goal-x and --goal-y")
    if static_waypoints is not None and dynamic_goal:
        raise SystemExit("Use either --waypoints or runtime A* goal arguments, not both")
    if static_waypoints is not None:
        manager.set_path(static_waypoints)
    planned_once = False
    astar_status: dict[str, Any] | None = None
    planner_failed = False

    adapter = Esp32Adapter(Esp32Config(
        host=args.esp32_ip,
        port=args.esp32_port,
        dry_run=True,
        command_log_path=args.command_log,
    ))

    frame_count = 0
    started = time.perf_counter()

    print(json.dumps({
        "event": "runtime_started",
        "mapping_dir": str(args.mapping_dir),
        "reference_count": len(localizer.references),
        "frame_stride": args.frame_stride,
        "resize_mode": args.resize_mode,
        "coordinate_convention": {
            "vertical_axis": "-Y-up",
            "navigation_plane": "X/Z",
            "position_mapping": "x_m=position_xyz[0], y_m=position_xyz[2]",
        },
        "dry_run": True,
        "command_log": str(args.command_log) if args.command_log else None,
        "live_map_dir": str(args.live_map_dir),
    }), flush=True)

    try:
        while args.max_frames == 0 or frame_count < args.max_frames:
            ok, frame = capture.read()
            if not ok:
                print(json.dumps({"event": "camera_frame_unavailable", "frame": frame_count}), flush=True)
                break

            if frame_count == 0:
                print(json.dumps({
                    "event": "rtsp_connected",
                    "url": args.url,
                    "frame_resolution": [int(frame.shape[1]), int(frame.shape[0])],
                }), flush=True)

            result = localizer.localize_frame(
                frame,
                query_id=f"camera_{frame_count:06d}",
                resize_mode=args.resize_mode,
            )
            state = manager.update(result)

            if dynamic_goal and not planned_once and state.pose is not None and state.pose.accepted:
                assert state.pose.position_xyz is not None
                start_x, start_y = reconstruction_xyz_to_navigation_xy(state.pose.position_xyz)
                try:
                    planned = plan_path(
                        args.map_dir,
                        start_x,
                        start_y,
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
                    astar_status = {
                        "status": "planned",
                        "waypoint_count": len(waypoints),
                        "path_length_m": planned["path_length_m"],
                        "start": planned["start"],
                        "goal": planned["goal"],
                    }
                    state = manager.update(result)
                    print(json.dumps({"event": "astar_planned", **astar_status}), flush=True)
                except Exception as exc:  # noqa: BLE001 - runtime must stop safely on planner errors.
                    planned_once = True
                    astar_status = {"status": "failed", "error": str(exc), "waypoint_count": 0}
                    planner_failed = True
                    state.mode = "LOCALIZATION_LOST"
                    state.reason = "planner_failed"
                    state.command = TwistCommand(0.0, 0.0, "safety_stop")
                    print(json.dumps({"event": "astar_failed", **astar_status}), flush=True)

            pose = state.pose
            viewer_state.update(
                position_xyz=pose.position_xyz if pose and pose.accepted else None,
                yaw_deg=pose.yaw_deg if pose and pose.accepted else None,
                confidence=pose.confidence if pose else 0.0,
                localization_status=result.get("status", "unknown"),
                mode=state.mode,
                path_xz=manager.waypoints,
            )

            if planner_failed:
                state.mode = "LOCALIZATION_LOST"
                state.reason = "planner_failed"
                state.command = TwistCommand(0.0, 0.0, "safety_stop")

            if state.mode == "LOCALIZATION_LOST" or state.command.status == "safety_stop":
                adapter.stop()
            else:
                adapter.send(state.command)

            elapsed = max(time.perf_counter() - started, 1e-6)
            fps = (frame_count + 1) / elapsed
            print(
                json.dumps(
                    localization_summary(
                        frame_count,
                        frame,
                        result,
                        state.mode,
                        state.reason,
                        state.command.status,
                        fps,
                        astar_status,
                    )
                ),
                flush=True,
            )

            frame_count += 1
    finally:
        adapter.stop()
        capture.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
