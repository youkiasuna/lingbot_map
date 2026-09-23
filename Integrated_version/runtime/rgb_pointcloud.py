"""Utilities for associating RGB pixels with world-space points."""
from __future__ import annotations

from typing import Tuple

import numpy as np


def flatten_colored_world_points(
    world_points: np.ndarray,
    images_rgb: np.ndarray,
    *,
    max_points: int | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Flatten frame-aligned world points and RGB images into point/color arrays.

    world_points must have shape (frames, height, width, 3) and images_rgb
    must have shape (frames, height, width, 3). Invalid world points are
    removed together with their corresponding colors. Images are expected to
    already be RGB uint8-like arrays; no channel conversion is guessed here.
    """
    points = np.asarray(world_points)
    colors = np.asarray(images_rgb)
    if points.ndim != 4 or points.shape[-1] != 3:
        raise ValueError("world_points must have shape (frames, height, width, 3)")
    if colors.ndim != 4 or colors.shape[-1] != 3:
        raise ValueError("images_rgb must have shape (frames, height, width, 3)")
    if points.shape[:3] != colors.shape[:3]:
        raise ValueError("world_points and images_rgb must be frame/pixel aligned")
    if max_points is not None and max_points <= 0:
        raise ValueError("max_points must be positive when provided")

    flat_points = points.reshape(-1, 3).astype(np.float32, copy=False)
    flat_colors = np.clip(colors.reshape(-1, 3), 0, 255).astype(np.uint8, copy=False)
    valid = np.isfinite(flat_points).all(axis=1)
    flat_points = flat_points[valid]
    flat_colors = flat_colors[valid]

    if max_points is not None and len(flat_points) > max_points:
        stride = max(1, len(flat_points) // max_points)
        flat_points = flat_points[::stride][:max_points]
        flat_colors = flat_colors[::stride][:max_points]
    return flat_points, flat_colors
