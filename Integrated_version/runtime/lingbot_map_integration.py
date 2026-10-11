"""Reusable adapters for the upstream LingBot-MAP package and its outputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from Integrated_version.shared.json_io import atomic_write_json
from Integrated_version.shared.npz_io import atomic_write_npz


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
    """Persist frame-aligned camera and dense 2D-to-3D prediction data."""
    frame_count = len(frame_paths)
    if frame_count == 0:
        raise ValueError("At least one mapping frame is required.")
    if output_path.suffix != ".npz":
        raise ValueError("--output-archive must end with .npz.")

    archive: dict[str, np.ndarray] = {
        "schema_version": np.asarray(2, dtype=np.int32),
        "frame_paths": np.asarray([
            os.path.relpath(Path(path).absolute(), output_path.parent.resolve())
            for path in frame_paths
        ]),
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

    atomic_write_npz(output_path, archive)

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
    atomic_write_json(metadata_path, metadata, indent=2)
    return output_path, metadata_path
