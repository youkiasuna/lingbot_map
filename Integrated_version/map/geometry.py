"""Shared axis, grid-mask, and vector geometry operations."""

from __future__ import annotations

import math

import numpy as np


def axis_indices(vertical_axis: str) -> tuple[int, float, list[int]]:
    axis = vertical_axis[-1]
    axis_index = "xyz".index(axis)
    sign = -1.0 if vertical_axis.startswith("-") else 1.0
    horizontal = [index for index in range(3) if index != axis_index]
    return axis_index, sign, horizontal


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    height, width = mask.shape
    result = mask.copy()
    offsets = [
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    ]
    ys, xs = np.nonzero(mask)
    for x, y in zip(xs, ys):
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                result[ny, nx] = True
    return result


def cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-9:
        raise ValueError("Cannot normalize a zero-length vector.")
    return tuple(value / length for value in vector)
