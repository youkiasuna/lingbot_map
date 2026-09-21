"""Reusable in-process LingBot-MAP model session.

The session loads the model once and can infer multiple image windows without
starting a new Python subprocess for every window.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import time
from typing import Any
import cv2
import numpy as np
import torch

from experiments.run_lingbot_mapping import (
    as_numpy,
    export_preprocessed_images,
    load_lingbot_demo,
    write_prediction_archive,
)


@dataclass(frozen=True)
class LingBotMapSessionConfig:
    model_path: Path
    lingbot_root: Path
    image_size: int = 518
    patch_size: int = 14
    camera_num_iterations: int = 1
    mode: str = "streaming"
    num_scale_frames: int = 8
    keyframe_interval: int = 1
    window_size: int = 64
    overlap_size: int = 16
    use_sdpa: bool = True
    offload_to_cpu: bool = True


class LingBotMapSession:
    """Load LingBot-MAP once and reuse it for multiple inference windows."""

    def __init__(self, config: LingBotMapSessionConfig) -> None:
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.demo = load_lingbot_demo(config.lingbot_root)
        args = SimpleNamespace(
            model_path=config.model_path,
            image_size=config.image_size,
            patch_size=config.patch_size,
            camera_num_iterations=config.camera_num_iterations,
            mode=config.mode,
            num_scale_frames=config.num_scale_frames,
            keyframe_interval=config.keyframe_interval,
            window_size=config.window_size,
            overlap_size=config.overlap_size,
            overlap_keyframes=None,
            enable_3d_rope=True,
            max_frame_num=1024,
            kv_cache_sliding_window=64,
            use_sdpa=config.use_sdpa,
            offload_to_cpu=config.offload_to_cpu,
        )
        started = time.perf_counter()
        self.model = self.demo.load_model(args, self.device)
        self.model_load_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if self.device.type == "cuda":
            dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
        else:
            dtype = torch.float32
        self.dtype = dtype
        if dtype != torch.float32 and getattr(self.model, "aggregator", None) is not None:
            self.model.aggregator = self.model.aggregator.to(dtype=dtype)

    def infer_image_folder(self, image_dir: Path, output_dir: Path) -> dict[str, Any]:
        started = time.perf_counter()
        images, frame_paths, resolved_folder = self.demo.load_images(
            image_folder=str(image_dir),
            video_path=None,
            fps=10,
            first_k=None,
            stride=1,
            image_size=self.config.image_size,
            patch_size=self.config.patch_size,
            rotate_clockwise_90=False,
        )
        export_preprocessed_images(images, output_dir / "preprocessed")
        images = images.to(self.device)
        output_device = torch.device("cpu") if self.config.offload_to_cpu else None
        inference_started = time.perf_counter()
        with torch.no_grad(), torch.amp.autocast(
            "cuda",
            dtype=self.dtype,
            enabled=self.device.type == "cuda",
        ):
            if self.config.mode == "streaming":
                predictions = self.model.inference_streaming(
                    images,
                    num_scale_frames=self.config.num_scale_frames,
                    keyframe_interval=self.config.keyframe_interval,
                    output_device=output_device,
                )
            else:
                predictions = self.model.inference_windowed(
                    images,
                    window_size=self.config.window_size,
                    overlap_size=self.config.overlap_size,
                    overlap_keyframes=None,
                    num_scale_frames=self.config.num_scale_frames,
                    keyframe_interval=self.config.keyframe_interval,
                    output_device=output_device,
                )
        inference_ms = round((time.perf_counter() - inference_started) * 1000.0, 3)
        if self.config.offload_to_cpu:
            del images
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            images_for_post = predictions["images"]
        else:
            images_for_post = images
        predictions, images_cpu = self.demo.postprocess(predictions, images_for_post)
        archive, metadata = write_prediction_archive(
            predictions,
            frame_paths,
            output_dir / "predictions.npz",
            output_dir / "preprocessed",
            self.demo._get_world_points,
        )
        points = np.asarray(predictions["world_points"])
        points = points.reshape(-1, 3)
        points = points[np.isfinite(points).all(axis=1)]
        return {
            "points_xyz": points.astype(np.float32),
            "archive": archive,
            "metadata": metadata,
            "model_load_ms": self.model_load_ms,
            "inference_ms": inference_ms,
            "total_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "device": str(self.device),
        }
