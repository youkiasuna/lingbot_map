"""LingBot-MAP inference backend for bounded offline sliding windows."""
from __future__ import annotations
from dataclasses import dataclass
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Iterator
import numpy as np

from runtime.local_pointcloud_backend import LocalPointCloudResult


@dataclass(frozen=True)
class LingBotMapBackendConfig:
    source_dir: Path
    model_path: Path
    lingbot_root: Path
    output_root: Path
    max_points_per_window: int = 100_000
    camera_num_iterations: int = 1
    use_sdpa: bool = True


class LingBotMapBackend:
    """Run the existing mapping entry point on bounded image windows.

    This is an offline adapter, not streaming inference. The model is invoked
    once per selected window and its predictions.npz is converted to the
    common LocalPointCloudResult contract.
    """

    name = "lingbot_map_windowed"

    def __init__(self, config: LingBotMapBackendConfig) -> None:
        self.config = config
        self.image_paths = sorted(
            path for path in config.source_dir.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        if not self.image_paths:
            raise ValueError(f"no images found in {config.source_dir}")
        if not config.model_path.is_file():
            raise FileNotFoundError(config.model_path)
        if not config.lingbot_root.is_dir():
            raise FileNotFoundError(config.lingbot_root)

    def iter_generate(
        self,
        *,
        window_size: int,
        process_every: int,
        max_frames: int = 0,
        max_windows: int = 0,
    ) -> Iterator[LocalPointCloudResult]:
        if window_size <= 0 or process_every <= 0:
            raise ValueError("window_size and process_every must be positive")
        limit = len(self.image_paths) if max_frames <= 0 else min(max_frames, len(self.image_paths))
        emitted = 0
        for end in range(window_size, limit + 1, process_every):
            if max_windows > 0 and emitted >= max_windows:
                break
            start = end - window_size
            started = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix="lingbot_window_") as temp_dir:
                image_dir = Path(temp_dir) / "images"
                image_dir.mkdir()
                for path in self.image_paths[start:end]:
                    shutil.copy2(path, image_dir / path.name)
                package_dir = self.config.output_root / f"window_{start:06d}_{end - 1:06d}"
                package_dir.mkdir(parents=True, exist_ok=True)
                self._run_mapping(image_dir, package_dir)
                archive = package_dir / "predictions.npz"
                data = np.load(archive, allow_pickle=True)
                points = np.asarray(data["world_points"], dtype=np.float32).reshape(-1, 3)
                points = points[np.isfinite(points).all(axis=1)]
                if len(points) > self.config.max_points_per_window:
                    stride = max(1, len(points) // self.config.max_points_per_window)
                    points = points[::stride][:self.config.max_points_per_window]
            yield LocalPointCloudResult(
                backend=self.name,
                start_frame=start,
                end_frame=end - 1,
                points_xyz=points,
                pose_xyz=None,
                yaw_deg=None,
                confidence=1.0,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                source=str(package_dir / "predictions.npz"),
            )
            emitted += 1

    def _run_mapping(self, image_dir: Path, output_dir: Path) -> None:
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "experiments" / "run_lingbot_mapping.py"),
            "--image-folder", str(image_dir),
            "--model-path", str(self.config.model_path),
            "--output-dir", str(output_dir),
            "--lingbot-root", str(self.config.lingbot_root),
            "--camera-num-iterations", str(self.config.camera_num_iterations),
            "--downsample-factor", "4",
        ]
        if self.config.use_sdpa:
            command.append("--use-sdpa")
        subprocess.run(command, check=True)
