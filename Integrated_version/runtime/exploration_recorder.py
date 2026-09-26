"""Optional on-disk keyframe recorder for unknown-scene exploration."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time


@dataclass(frozen=True)
class ExplorationRecord:
    frame_id: int
    timestamp_unix: float
    width: int
    height: int
    path: str


class ExplorationFrameRecorder:
    """Save selected frames without retaining the image stream in memory."""

    def __init__(self, output_dir: str | Path, *, frame_every: int = 10) -> None:
        if frame_every <= 0:
            raise ValueError("frame_every must be positive")
        self.output_dir = Path(output_dir)
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.frame_every = int(frame_every)
        self.saved_frames = 0
        self.manifest_path = self.output_dir / "frames.jsonl"
        self.session_path = self.output_dir / "session.json"
        self._write_session()

    def record(self, cv2_module, frame, *, frame_id: int, timestamp_unix: float) -> bool:
        if frame_id % self.frame_every != 0:
            return False
        destination = self.frames_dir / f"{frame_id:06d}.jpg"
        if destination.exists():
            return False
        temporary = self.frames_dir / f".{frame_id:06d}.{os.getpid()}.tmp.jpg"
        if not cv2_module.imwrite(str(temporary), frame):
            raise OSError(f"failed to write exploration frame: {temporary}")
        os.replace(temporary, destination)
        record = ExplorationRecord(
            frame_id=int(frame_id),
            timestamp_unix=float(timestamp_unix),
            width=int(frame.shape[1]),
            height=int(frame.shape[0]),
            path=str(destination.relative_to(self.output_dir)),
        )
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
        self.saved_frames += 1
        self._write_session()
        return True

    def _write_session(self) -> None:
        payload = {
            "schema_version": 1,
            "created_at_unix": time.time(),
            "frame_every": self.frame_every,
            "saved_frames": self.saved_frames,
            "frames_manifest": self.manifest_path.name,
            "frames_dir": self.frames_dir.name,
        }
        temporary = self.session_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.session_path)
