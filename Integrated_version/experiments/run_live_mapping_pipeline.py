#!/usr/bin/env python3
"""Run phone capture and periodic LingBot-MAP processing concurrently.

This is a practical online-mapping demo. Capture keeps writing frames while a
background worker processes a growing prefix of the session. The current
LingBot wrapper is batch-oriented, so each update reuses all frames captured so
far; the interface is deliberately separated so the worker can later be
replaced by a stateful streaming model without changing the camera side.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from demo_storage import TEMP_ROOT, finish_session, new_session


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SESSION_ROOT = TEMP_ROOT
DEFAULT_MODEL = ROOT / "models/lingbot-map.pt"


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def count_frames(frames_dir: Path) -> int:
    return sum(1 for path in frames_dir.glob("*.jpg") if path.is_file())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Phone MJPEG/RTSP/video URL")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT)
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--managed-by-server", action="store_true", help="Storage decisions are handled by the demo server")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--batch-frames", type=int, default=30, help="Minimum frames before first mapping update")
    parser.add_argument("--process-every", type=int, default=30, help="New frames between mapping updates")
    parser.add_argument("--max-frames", type=int, default=0, help="0 means run until Ctrl+C")
    parser.add_argument("--warmup-frames", type=int, default=10)
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--rotate", choices=("none", "cw90", "ccw90", "180"), default="none")
    parser.add_argument("--image-size", type=int, default=518)
    parser.add_argument("--downsample-factor", type=int, default=8)
    parser.add_argument("--use-sdpa", action="store_true")
    parser.add_argument("--camera-num-iterations", type=int, default=1)
    parser.add_argument("--sample-stride", type=int, default=8)
    parser.add_argument("--conf-threshold", type=float, default=1.5)
    parser.add_argument("--scene-max-points", type=int, default=45000)
    parser.add_argument("--with-tsdf-mesh", action="store_true", help="Fuse LingBot depth into a TSDF triangle mesh after each mapping update.")
    parser.add_argument("--tsdf-voxel-length", type=float, default=0.035)
    parser.add_argument("--tsdf-sdf-trunc", type=float, default=0.12)
    parser.add_argument("--tsdf-frame-stride", type=int, default=1)
    parser.add_argument("--with-mesh-navigation", action="store_true", help="Build navigation map from TSDF mesh output.")
    parser.add_argument("--mesh-nav-resolution", type=float, default=0.05)
    parser.add_argument("--mesh-nav-robot-radius", type=float, default=0.12)
    parser.add_argument("--with-derived-map", action="store_true", help="Also run the slower classified/2D replay pipeline.")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    if args.fps <= 0 or args.batch_frames < 1 or args.process_every < 1:
        parser.error("fps, batch-frames, and process-every must be positive")
    if args.max_frames < 0 or args.warmup_frames < 0:
        parser.error("max-frames and warmup-frames cannot be negative")
    if not args.model_path.is_file():
        parser.error(f"model checkpoint not found: {args.model_path}")
    return args


class LivePipeline:
    def __init__(self, args: argparse.Namespace, session_dir: Path):
        self.args = args
        self.session_dir = session_dir
        self.frames_dir = session_dir / "frames"
        self.mapping_dir = session_dir / "mapping" / "latest"
        self.replay_dir = session_dir / "online_replay" / "latest"
        self.scene_json = session_dir / "live_scene.json"
        self.mesh_json = session_dir / "live_mesh.json"
        self.mesh_navigation_dir = session_dir / "mesh_navigation" / "latest"
        self.status_path = session_dir / "pipeline_status.json"
        self.log_path = session_dir / "pipeline.log"
        self.stop_event = threading.Event()
        self.frame_event = threading.Event()
        self.state_lock = threading.Lock()
        self.status = {
            "schema_version": 1,
            "state": "STARTING",
            "url": args.url,
            "session_dir": str(session_dir.resolve()),
            "frames_captured": 0,
            "frames_processed": 0,
            "updates_completed": 0,
            "scene_url": "/api/live/scene",
            "mesh_url": "/api/live/mesh",
            "mesh_navigation_dir": str((session_dir / "mesh_navigation" / "latest").resolve()),
            "last_error": None,
            "started_at_unix": time.time(),
        }
        self.log_handle = self.log_path.open("a", encoding="utf-8")

    def update_status(self, **values) -> None:
        with self.state_lock:
            self.status.update(values)
            snapshot = dict(self.status)
        atomic_json(self.status_path, snapshot)

    def log(self, message: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        print(line, flush=True)
        self.log_handle.write(line + "\n")
        self.log_handle.flush()

    def rotate(self, frame):
        return {
            "none": lambda: frame,
            "cw90": lambda: cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE),
            "ccw90": lambda: cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE),
            "180": lambda: cv2.rotate(frame, cv2.ROTATE_180),
        }[self.args.rotate]()

    def capture_loop(self) -> None:
        cap = cv2.VideoCapture(self.args.url, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,
        ])
        if not cap.isOpened():
            self.update_status(state="ERROR", last_error=f"Unable to open stream: {self.args.url}")
            self.stop_event.set()
            return
        manifest = {
            "schema_version": 1,
            "mode": "live_mapping_pipeline",
            "url": self.args.url,
            "session_dir": str(self.session_dir.resolve()),
            "frames_dir": str(self.frames_dir.resolve()),
            "requested_fps": self.args.fps,
            "frames": [],
        }
        atomic_json(self.session_dir / "capture_manifest.json", manifest)
        for _ in range(self.args.warmup_frames):
            cap.read()
        period = 1.0 / self.args.fps
        next_save = time.perf_counter()
        saved = 0
        read_count = 0
        try:
            while not self.stop_event.is_set() and (self.args.max_frames == 0 or saved < self.args.max_frames):
                ok, frame = cap.read()
                read_count += 1
                if not ok or frame is None:
                    self.log("stream read failed; stopping capture")
                    break
                now = time.perf_counter()
                if now < next_save:
                    continue
                frame = self.rotate(frame)
                path = self.frames_dir / f"{saved:06d}.jpg"
                if not cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.args.jpeg_quality]):
                    raise OSError(f"failed to write {path}")
                manifest["frames"].append({"index": saved, "file": str(path.relative_to(self.session_dir)), "timestamp_unix": time.time()})
                saved += 1
                self.update_status(frames_captured=saved)
                atomic_json(self.session_dir / "capture_manifest.json", manifest)
                self.frame_event.set()
                next_save += period
                if now - next_save > period:
                    next_save = now + period
                if self.args.preview:
                    cv2.imshow("Live Mapping Capture", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self.stop_event.set()
                        break
        finally:
            cap.release()
            if self.args.preview:
                cv2.destroyAllWindows()
            manifest["ended_at_unix"] = time.time()
            manifest["saved_frames"] = saved
            manifest["read_frames"] = read_count
            atomic_json(self.session_dir / "capture_manifest.json", manifest)
            self.frame_event.set()

    def run_command(self, command: list[str], label: str) -> None:
        self.log(label + ": " + " ".join(command))
        with self.log_path.open("a", encoding="utf-8") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, start_new_session=True)
        if result.returncode != 0:
            raise RuntimeError(f"{label} failed with exit code {result.returncode}")

    def process_once(self, frame_count: int) -> None:
        self.update_status(state="MAPPING", frames_processed=frame_count, last_error=None)
        self.mapping_dir.mkdir(parents=True, exist_ok=True)
        ply_path = self.mapping_dir / "rebuilt_colored_map.ply"
        mapping_cmd = [
            sys.executable, str(SCRIPT_DIR / "run_lingbot_mapping.py"),
            "--image-folder", str(self.frames_dir), "--first-k", str(frame_count),
            "--model-path", str(self.args.model_path), "--output-dir", str(self.mapping_dir),
            "--camera-num-iterations", str(self.args.camera_num_iterations),
            "--image-size", str(self.args.image_size),
            "--downsample-factor", str(self.args.downsample_factor),
            "--output-ply", str(ply_path),
        ]
        if self.args.use_sdpa:
            mapping_cmd.append("--use-sdpa")
        self.run_command(mapping_cmd, "mapping")
        self.update_status(state="EXPORTING_SCENE", frames_processed=frame_count)
        scene_cmd = [
            sys.executable, str(SCRIPT_DIR / "export_live_scene_json.py"),
            "--ply", str(ply_path), "--output", str(self.scene_json),
            "--max-points", str(self.args.scene_max_points),
            "--frame-count", str(frame_count),
            "--update-index", str(self.status["updates_completed"] + 1),
        ]
        self.run_command(scene_cmd, "scene snapshot")
        if self.args.with_tsdf_mesh:
            self.update_status(state="FUSING_TSDF", frames_processed=frame_count)
            mesh_cmd = [
                sys.executable, str(SCRIPT_DIR / "build_tsdf_mesh.py"),
                "--archive", str(self.mapping_dir / "predictions.npz"),
                "--output-mesh", str(self.mapping_dir / "tsdf_mesh.ply"),
                "--preview-json", str(self.mesh_json),
                "--max-frames", str(frame_count),
                "--voxel-length", str(self.args.tsdf_voxel_length),
                "--sdf-trunc", str(self.args.tsdf_sdf_trunc),
                "--frame-stride", str(self.args.tsdf_frame_stride),
                "--update-index", str(self.status["updates_completed"] + 1),
            ]
            self.run_command(mesh_cmd, "TSDF mesh")
            if self.args.with_mesh_navigation:
                self.update_status(state="BUILDING_MESH_NAVIGATION", frames_processed=frame_count)
                self.mesh_navigation_dir.mkdir(parents=True, exist_ok=True)
                nav_cmd = [
                    sys.executable, str(ROOT / "Integrated_version" / "map" / "build_mesh_navigation_map.py"),
                    "--mesh", str(self.mapping_dir / "tsdf_mesh.ply"),
                    "--output-dir", str(self.mesh_navigation_dir),
                    "--vertical-axis=-y",
                    "--resolution-m", str(self.args.mesh_nav_resolution),
                    "--robot-radius-m", str(self.args.mesh_nav_robot_radius),
                ]
                self.run_command(nav_cmd, "mesh navigation map")
        if self.args.with_derived_map:
            self.update_status(state="INTEGRATING", frames_processed=frame_count)
            self.replay_dir.mkdir(parents=True, exist_ok=True)
            replay_cmd = [
                sys.executable, str(SCRIPT_DIR / "run_lingbot_online_replay.py"),
                "--archive", str(self.mapping_dir / "predictions.npz"),
                "--output-dir", str(self.replay_dir), "--max-frames", str(frame_count),
                "--sample-stride", str(self.args.sample_stride),
                "--conf-threshold", str(self.args.conf_threshold), "--write-every", str(max(1, min(5, frame_count))),
            ]
            self.run_command(replay_cmd, "incremental map")
            viewer_cmd = [
                sys.executable, str(SCRIPT_DIR / "export_online_replay_3d_viewer.py"),
                "--replay-dir", str(self.replay_dir), "--max-points-per-frame", "12000",
            ]
            self.run_command(viewer_cmd, "3D viewer")
        self.update_status(state="READY", frames_processed=frame_count, updates_completed=self.status["updates_completed"] + 1, last_update_unix=time.time())

    def process_loop(self) -> None:
        processed = 0
        while not self.stop_event.is_set():
            self.frame_event.wait(1.0)
            self.frame_event.clear()
            available = count_frames(self.frames_dir)
            target = self.args.batch_frames if processed == 0 else processed + self.args.process_every
            if available < target:
                continue
            try:
                self.process_once(target)
                processed = target
            except Exception as exc:
                self.log(f"ERROR: {exc}")
                self.update_status(state="ERROR", last_error=str(exc), frames_processed=processed)
                processed = target

    def run(self) -> None:
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.update_status(state="CAPTURING")
        capture = threading.Thread(target=self.capture_loop, name="capture", daemon=True)
        processor = threading.Thread(target=self.process_loop, name="processor", daemon=True)
        capture.start()
        processor.start()
        try:
            while capture.is_alive() and not self.stop_event.is_set():
                time.sleep(0.5)
            if self.args.max_frames > 0 and not self.stop_event.is_set() and count_frames(self.frames_dir) >= self.args.batch_frames:
                deadline = time.time() + 900.0
                while processor.is_alive() and time.time() < deadline:
                    with self.state_lock:
                        completed = self.status["updates_completed"]
                        state = self.status["state"]
                    if completed >= 1 or state == "ERROR":
                        break
                    self.frame_event.set()
                    time.sleep(0.5)
        except KeyboardInterrupt:
            self.log("Ctrl+C received")
        finally:
            previous_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
            self.stop_event.set()
            self.frame_event.set()
            # Storage must not move or disappear while a worker still writes it.
            capture.join()
            processor.join()

            with self.state_lock:
                failed = self.status["state"] == "ERROR"

            self.update_status(state="ERROR" if failed else "STOPPED", ended_at_unix=time.time())
            self.log_handle.close()
            signal.signal(signal.SIGINT, previous_sigint)


def main() -> int:
    args = parse_args()
    session_name = args.session_name or datetime.now().strftime("live_%Y%m%d_%H%M%S")
    if Path(session_name).name != session_name or session_name in {".", ".."}:
        raise SystemExit("Invalid session name")
    if args.managed_by_server:
        session_dir = args.session_root.resolve() / session_name
        session_dir.mkdir(parents=True, exist_ok=False)
    else:
        session_dir = new_session(session_name, args.session_root.resolve())
    print(f"Session: {session_dir}", flush=True)
    try:
        LivePipeline(args, session_dir).run()
    finally:
        if not args.managed_by_server:
            finish_session(session_dir, ROOT / "outputs/live_sessions", args.session_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())