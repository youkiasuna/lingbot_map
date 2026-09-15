#!/usr/bin/env python3
"""Capture frames from a phone/IP-camera stream into a research session."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
from demo_storage import TEMP_ROOT, finish_session, new_session


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION_ROOT = TEMP_ROOT


def make_session_dir(root: Path, name: str | None) -> Path:
    if name:
        return root / name
    stamp = datetime.now().strftime("session_%Y%m%d_%H%M%S")
    return root / stamp


def rotate_frame(frame, mode: str):
    if mode == "none":
        return frame
    if mode == "cw90":
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if mode == "ccw90":
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if mode == "180":
        return cv2.rotate(frame, cv2.ROTATE_180)
    raise ValueError(f"Unknown rotate mode: {mode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="MJPEG/RTSP/video URL, for example http://PHONE_IP:8080/video")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT)
    parser.add_argument("--session-name", default=None, help="Optional fixed session folder name")
    parser.add_argument("--fps", type=float, default=5.0, help="Saved frame rate")
    parser.add_argument("--max-frames", type=int, default=100, help="Stop after saving this many frames; 0 means unlimited")
    parser.add_argument("--warmup-frames", type=int, default=10, help="Read and discard initial unstable frames")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--rotate", choices=("none", "cw90", "ccw90", "180"), default="none")
    parser.add_argument("--preview", action="store_true", help="Show OpenCV preview window; press q to stop")
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps must be positive")
    if args.max_frames < 0 or args.warmup_frames < 0:
        parser.error("--max-frames and --warmup-frames cannot be negative")
    if not 1 <= args.jpeg_quality <= 100:
        parser.error("--jpeg-quality must be 1..100")
    return args


def main() -> int:
    args = parse_args()
    session_dir = new_session(args.session_name or "capture", args.session_root.resolve())
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.url)
    if not cap.isOpened():
        finish_session(session_dir, ROOT / "outputs/live_sessions", args.session_root.resolve())
        raise SystemExit(f"Unable to open stream: {args.url}")

    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)

    manifest = {
        "schema_version": 1,
        "mode": "phone_stream_capture",
        "url": args.url,
        "session_dir": str(session_dir),
        "frames_dir": str(frames_dir),
        "requested_fps": args.fps,
        "max_frames": args.max_frames,
        "warmup_frames": args.warmup_frames,
        "jpeg_quality": args.jpeg_quality,
        "rotate": args.rotate,
        "source_width": source_width,
        "source_height": source_height,
        "source_fps": source_fps,
        "started_at_unix": time.time(),
        "frames": [],
    }
    (session_dir / "capture_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Capturing from {args.url}")
    print(f"Session: {session_dir}")
    print("Press Ctrl+C to stop" + (" or q in preview window" if args.preview else ""))

    for _ in range(args.warmup_frames):
        cap.read()

    saved = 0
    read_count = 0
    period = 1.0 / args.fps
    next_save_time = time.perf_counter()
    started = time.perf_counter()
    try:
        while args.max_frames == 0 or saved < args.max_frames:
            ok, frame = cap.read()
            read_count += 1
            if not ok or frame is None:
                print("Stream ended or frame read failed.")
                break
            frame = rotate_frame(frame, args.rotate)
            now = time.perf_counter()
            if now < next_save_time:
                if args.preview:
                    cv2.imshow("Phone Stream Capture", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue
            output_path = frames_dir / f"{saved:06d}.jpg"
            ok = cv2.imwrite(str(output_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.jpeg_quality])
            if not ok:
                raise OSError(f"Failed to write {output_path}")
            height, width = frame.shape[:2]
            entry = {
                "index": saved,
                "file": str(output_path.relative_to(session_dir)),
                "timestamp_unix": time.time(),
                "width": width,
                "height": height,
                "read_count": read_count,
            }
            manifest["frames"].append(entry)
            saved += 1
            print(json.dumps(entry), flush=True)
            next_save_time += period
            if now - next_save_time > period:
                next_save_time = now + period
            if args.preview:
                cv2.imshow("Phone Stream Capture", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        elapsed = time.perf_counter() - started
        cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        manifest["ended_at_unix"] = time.time()
        manifest["saved_frames"] = saved
        manifest["read_frames"] = read_count
        manifest["elapsed_sec"] = round(elapsed, 3)
        manifest["actual_saved_fps"] = round(saved / elapsed, 3) if elapsed > 0 else 0.0
        (session_dir / "capture_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {session_dir / 'capture_manifest.json'}")
        print(f"Saved {saved} frames at {manifest['actual_saved_fps']} fps")
        finish_session(session_dir, ROOT / "outputs/live_sessions", args.session_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
