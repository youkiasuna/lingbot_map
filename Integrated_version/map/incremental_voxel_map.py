#!/usr/bin/env python3
"""Incremental voxel-to-occupancy map utilities for online replay experiments."""

from __future__ import annotations

import json
import math
import struct
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

FREE = 254
UNKNOWN = 205
OCCUPIED = 0

PLY_ROW = struct.Struct("<fffBBBf")


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def axis_indices(vertical_axis: str) -> tuple[int, float, list[int]]:
    axis = vertical_axis[-1]
    axis_index = "xyz".index(axis)
    sign = -1.0 if vertical_axis.startswith("-") else 1.0
    horizontal = [index for index in range(3) if index != axis_index]
    return axis_index, sign, horizontal


def estimate_floor_height(
    points_xyz: np.ndarray,
    vertical_axis: str = "-y",
    low_percentile: float = 1.0,
    high_percentile: float = 35.0,
    bin_size_m: float = 0.015,
) -> float:
    axis_index, sign, _ = axis_indices(vertical_axis)
    heights = sign * points_xyz[:, axis_index]
    low, high = np.percentile(heights, [low_percentile, high_percentile])
    sample = heights[(heights >= low) & (heights <= high)]
    if sample.size == 0:
        return float(np.percentile(heights, 10.0))
    bins = max(8, int(math.ceil((float(sample.max()) - float(sample.min())) / bin_size_m)))
    counts, edges = np.histogram(sample, bins=bins)
    peak = int(np.argmax(counts))
    return float((edges[peak] + edges[peak + 1]) * 0.5)


