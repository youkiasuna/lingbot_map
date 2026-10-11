#!/usr/bin/env python3
"""Create a frame-aligned LingBot-MAP package for relocalization experiments.

This runner intentionally lives in Integrated_version so the upstream LingBot-MAP
checkout remains unchanged. It reuses its preprocessing, model, and postprocess
functions, then persists the camera and 3D outputs that PLY alone discards.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

INTEGRATED_ROOT = REPOSITORY_ROOT / "Integrated_version"
DEFAULT_LINGBOT_ROOT = INTEGRATED_ROOT.parent / "lingbot-map-main"

from Integrated_version.runtime.lingbot_map_integration import (
    export_preprocessed_images,
    load_lingbot_demo,
    write_prediction_archive,
)


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
