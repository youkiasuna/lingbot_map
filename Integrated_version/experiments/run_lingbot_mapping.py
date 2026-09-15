#!/usr/bin/env python3
"""Create a frame-aligned LingBot-MAP package for relocalization experiments.

This runner intentionally lives in Integrated_version so the upstream LingBot-MAP
checkout remains unchanged. It reuses its preprocessing, model, and postprocess
functions, then persists the camera and 3D outputs that PLY alone discards.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINGBOT_ROOT = INTEGRATED_ROOT.parent / "lingbot-map-main"


def load_lingbot_demo(lingbot_root: Path) -> Any:
    demo_path = lingbot_root / "demo.py"
    if not demo_path.is_file():
        raise FileNotFoundError(f"LingBot-MAP demo.py not found at {demo_path}")
    root = str(lingbot_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    import demo as lingbot_demo

    return lingbot_demo


def export_preprocessed_images(images: torch.Tensor, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(images):
        rgb = (image.permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
        output_path = output_dir / f"{index:06d}.png"
        if not cv2.imwrite(str(output_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise OSError(f"Failed to write {output_path}")


def as_numpy(value: Any, name: str) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    if isinstance(value, np.ndarray):
        return value
    raise TypeError(f"{name} must be a tensor or ndarray, got {type(value).__name__}.")


def require_frame_aligned(name: str, value: np.ndarray, frame_count: int) -> np.ndarray:
    if value.ndim < 1 or value.shape[0] != frame_count:
        raise ValueError(
            f"{name} must be frame-aligned with shape[0]={frame_count}; got {value.shape}."
        )
    return value


def write_prediction_archive(
    predictions: dict[str, Any],
    frame_paths: list[str],
    output_path: Path,
    preprocessed_image_dir: Path,
    derive_world_points: Any,
) -> tuple[Path, Path]:
    """Write camera and dense 2D-to-3D data without changing LingBot-MAP source."""
    frame_count = len(frame_paths)
    if frame_count == 0:
        raise ValueError("At least one mapping frame is required.")
    if output_path.suffix != ".npz":
        raise ValueError("--output-archive must end with .npz.")

    archive: dict[str, np.ndarray] = {
        "schema_version": np.asarray(2, dtype=np.int32),
        "frame_paths": np.asarray([os.path.relpath(Path(path).absolute(), output_path.parent.resolve()) for path in frame_paths]),
    }
    required_fields = {
        "extrinsic_c2w": predictions.get("extrinsic"),
        "intrinsic": predictions.get("intrinsic"),
    }
    for name, value in required_fields.items():
        if value is None:
            raise ValueError(f"LingBot prediction is missing {name}.")
        archive[name] = require_frame_aligned(name, as_numpy(value, name), frame_count)

    if archive["extrinsic_c2w"].shape[1:] != (3, 4):
        raise ValueError("extrinsic_c2w must have shape (N, 3, 4).")
    if archive["intrinsic"].shape[1:] != (3, 3):
        raise ValueError("intrinsic must have shape (N, 3, 3).")

    world_points = predictions.get("world_points")
    if world_points is None:
        world_points = derive_world_points(predictions)
    archive["world_points"] = require_frame_aligned(
        "world_points", as_numpy(world_points, "world_points"), frame_count
    )
    if archive["world_points"].shape[-1] != 3:
        raise ValueError("world_points must end with an XYZ coordinate dimension.")

    for name in ("world_points_conf", "depth", "depth_conf"):
        value = predictions.get(name)
        if value is not None:
            archive[name] = require_frame_aligned(name, as_numpy(value, name), frame_count)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = output_path.with_name(f".{output_path.stem}.tmp.npz")
    np.savez_compressed(temporary_archive, **archive)
    os.replace(temporary_archive, output_path)

    metadata_path = output_path.with_suffix(".json")
    metadata = {
        "schema_version": 2,
        "frame_paths_base": "archive_directory",
        "archive": output_path.name,
        "frame_count": frame_count,
        "coordinate_convention": "extrinsic_c2w maps OpenCV camera coordinates to LingBot world coordinates.",
        "image_coordinate_convention": "world_points[frame, y, x] aligns with preprocessed/<frame>.png pixel (x, y).",
        "preprocessed_image_dir": str(preprocessed_image_dir.resolve()),
        "arrays": {
            name: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for name, value in archive.items()
        },
    }
    temporary_metadata = metadata_path.with_suffix(".json.tmp")
    temporary_metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_metadata, metadata_path)
    return output_path, metadata_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LingBot-MAP and export a reproducible visual-localization map package."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image-folder", type=Path)
    source.add_argument("--video-path", type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lingbot-root", type=Path, default=DEFAULT_LINGBOT_ROOT)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--first-k", type=int, default=None)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--rotate-clockwise-90", action="store_true")
    parser.add_argument("--image-size", type=int, default=518)
    parser.add_argument("--patch-size", type=int, default=14)
    parser.add_argument("--mode", choices=("streaming", "windowed"), default="streaming")
    parser.add_argument("--num-scale-frames", type=int, default=8)
    parser.add_argument("--keyframe-interval", type=int, default=None)
    parser.add_argument("--window-size", type=int, default=64)
    parser.add_argument("--overlap-size", type=int, default=16)
    parser.add_argument("--overlap-keyframes", type=int, default=None)
    parser.add_argument("--camera-num-iterations", type=int, default=4)
    parser.add_argument("--enable-3d-rope", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-frame-num", type=int, default=1024)
    parser.add_argument("--kv-cache-sliding-window", type=int, default=64)
    parser.add_argument("--use-sdpa", action="store_true")
    parser.add_argument("--offload-to-cpu", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-ply", type=Path, default=None)
    parser.add_argument("--conf-threshold", type=float, default=1.5)
    parser.add_argument("--downsample-factor", type=int, default=10)
    args = parser.parse_args()
    if args.fps <= 0 or args.stride <= 0 or args.image_size <= 0 or args.patch_size <= 0:
        parser.error("fps, stride, image-size, and patch-size must be positive")
    if args.keyframe_interval is not None and args.keyframe_interval <= 0:
        parser.error("keyframe-interval must be positive")
    if args.downsample_factor <= 0:
        parser.error("downsample-factor must be positive")
    return args


def run(args: argparse.Namespace) -> None:
    lingbot_demo = load_lingbot_demo(args.lingbot_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    preprocessed_dir = args.output_dir / "preprocessed"
    archive_path = args.output_dir / "predictions.npz"

    images, frame_paths, resolved_image_folder = lingbot_demo.load_images(
        image_folder=str(args.image_folder) if args.image_folder else None,
        video_path=str(args.video_path) if args.video_path else None,
        fps=args.fps,
        first_k=args.first_k,
        stride=args.stride,
        image_size=args.image_size,
        patch_size=args.patch_size,
        rotate_clockwise_90=args.rotate_clockwise_90,
    )
    export_preprocessed_images(images, preprocessed_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = lingbot_demo.load_model(args, device)
    if device.type == "cuda":
        dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    else:
        dtype = torch.float32
    if dtype != torch.float32 and getattr(model, "aggregator", None) is not None:
        model.aggregator = model.aggregator.to(dtype=dtype)

    images = images.to(device)
    frame_count = images.shape[0]
    if args.keyframe_interval is None:
        args.keyframe_interval = (frame_count + 319) // 320 if args.mode == "streaming" and frame_count > 320 else 1

    output_device = torch.device("cpu") if args.offload_to_cpu else None
    started_at = time.perf_counter()
    with torch.no_grad(), torch.amp.autocast("cuda", dtype=dtype, enabled=device.type == "cuda"):
        if args.mode == "streaming":
            predictions = model.inference_streaming(
                images,
                num_scale_frames=args.num_scale_frames,
                keyframe_interval=args.keyframe_interval,
                output_device=output_device,
            )
        else:
            predictions = model.inference_windowed(
                images,
                window_size=args.window_size,
                overlap_size=args.overlap_size,
                overlap_keyframes=args.overlap_keyframes,
                num_scale_frames=args.num_scale_frames,
                keyframe_interval=args.keyframe_interval,
                output_device=output_device,
            )
    inference_seconds = time.perf_counter() - started_at

    if args.offload_to_cpu:
        del images
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        images_for_post = predictions["images"]
    else:
        images_for_post = images
    predictions, images_cpu = lingbot_demo.postprocess(predictions, images_for_post)
    archive, metadata = write_prediction_archive(
        predictions,
        frame_paths,
        archive_path,
        preprocessed_dir,
        lingbot_demo._get_world_points,
    )

    run_metadata = {
        "lingbot_root": str(args.lingbot_root.resolve()),
        "resolved_image_folder": resolved_image_folder,
        "mode": args.mode,
        "keyframe_interval": args.keyframe_interval,
        "camera_num_iterations": args.camera_num_iterations,
        "inference_seconds": round(inference_seconds, 3),
        "device": str(device),
    }
    (args.output_dir / "run.json").write_text(
        json.dumps(run_metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {archive}")
    print(f"Wrote {metadata}")

    if args.output_ply:
        vis_predictions = lingbot_demo.prepare_for_visualization(predictions, images_cpu)
        lingbot_demo.export_predictions_to_ply(
            vis_predictions,
            str(args.output_ply),
            conf_threshold=args.conf_threshold,
            downsample_factor=args.downsample_factor,
            image_folder=resolved_image_folder,
        )


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