def remove_small_components(mask: np.ndarray, min_cells: int) -> tuple[np.ndarray, int, int]:
    if min_cells <= 1:
        return mask, int(mask.sum()), 0
    height, width = mask.shape
    result = mask.copy()
    visited = np.zeros_like(mask, dtype=bool)
    component_count = 0
    removed_cells = 0
    for sy in range(height):
        for sx in range(width):
            if visited[sy, sx] or not mask[sy, sx]:
                continue
            component_count += 1
            queue: deque[tuple[int, int]] = deque([(sx, sy)])
            visited[sy, sx] = True
            cells: list[tuple[int, int]] = []
            while queue:
                x, y = queue.popleft()
                cells.append((x, y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
            if len(cells) < min_cells:
                removed_cells += len(cells)
                for x, y in cells:
                    result[y, x] = False
    return result, component_count, removed_cells


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


def component_stats(free: np.ndarray) -> dict[str, int]:
    height, width = free.shape
    visited = np.zeros_like(free, dtype=bool)
    sizes: list[int] = []
    for sy in range(height):
        for sx in range(width):
            if visited[sy, sx] or not free[sy, sx]:
                continue
            queue: deque[tuple[int, int]] = deque([(sx, sy)])
            visited[sy, sx] = True
            size = 0
            while queue:
                x, y = queue.popleft()
                size += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and free[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            sizes.append(size)
    return {
        "free_components": len(sizes),
        "largest_free_component_cells": max(sizes) if sizes else 0,
    }


class IncrementalVoxelMap:
    """Dictionary-backed runtime map that can grow as new frames arrive."""

    def __init__(
        self,
        *,
        floor_height_m: float,
        vertical_axis: str = "-y",
        resolution_m: float = 0.05,
        voxel_size_m: float = 0.04,
        voxel_min_points: int = 2,
        floor_band_m: float = 0.10,
        floor_min_points_per_cell: int = 2,
        obstacle_min_height_m: float = 0.18,
        obstacle_max_height_m: float = 2.0,
        obstacle_min_points_per_cell: int = 4,
        min_obstacle_component_cells: int = 4,
        robot_radius_m: float = 0.08,
        snapshot_point_limit: int = 250_000,
    ) -> None:
        self.floor_height_m = floor_height_m
        self.vertical_axis = vertical_axis
        self.resolution_m = resolution_m
        self.voxel_size_m = voxel_size_m
        self.voxel_min_points = voxel_min_points
        self.floor_band_m = floor_band_m
        self.floor_min_points_per_cell = floor_min_points_per_cell
        self.obstacle_min_height_m = obstacle_min_height_m
        self.obstacle_max_height_m = obstacle_max_height_m
        self.obstacle_min_points_per_cell = obstacle_min_points_per_cell
        self.min_obstacle_component_cells = min_obstacle_component_cells
        self.robot_radius_m = robot_radius_m
        self.snapshot_point_limit = snapshot_point_limit
        self.axis_index, self.axis_sign, self.horizontal_indices = axis_indices(vertical_axis)
        self.floor_counts: defaultdict[tuple[int, int], int] = defaultdict(int)
        self.obstacle_counts: defaultdict[tuple[int, int], int] = defaultdict(int)
        self.frame_count = 0
        self.accepted_points = 0
        self.floor_points = 0
        self.obstacle_points = 0
        self.unknown_points = 0
        self.snapshot_points: list[tuple[float, float, float, int, int, int, float]] = []

    def update(self, points_xyz: np.ndarray, confidence: np.ndarray | None = None) -> dict[str, int]:
        if points_xyz.ndim != 2 or points_xyz.shape[1] != 3:
            raise ValueError("points_xyz must have shape (N, 3).")
        finite = np.isfinite(points_xyz).all(axis=1)
        points = points_xyz[finite]
        if confidence is not None:
            conf = confidence.reshape(-1)[finite]
        else:
            conf = np.ones(points.shape[0], dtype=np.float32)
        if points.size == 0:
            self.frame_count += 1
            return {"accepted_points": 0, "floor_points": 0, "obstacle_points": 0, "unknown_points": 0}

        q = np.floor(points / self.voxel_size_m).astype(np.int32)
        _, unique_indices, inverse, counts = np.unique(
            q,
            axis=0,
            return_index=True,
            return_inverse=True,
            return_counts=True,
        )
        keep = counts[inverse] >= self.voxel_min_points
        kept = points[keep]
        kept_conf = conf[keep]

        heights = self.axis_sign * kept[:, self.axis_index]
        relative_heights = heights - self.floor_height_m
        us = kept[:, self.horizontal_indices[0]]
        vs = kept[:, self.horizontal_indices[1]]
        cell_u = np.floor(us / self.resolution_m).astype(np.int32)
        cell_v = np.floor(vs / self.resolution_m).astype(np.int32)

        floor_mask = np.abs(relative_heights) <= self.floor_band_m
        obstacle_mask = (
            (relative_heights >= self.obstacle_min_height_m)
            & (relative_heights <= self.obstacle_max_height_m)
        )
        for key in zip(cell_u[floor_mask], cell_v[floor_mask]):
            self.floor_counts[(int(key[0]), int(key[1]))] += 1
        for key in zip(cell_u[obstacle_mask], cell_v[obstacle_mask]):
            self.obstacle_counts[(int(key[0]), int(key[1]))] += 1

        self.frame_count += 1
        self.accepted_points += int(kept.shape[0])
        self.floor_points += int(floor_mask.sum())
        self.obstacle_points += int(obstacle_mask.sum())
        self.unknown_points += int((~(floor_mask | obstacle_mask)).sum())
        self._append_snapshot_points(kept, kept_conf, floor_mask, obstacle_mask)
        return {
            "accepted_points": int(kept.shape[0]),
            "floor_points": int(floor_mask.sum()),
            "obstacle_points": int(obstacle_mask.sum()),
            "unknown_points": int((~(floor_mask | obstacle_mask)).sum()),
        }

    def _append_snapshot_points(
        self,
        points: np.ndarray,
        confidence: np.ndarray,
        floor_mask: np.ndarray,
        obstacle_mask: np.ndarray,
    ) -> None:
        if len(self.snapshot_points) >= self.snapshot_point_limit:
            return
        budget = self.snapshot_point_limit - len(self.snapshot_points)
        step = max(1, int(math.ceil(points.shape[0] / max(1, min(budget, 4000)))))
        selected = np.arange(0, points.shape[0], step)[:budget]
        for index in selected:
            x, y, z = (float(v) for v in points[index])
            if floor_mask[index]:
                color = (235, 242, 238)
            elif obstacle_mask[index]:
                color = (31, 39, 45)
            else:
                color = (174, 183, 189)
            self.snapshot_points.append((x, y, z, *color, float(confidence[index])))

    def to_grid(self) -> tuple[np.ndarray, dict[str, object]]:
        keys = set(self.floor_counts) | set(self.obstacle_counts)
        if not keys:
            pixels = np.asarray([[UNKNOWN]], dtype=np.uint8)
            metadata = self._metadata(0, 0, 1, 1, pixels, np.zeros((1, 1), dtype=bool), 0, 0, 0)
            return pixels, metadata
        min_u = min(key[0] for key in keys)
        max_u = max(key[0] for key in keys)
        min_v = min(key[1] for key in keys)
        max_v = max(key[1] for key in keys)
        width = max_u - min_u + 1
        height = max_v - min_v + 1
        floor = np.zeros((height, width), dtype=np.int32)
        obstacle = np.zeros((height, width), dtype=np.int32)
        for (u, v), count in self.floor_counts.items():
            floor[max_v - v, u - min_u] = count
        for (u, v), count in self.obstacle_counts.items():
            obstacle[max_v - v, u - min_u] = count
        free = floor >= self.floor_min_points_per_cell
        occupied_raw = obstacle >= self.obstacle_min_points_per_cell
        occupied_clean, obstacle_components, removed_obstacles = remove_small_components(
            occupied_raw,
            self.min_obstacle_component_cells,
        )
        inflation_pixels = math.ceil(self.robot_radius_m / self.resolution_m)
        occupied = dilate(occupied_clean, inflation_pixels)
        pixels = np.full((height, width), UNKNOWN, dtype=np.uint8)
        pixels[free] = FREE
        pixels[occupied] = OCCUPIED
        metadata = self._metadata(
            min_u,
            max_v,
            width,
            height,
            pixels,
            occupied,
            obstacle_components,
            removed_obstacles,
            inflation_pixels,
        )
        metadata["counts"].update(component_stats(pixels == FREE))
        return pixels, metadata

    def _metadata(
        self,
        min_u_cell: int,
        max_v_cell: int,
        width: int,
        height: int,
        pixels: np.ndarray,
        occupied: np.ndarray,
        obstacle_components: int,
        removed_obstacles: int,
        inflation_pixels: int,
    ) -> dict[str, object]:
        return {
            "format_version": 1,
            "method": "incremental_voxel_online_replay",
            "vertical_axis": self.vertical_axis,
            "horizontal_axes": "".join(axis.upper() for axis in "xyz" if axis != self.vertical_axis[-1]),
            "floor_height_m": self.floor_height_m,
            "resolution_m": self.resolution_m,
            "meters_per_pixel": self.resolution_m,
            "origin_u_m": min_u_cell * self.resolution_m,
            "origin_v_m": (max_v_cell + 1) * self.resolution_m,
            "width_px": width,
            "height_px": height,
            "voxel_size_m": self.voxel_size_m,
            "voxel_min_points": self.voxel_min_points,
            "floor_band_m": self.floor_band_m,
            "floor_min_points_per_cell": self.floor_min_points_per_cell,
            "obstacle_min_height_m": self.obstacle_min_height_m,
            "obstacle_max_height_m": self.obstacle_max_height_m,
            "obstacle_min_points_per_cell": self.obstacle_min_points_per_cell,
            "min_obstacle_component_cells": self.min_obstacle_component_cells,
            "robot_radius_m": self.robot_radius_m,
            "inflation_pixels": inflation_pixels,
            "counts": {
                "frames_integrated": self.frame_count,
                "accepted_points": self.accepted_points,
                "floor_points": self.floor_points,
                "obstacle_points": self.obstacle_points,
                "unknown_points": self.unknown_points,
                "free_cells": int((pixels == FREE).sum()),
                "occupied_cells": int(occupied.sum()),
                "unknown_cells": int((pixels == UNKNOWN).sum()),
                "obstacle_components_raw": int(obstacle_components),
                "removed_small_obstacle_cells": int(removed_obstacles),
            },
            "pgm_values": "0=occupied inflated, 205=unknown, 254=free floor",
        }

    def write(self, output_dir: Path) -> dict[str, object]:
        pixels, metadata = self.to_grid()
        output_dir.mkdir(parents=True, exist_ok=True)
        write_pgm(output_dir / "map.pgm", int(metadata["width_px"]), int(metadata["height_px"]), pixels.tobytes())
        write_pgm(output_dir / "navigation_map.pgm", int(metadata["width_px"]), int(metadata["height_px"]), pixels.tobytes())
        (output_dir / "map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (output_dir / "navigation_map.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        self.write_snapshot_ply(output_dir / "snapshot.ply")
        return metadata

    def write_snapshot_ply(self, path: Path) -> None:
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            "comment online replay snapshot\n"
            f"element vertex {len(self.snapshot_points)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            "property float confidence\nend_header\n"
        )
        with path.open("wb") as handle:
            handle.write(header.encode("ascii"))
            for point in self.snapshot_points:
                handle.write(PLY_ROW.pack(*point))
