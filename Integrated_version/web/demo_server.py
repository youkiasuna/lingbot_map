#!/usr/bin/env python3
"""Interactive demo for prepared mapping, localization, A* and simulation."""
from __future__ import annotations
import argparse, json, math, shutil, signal, socket, subprocess, sys, threading, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
INTEGRATED = ROOT / "Integrated_version"
sys.path.insert(0, str(INTEGRATED))
sys.path.insert(0, str(INTEGRATED / "planner"))
from experiments.orb_keyframe_localizer import OrbKeyframeLocalizer, result_to_pose
from localization.localizer_interface import FilePosePublisher, PoseSample
from planner.grid_navigation import load_grid_map, plan_path
from experiments.demo_storage import new_session, save_session, discard_session

ROBOT_COMMAND_MAP = {
    "forward": "F",
    "backward": "B",
    "left": "L",
    "right": "R",
    "stop": "S",
}


def send_robot_command(ip: str, port: int, command: str) -> str:
    """Send a single-letter motion command to the ESP32 car over TCP.

    Mirrors car/car/pc_controller.py and car/car/web_controller.py so the
    same firmware protocol (newline-terminated single letter) is reused
    instead of inventing a new one.
    """
    payload = command.encode("utf-8") + b"\n"
    with socket.create_connection((ip, port), timeout=2) as sock:
        sock.sendall(payload)
        return sock.recv(1024).decode("utf-8", errors="ignore").strip()


