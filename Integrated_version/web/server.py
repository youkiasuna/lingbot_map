#!/usr/bin/env python3
"""Small browser UI/API for map display, goal selection, and A* planning."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
PLANNER_DIR = INTEGRATED_ROOT / "planner"
if str(PLANNER_DIR) not in sys.path:
    sys.path.insert(0, str(PLANNER_DIR))

from grid_navigation import plan_path


STATIC_DIR = INTEGRATED_ROOT / "web"


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class NavigationHandler(BaseHTTPRequestHandler):
    map_dir: Path
    allow_unknown: bool
    use_obstacle_distance: bool
    safety_radius_m: float
    risk_weight: float

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"status": "error", "message": message}, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self.serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        elif path == "/styles.css":
            self.serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
        elif path == "/map.pgm":
            self.serve_file(self.map_dir / "map.pgm", "application/octet-stream")
        elif path == "/api/map":
            self.handle_get_map()
        elif path == "/api/pose":
            self.handle_get_optional_json("current_pose.json", "pose")
        elif path == "/api/path":
            self.handle_get_optional_json("planned_path.json", "path")
        elif path == "/api/navigation":
            self.handle_get_optional_json("navigation_state.json", "navigation")
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Unknown route: {unquote(path)}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/plan":
            self.handle_plan()
        elif parsed.path == "/api/navigation/start":
            self.handle_navigation_start()
        elif parsed.path == "/api/navigation/stop":
            self.handle_navigation_stop()
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Unknown route: {unquote(parsed.path)}")

    def serve_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, f"File not found: {path.name}")
            return
        data = path.read_bytes()
        guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guessed_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_request_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def handle_get_map(self) -> None:
        metadata = read_json(self.map_dir / "map.json")
        if metadata is None:
            self.send_error_json(HTTPStatus.NOT_FOUND, "map.json not found in map directory.")
            return
        payload = dict(metadata)
        payload["map_url"] = "/map.pgm"
        payload["allow_unknown"] = self.allow_unknown
        self.send_json({"status": "ok", "map": payload})

    def handle_get_optional_json(self, filename: str, key: str) -> None:
        payload = read_json(self.map_dir / filename)
        if payload is None:
            self.send_json({"status": "missing", key: None})
            return
        self.send_json({"status": "ok", key: payload})

    def handle_plan(self) -> None:
        try:
            body = self.read_request_json()
            goal_x = float(body["goal_x_m"])
            goal_y = float(body["goal_y_m"])
            pose = read_json(self.map_dir / "current_pose.json")
            if pose is None:
                self.send_error_json(HTTPStatus.CONFLICT, "current_pose.json is missing. Start the mock or visual localizer first.")
                return
            start_x = float(pose["x_m"])
            start_y = float(pose["y_m"])
            result = plan_path(
                self.map_dir,
                start_x,
                start_y,
                goal_x,
                goal_y,
                self.allow_unknown,
                self.use_obstacle_distance,
                self.safety_radius_m,
                self.risk_weight,
            )
            result["planned_at_unix"] = time.time()
            write_json(self.map_dir / "planned_path.json", result)
            write_json(self.map_dir / "navigation_state.json", {
                "state": "GOAL_SELECTED",
                "updated_at_unix": time.time(),
            })
            self.send_json({"status": "ok", "path": result})
        except (KeyError, TypeError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except FileNotFoundError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))

    def handle_navigation_start(self) -> None:
        path = read_json(self.map_dir / "planned_path.json")
        if path is None:
            self.send_error_json(HTTPStatus.CONFLICT, "No planned_path.json exists. Select a goal first.")
            return
        state = {
            "state": "NAVIGATING",
            "updated_at_unix": time.time(),
            "controller": "not_connected",
            "path_waypoint_count": path.get("waypoint_count", 0),
        }
        write_json(self.map_dir / "navigation_state.json", state)
        self.send_json({"status": "ok", "navigation": state})

    def handle_navigation_stop(self) -> None:
        state = {
            "state": "STOP",
            "updated_at_unix": time.time(),
            "reason": "user_requested",
        }
        write_json(self.map_dir / "navigation_state.json", state)
        self.send_json({"status": "ok", "navigation": state})


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the map localization test UI.")
    parser.add_argument("--map-dir", required=True, type=Path, help="Directory containing map.pgm and map.json")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=18088, help="Bind port")
    parser.add_argument("--allow-unknown", action="store_true", help="Allow A* to plan through unknown map cells")
    parser.add_argument("--use-obstacle-distance", action="store_true", help="Apply obstacle proximity penalty when distance field exists")
    parser.add_argument("--safety-radius-m", type=float, default=0.25, help="Distance under which obstacle proximity is penalized")
    parser.add_argument("--risk-weight", type=float, default=1.0, help="A* cost weight for obstacle proximity")
    args = parser.parse_args()

    if not (args.map_dir / "map.pgm").exists() or not (args.map_dir / "map.json").exists():
        raise SystemExit(f"{args.map_dir} must contain map.pgm and map.json")

    handler = type(
        "ConfiguredNavigationHandler",
        (NavigationHandler,),
        {
            "map_dir": args.map_dir,
            "allow_unknown": args.allow_unknown,
            "use_obstacle_distance": args.use_obstacle_distance,
            "safety_radius_m": args.safety_radius_m,
            "risk_weight": args.risk_weight,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving navigation UI at http://{args.host}:{args.port}")
    print(f"Map directory: {args.map_dir}")
    server.serve_forever()


if __name__ == "__main__":
    main()