class DemoHandler(BaseHTTPRequestHandler):
    map_dir: Path
    scene_dir: Path
    query_dir: Path
    result_dir: Path
    min_confidence: float
    pose_offset_x: float
    pose_offset_y: float
    snap_localization_to_free: bool
    live_root: Path
    live_url = ""
    live_process = None
    live_lock = threading.RLock()
    robot_ip = "192.168.4.1"
    robot_port = 8888
    robot_lock = threading.RLock()
    robot_last_error = None
    localizer = None
    lock = threading.RLock()
    stop_event = threading.Event()
    navigation_thread = None
    state = {"mode": "simulation", "system_state": "READY",
             "mapping": {"state": "MAP_READY", "source": "prepared_scene"},
             "localization": {"state": "WAITING"},
             "robot": {"state": "SIMULATOR_READY", "connected": False}}

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path, content_type):
        if not path.is_file():
            self.send_json({"status": "error", "message": "File not found: " + str(path)}, HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 32768:
            raise ValueError("Request body is too large.")
        return json.loads(self.rfile.read(length).decode()) if length else {}

    @classmethod
    def set_state(cls, **values):
        with cls.lock:
            cls.state.update(values)


    def live_status(cls):
        status_path = cls.live_root / "current/pipeline_status.json"
        with cls.live_lock:
            process = cls.live_process
            process_running = process is not None and process.poll() is None
            url = cls.live_url
        if status_path.is_file():
            try:
                payload = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {"state": "ERROR", "last_error": "Invalid pipeline status file."}
        else:
            payload = {"state": "IDLE", "frames_captured": 0, "frames_processed": 0, "updates_completed": 0}
        payload["url"] = payload.get("url") or url
        payload["process_running"] = process_running
        payload["viewer_url"] = "/live-3d"
        payload["mesh_viewer_url"] = "/live-mesh"
        return payload


    def proxy_video(self):
        cls = type(self)
        with cls.live_lock:
            url = cls.live_url
        if not url or not url.startswith(("http://", "https://")):
            self.send_json({"status": "error", "message": "尚未連線手機串流，或串流不是 http(s) MJPEG 網址。"}, HTTPStatus.NOT_FOUND)
            return
        request = Request(url, headers={
            "User-Agent": "lingbot-map-demo/1.0",
            "Accept": "multipart/x-mixed-replace,*/*",
        })
        try:
            with urlopen(request, timeout=8) as upstream:
                content_type = upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=--frame")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = upstream.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (OSError, TimeoutError) as exc:
            try:
                self.send_json({"status": "error", "message": f"無法讀取手機影像串流：{exc}"}, HTTPStatus.BAD_GATEWAY)
            except OSError:
                return

    def stop_live_process(cls):
        with cls.live_lock:
            process = cls.live_process
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)


    def reset_live_storage(cls):
        current = cls.live_root / "current"
        if current.exists():
            raise ValueError("請先保存或捨棄本次 Demo，再開始新的掃描。")
        current.parent.mkdir(parents=True, exist_ok=True)

    def handle_live_connect(self, body):
        url = str(body.get("url", "")).strip()
        if not url.startswith(("rtsp://", "http://", "https://")):
            raise ValueError("手機串流 URL 必須使用 rtsp:// 或 http://")
        parsed = urlsplit(url)
        if not parsed.hostname:
            raise ValueError("手機串流 URL 缺少主機位址。")
        port = parsed.port or (554 if parsed.scheme == "rtsp" else 443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((parsed.hostname, port), timeout=2):
                pass
        except OSError as exc:
            raise ValueError(f"手機串流目前無法連線：{exc}") from exc
        cls = type(self)
        with cls.live_lock:
            if cls.live_process is not None and cls.live_process.poll() is None:
                raise ValueError("即時建模正在執行，請先停止目前工作階段。")
            cls.live_url = url
        self.send_json({"status": "ok", "live": self.live_status()})

    def handle_live_start(self):
        cls = type(self)
        with cls.live_lock:
            url = cls.live_url
            running = cls.live_process is not None and cls.live_process.poll() is None
        if running:
            raise ValueError("即時建模已經在執行。")
        if not url:
            raise ValueError("請先輸入並連線手機串流 URL。")
        self.reset_live_storage()
        script = INTEGRATED / "experiments/run_live_mapping_pipeline.py"
        command = [
            sys.executable, str(script), "--url", url,
            "--session-root", str(self.live_root), "--session-name", "current",
            "--fps", "5", "--batch-frames", "30", "--process-every", "30",
            "--max-frames", "0", "--camera-num-iterations", "1", "--use-sdpa",
            "--with-tsdf-mesh", "--tsdf-frame-stride", "2",
            "--with-mesh-navigation",
            "--managed-by-server",
        ]
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with cls.live_lock:
            cls.live_process = process
        self.send_json({"status": "ok", "live": self.live_status()})

    def handle_live_stop(self):
        self.stop_live_process()
        self.send_json({"status": "ok", "live": self.live_status()})

    def handle_live_reset(self):
        raise ValueError("請使用保存或捨棄 Demo，避免直接覆寫尚未確認的資料。")

    def handle_storage(self, body):
        cls = type(self)
        if cls.live_process is not None and cls.live_process.poll() is None:
            raise ValueError("請先停止掃描，並等待建圖完成。")
        if cls.navigation_thread is not None and cls.navigation_thread.is_alive():
            raise ValueError("請先停止導航模擬。")
        action = body.get("action")
        if action not in {"save", "discard"}:
            raise ValueError("Unknown storage action")
        old = cls.session_dir
        # Prepare the replacement before committing the storage decision.
        replacement = new_session("web_demo")
        try:
            prepare_demo_map(cls.source_map_dir, replacement / "map")
            saved = save_session(old, ROOT / "outputs/saved_demos") if action == "save" else None
            if action == "discard":
                discard_session(old)
        except Exception:
            discard_session(replacement)
            raise
        configure_workspace(cls, replacement)
        cls.live_process = None
        cls.state = {"mode": "simulation", "system_state": "READY", "localization": {"state": "WAITING"}}
        self.send_json({"status": "ok", "saved": str(saved) if saved else None, "session": str(replacement)})

    def do_GET(self):
        request = urlparse(self.path)
        path = request.path
        if path == "/api/storage":
            self.send_json({"status": "ok", "session": str(self.session_dir), "state": "temporary"})
            return
        if path == "/api/live/status":
            self.send_json({"status": "ok", "live": self.live_status()})
            return
        if path == "/api/live/scene":
            self.send_file(self.live_root / "current/live_scene.json", "application/json; charset=utf-8")
            return
        if path == "/api/live/mesh":
            self.send_file(self.live_root / "current/live_mesh.json", "application/json; charset=utf-8")
            return
        if path == "/api/live/mesh.ply":
            self.send_file(self.live_root / "current/mapping/latest/tsdf_mesh.ply", "application/octet-stream")
            return
        if path == "/api/live/nav-map":
            self.send_file(self.live_root / "current/mesh_navigation/latest/map.json", "application/json; charset=utf-8")
            return
        if path == "/api/live/nav-map.pgm":
            self.send_file(self.live_root / "current/mesh_navigation/latest/map.pgm", "application/octet-stream")
            return
        if path == "/video-proxy":
            self.proxy_video()
            return
        if path == "/api/robot/status":
            with self.robot_lock:
                self.send_json({"status": "ok", "robot": {
                    "ip": self.robot_ip, "port": self.robot_port,
                    "last_error": self.robot_last_error,
                }})
            return
        if path == "/live-3d":
            self.send_file(INTEGRATED / "web/demo/live_scene_viewer.html", "text/html; charset=utf-8")
            return
        if path == "/live-mesh":
            self.send_file(INTEGRATED / "web/demo/live_mesh_viewer.html", "text/html; charset=utf-8")
            return
        if path == "/3d-classified":
            self.send_file(INTEGRATED / "web/demo/classified_viewer.html", "text/html; charset=utf-8")
            return
        if path == "/3d-ply":
            source = parse_qs(request.query).get("source", ["clean"])[0]
            source_dir = ROOT / "outputs/maps/20260818_navigation_rebuilt" if source == "rebuilt" else self.map_dir
            ply_files = {"floor": source_dir / "floor.ply", "obstacle": source_dir / "obstacle.ply", "unknown": source_dir / "unknown.ply"}
            name = parse_qs(request.query).get("name", ["floor"])[0]
            self.send_file(ply_files.get(name, ply_files["floor"]), "application/octet-stream")
            return
        if path == "/3d-models":
            self.send_file(INTEGRATED / "web/demo/models.html", "text/html; charset=utf-8")
            return
        if path == "/":
            self.send_file(INTEGRATED / "web/demo/index.html", "text/html; charset=utf-8")
        elif path == "/3d-viewer":
            viewers = {
                "clean": ROOT / "outputs/maps/20260818_clean/20260818_clean_height_viewer.html",
                "calibrated": ROOT / "outputs/maps/20260818_calibrated/20260818_floor_calibrated_viewer.html",
                "calibrated_y": ROOT / "outputs/maps/20260818_calibrated_y/20260818_floor_calibrated_viewer.html",
                "calibrated_z": ROOT / "outputs/maps/20260818_calibrated_z/20260818_floor_calibrated_viewer.html",
                "navigation": ROOT / "outputs/maps/20260818_navigation/20260818_navigation_viewer.html",
                "rebuilt": ROOT / "outputs/archive/scene_20260818_rebuild/visualization/auto_floor_viewer.html",
                "initial": ROOT / "outputs/archive/scene_20260818_initial/20260818_auto_floor_viewer.html",
            }
            key = parse_qs(request.query).get("model", ["rebuilt"])[0]
            self.send_file(viewers.get(key, viewers["clean"]), "text/html; charset=utf-8")
        elif path == "/map.pgm":
            self.send_file(self.map_dir / "map.pgm", "application/octet-stream")
        elif path == "/api/map":
            metadata = json.loads((self.map_dir / "map.json").read_text())
            metadata["map_url"] = "/map.pgm"
            metadata["viewer_3d_url"] = "/3d-viewer"
            self.send_json({"status": "ok", "map": metadata})
        elif path == "/api/queries":
            names = sorted(p.name for p in self.query_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
            self.send_json({"status": "ok", "queries": names})
        elif path == "/api/state":
            with self.lock:
                payload = dict(self.state)
            for key, name in (("pose", "current_pose.json"), ("path", "planned_path.json"), ("navigation", "navigation_state.json")):
                p = self.map_dir / name
                payload[key] = json.loads(p.read_text()) if p.is_file() else None
            self.send_json({"status": "ok", "state": payload})
        else:
            self.send_json({"status": "error", "message": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        with self.lock:
            self.dispatch_post()

    def dispatch_post(self):
        try:
            body = self.read_body()
            path = urlparse(self.path).path
            if path == "/api/storage":
                self.handle_storage(body)
            elif path == "/api/live/connect":
                self.handle_live_connect(body)
            elif path == "/api/live/start":
                self.handle_live_start()
            elif path == "/api/live/stop":
                self.handle_live_stop()
            elif path == "/api/live/reset":
                self.handle_live_reset()
            elif path == "/api/move":
                self.handle_move(body)
            elif path == "/api/robot/configure":
                self.handle_robot_configure(body)
            elif path == "/api/mapping/start":
                self.handle_mapping()
            elif path == "/api/localization/run":
                self.handle_localization(body)
            elif path == "/api/plan":
                self.handle_plan(body)
            elif path == "/api/navigation/start":
                self.handle_start()
            elif path == "/api/navigation/stop":
                self.handle_stop()
            else:
                self.send_json({"status": "error", "message": "Not found"}, HTTPStatus.NOT_FOUND)
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            self.send_json({"status": "error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_move(self, body):
        """Manual driving: forward the direction straight to the ESP32 over TCP.

        This does not touch localization, planning, or navigation state —
        it is the same "send one letter, get one letter back" contract
        car/car/pc_controller.py already uses, just reachable from the
        browser through this server instead of a standalone script.
        """
        direction = str(body.get("command", ""))
        letter = ROBOT_COMMAND_MAP.get(direction)
        if letter is None:
            raise ValueError(f"Unknown command: {direction!r}. Use one of {sorted(ROBOT_COMMAND_MAP)}.")
        cls = type(self)
        with cls.robot_lock:
            ip, port = cls.robot_ip, cls.robot_port
        try:
            response = send_robot_command(ip, port, letter)
            cls.robot_last_error = None
        except OSError as exc:
            cls.robot_last_error = str(exc)
            raise ValueError(f"無法連線車體 {ip}:{port}：{exc}") from exc
        self.send_json({"status": "ok", "command": direction, "letter": letter, "robot_response": response})

    def handle_robot_configure(self, body):
        """Let the browser point at a different ESP32 without restarting the server."""
        cls = type(self)
        with cls.robot_lock:
            if "ip" in body:
                cls.robot_ip = str(body["ip"])
            if "port" in body:
                cls.robot_port = int(body["port"])
            ip, port = cls.robot_ip, cls.robot_port
        self.send_json({"status": "ok", "robot": {"ip": ip, "port": port}})

    def handle_mapping(self):
        needed = [self.map_dir / "map.pgm", self.map_dir / "map.json", self.scene_dir / "mapping/predictions.npz"]
        missing = [str(p) for p in needed if not p.is_file()]
        if missing:
            self.send_json({"status": "error", "message": "Map package incomplete.", "missing": missing}, HTTPStatus.CONFLICT)
            return
        self.set_state(system_state="MAP_READY", mapping={"state": "MAP_READY", "source": "scene_20260818"})
        self.send_json({"status": "ok", "mapping": self.state["mapping"]})

    def handle_localization(self, body):
        name = str(body.get("query", ""))
        candidate = self.query_dir / name
        if candidate.parent != self.query_dir or candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"} or not candidate.is_file():
            raise ValueError("Unknown query image.")
        query = candidate.resolve()
        if self.localizer is None:
            self.localizer = OrbKeyframeLocalizer(self.scene_dir / "mapping")
        self.set_state(system_state="LOCALIZING", localization={"state": "RUNNING", "query": query.name})
        for stale_file in ("planned_path.json", "navigation_state.json"):
            path = self.map_dir / stale_file
            if path.exists():
                path.unlink()
        result = self.localizer.localize(query)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        output = self.result_dir / (query.stem + "_demo_result.json")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        pose = result_to_pose(result, self.min_confidence)
        pose = PoseSample(pose.x_m + self.pose_offset_x, pose.y_m + self.pose_offset_y, pose.yaw_deg, pose.timestamp_unix, pose.source, pose.confidence, pose.status, pose.inlier_count, pose.reprojection_error_px, pose.frame_id)
        if self.snap_localization_to_free and pose.status == "ok":
            grid = load_grid_map(self.map_dir)
            start_px = grid.world_to_pixel(pose.x_m, pose.y_m)
            candidates = []
            for py in range(grid.height):
                for px in range(grid.width):
                    if grid.is_traversable(px, py):
                        candidates.append((px, py))
            if candidates:
                px, py = min(candidates, key=lambda cell: (cell[0] - start_px[0]) ** 2 + (cell[1] - start_px[1]) ** 2)
                x_m, y_m = grid.pixel_to_world(px, py)
                pose = PoseSample(x_m, y_m, pose.yaw_deg, pose.timestamp_unix, "demo_simulator_snapped", pose.confidence, pose.status, pose.inlier_count, pose.reprojection_error_px, pose.frame_id)
        FilePosePublisher(self.map_dir / "current_pose.json").publish(pose)
        best = result.get("best") or {}
        info = {"state": pose.status.upper(), "query": query.name,
                "confidence": best.get("confidence", 0.0),
                "inlier_count": best.get("inlier_count", 0),
                "reprojection_error_px": best.get("reprojection_error_px"),
                "latency_ms": result.get("latency_ms"), "result_json": str(output)}
        self.set_state(system_state="LOCALIZED" if pose.status == "ok" else "LOCALIZATION_REJECTED", localization=info)
        self.send_json({"status": "ok", "result": result, "pose": pose.to_payload()})

    def handle_plan(self, body):
        goal_x = float(body["goal_x_m"])
        goal_y = float(body["goal_y_m"])
        pose = json.loads((self.map_dir / "current_pose.json").read_text())
        if pose.get("status") != "ok" or float(pose.get("confidence", 0)) < self.min_confidence:
            raise ValueError("Localization has not passed the confidence gate.")
        result = plan_path(self.map_dir, float(pose["x_m"]), float(pose["y_m"]),
                           goal_x, goal_y, False, True, 0.25, 1.0)
        (self.map_dir / "planned_path.json").write_text(json.dumps(result, indent=2) + "\n")
        navigation_path = self.map_dir / "navigation_state.json"
        if navigation_path.exists():
            navigation_path.unlink()
        self.set_state(system_state="PATH_PLANNED")
        self.send_json({"status": "ok", "path": result})

    def handle_start(self):
        path = self.map_dir / "planned_path.json"
        if not path.is_file():
            raise ValueError("Plan a path first.")
        if self.navigation_thread and self.navigation_thread.is_alive():
            raise ValueError("Simulation is already running.")
        self.stop_event.clear()
        type(self).navigation_thread = threading.Thread(target=self.simulate, args=(json.loads(path.read_text()),), daemon=True)
        type(self).navigation_thread.start()
        self.send_json({"status": "ok", "navigation": {"state": "NAVIGATING", "mode": "simulation"}})

    def simulate(self, path):
        points = path.get("waypoints", [])
        if len(points) < 2:
            self.set_state(system_state="NAVIGATION_FAILED")
            return
        for point in points:
            if self.stop_event.is_set():
                return
            pose_path = self.map_dir / "current_pose.json"
            pose = json.loads(pose_path.read_text()) if pose_path.is_file() else point
            x0, y0 = float(pose.get("x_m", point["x_m"])), float(pose.get("y_m", point["y_m"]))
            x1, y1 = float(point["x_m"]), float(point["y_m"])
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.04))
            for step in range(1, steps + 1):
                if self.stop_event.wait(0.08):
                    return
                ratio = step / steps
                x, y = x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio
                yaw = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360
                sample = PoseSample(x, y, yaw, time.time(), "demo_simulator", 1.0)
                FilePosePublisher(pose_path).publish(sample)
        (self.map_dir / "navigation_state.json").write_text(json.dumps({"state": "ARRIVED", "updated_at_unix": time.time()}, indent=2) + "\n")
        self.set_state(system_state="ARRIVED")

    def handle_stop(self):
        self.stop_event.set()
        (self.map_dir / "navigation_state.json").write_text(json.dumps({"state": "STOP", "updated_at_unix": time.time(), "reason": "user_requested"}, indent=2) + "\n")
        self.set_state(system_state="STOPPED")
        self.send_json({"status": "ok", "navigation": {"state": "STOP"}})

def prepare_demo_map(source: Path, target: Path):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        "current_pose.json", "planned_path.json", "navigation_state.json"))


def configure_workspace(handler, session):
    handler.session_dir = session
    handler.map_dir = session / "map"
    handler.live_root = session / "live"
    handler.result_dir = session / "results"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-dir", type=Path, default=ROOT / "outputs/maps/20260818_navigation_rebuilt_voxel")
    parser.add_argument("--scene-dir", type=Path, default=ROOT / "outputs/scenes/scene_20260818")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18110)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--pose-offset-x", type=float, default=-1.53, help="Demo translation from LingBot X/Z to navigation-map X/Y.")
    parser.add_argument("--pose-offset-y", type=float, default=0.0, help="Demo translation from LingBot X/Z to navigation-map X/Y.")
    parser.add_argument("--snap-localization-to-free", action="store_true", help="Simulation only: snap localized pose to nearest traversable map cell.")
    parser.add_argument("--robot-ip", default="192.168.4.1", help="ESP32 car IP address for manual driving (car/car/esp32_motor_control.ino).")
    parser.add_argument("--robot-port", type=int, default=8888, help="ESP32 car TCP port for manual driving commands.")
    args = parser.parse_args()
    DemoHandler.source_map_dir, DemoHandler.scene_dir = args.map_dir.resolve(), args.scene_dir.resolve()
    session = new_session("web_demo")
    try:
        prepare_demo_map(DemoHandler.source_map_dir, session / "map")
    except Exception:
        discard_session(session)
        raise
    configure_workspace(DemoHandler, session)
    DemoHandler.query_dir = DemoHandler.scene_dir / "inputs/query_images"
    DemoHandler.min_confidence = args.min_confidence
    DemoHandler.pose_offset_x = args.pose_offset_x
    DemoHandler.pose_offset_y = args.pose_offset_y
    DemoHandler.snap_localization_to_free = args.snap_localization_to_free
    DemoHandler.robot_ip = args.robot_ip
    DemoHandler.robot_port = args.robot_port
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print("Demo UI: http://%s:%s" % (args.host, args.port), flush=True)
    print(f"Temporary results: {session}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        DemoHandler.stop_event.set()
        if DemoHandler.live_process is not None and DemoHandler.live_process.poll() is None:
            DemoHandler.live_process.send_signal(signal.SIGINT)
            DemoHandler.live_process.wait()
        server.server_close()
        print(f"Pending storage decision: {DemoHandler.session_dir}", flush=True)

if __name__ == "__main__":
    main()