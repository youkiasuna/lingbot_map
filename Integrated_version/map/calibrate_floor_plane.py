#!/usr/bin/env python3
"""RANSAC floor-plane calibration for cleaned LingBot-MAP point clouds.

The result uses one canonical convention for navigation:

    X/Y = horizontal plane, Z = up, floor height = 0

Horizontal yaw is intentionally left unchanged. A later calibration step can
align yaw to the robot or to a user-selected direction.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import struct
from pathlib import Path

ROW = struct.Struct("<fffBBBf")


def read_ply(path: Path, max_points: int | None) -> tuple[list[tuple[float, float, float, int, int, int, float]], list[tuple[float, float, float, int, int, int, float]], int]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError("The input is not a PLY file.")
        vertex_count = 0
        while True:
            line = handle.readline().decode("ascii", errors="strict").strip()
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[2])
            if line == "end_header":
                break
        if vertex_count <= 0:
            raise ValueError("PLY has no vertices.")
        stride = max(1, math.ceil(vertex_count / max_points)) if max_points else 1
        points = []
        for index in range(vertex_count):
            raw = handle.read(ROW.size)
            if len(raw) != ROW.size:
                raise ValueError("PLY vertex data ended unexpectedly.")
            points.append(ROW.unpack(raw))
    fit_points = points[::stride]
    return points, fit_points, stride


def cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
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


def plane_from_points(a, b, c) -> tuple[float, float, float, float] | None:
    normal = normalize(cross(
        (b[0] - a[0], b[1] - a[1], b[2] - a[2]),
        (c[0] - a[0], c[1] - a[1], c[2] - a[2]),
    ))
    d = -(normal[0] * a[0] + normal[1] * a[1] + normal[2] * a[2])
    return normal[0], normal[1], normal[2], d


def plane_distance(plane: tuple[float, float, float, float], point) -> float:
    a, b, c, d = plane
    return abs(a * point[0] + b * point[1] + c * point[2] + d)


def ransac_plane(points, iterations: int, threshold_m: float, seed: int) -> tuple[tuple[float, float, float, float], list[int]]:
    if len(points) < 3:
        raise ValueError("At least three points are required for plane fitting.")
    rng = random.Random(seed)
    best_plane = None
    best_inliers: list[int] = []
    for _ in range(iterations):
        a, b, c = rng.sample(points, 3)
        try:
            plane = plane_from_points(a, b, c)
        except ValueError:
            continue
        inliers = [index for index, point in enumerate(points) if plane_distance(plane, point) <= threshold_m]
        if len(inliers) > len(best_inliers):
            best_plane = plane
            best_inliers = inliers
    if best_plane is None or len(best_inliers) < 3:
        raise ValueError("RANSAC could not find a floor plane.")
    return best_plane, best_inliers


def signed_up_axis(axis: str) -> tuple[float, float, float]:
    sign = -1.0 if axis.startswith("-") else 1.0
    index = "xyz".index(axis[-1])
    result = [0.0, 0.0, 0.0]
    result[index] = sign
    return tuple(result)


def rotate_vector_to_target(
    vector: tuple[float, float, float],
    target: tuple[float, float, float],
) -> tuple[tuple[float, float, float], float]:
    dot = max(-1.0, min(1.0, sum(vector[i] * target[i] for i in range(3))))
    axis = cross(vector, target)
    axis_length = math.sqrt(sum(value * value for value in axis))
    if axis_length < 1e-9:
        if dot > 0:
            return (1.0, 0.0, 0.0), 0.0
        return (1.0, 0.0, 0.0), math.pi
    return normalize(axis), math.acos(dot)


def rotate(point: tuple[float, float, float], axis: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    dot = sum(point[i] * axis[i] for i in range(3))
    cross_value = cross(axis, point)
    return tuple(
        point[i] * cosine + cross_value[i] * sine + axis[i] * dot * (1.0 - cosine)
        for i in range(3)
    )


def write_ply(path: Path, points, transformed: list[tuple[float, float, float]]) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment calibrated by calibrate_floor_plane.py\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property float confidence\nend_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        for point, output in zip(points, transformed):
            handle.write(ROW.pack(*output, point[3], point[4], point[5], point[6]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit a floor plane and transform a point cloud to canonical Z-up coordinates.")
    parser.add_argument("--ply", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--input-up-axis", choices=("x", "-x", "y", "-y", "z", "-z"), required=True)
    parser.add_argument("--output-up-axis", choices=("x", "-x", "y", "-y", "z", "-z"), default="z")
    parser.add_argument("--max-fit-points", type=int, default=30_000)
    parser.add_argument("--ransac-iterations", type=int, default=1_000)
    parser.add_argument("--inlier-threshold-m", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=202608)
    args = parser.parse_args()
    if not args.ply.exists():
        raise SystemExit(f"PLY file not found: {args.ply}")

    points, fit_points, stride = read_ply(args.ply, args.max_fit_points)
    xyz = [point[:3] for point in fit_points]
    plane, inlier_indices = ransac_plane(xyz, args.ransac_iterations, args.inlier_threshold_m, args.seed)
    normal = plane[:3]
    input_up = signed_up_axis(args.input_up_axis)
    if sum(normal[i] * input_up[i] for i in range(3)) < 0:
        normal = tuple(-value for value in normal)
        plane = tuple(-value for value in plane)
    output_up = signed_up_axis(args.output_up_axis)
    rotation_axis, rotation_angle = rotate_vector_to_target(normal, output_up)

    rotated = [rotate(point[:3], rotation_axis, rotation_angle) for point in points]
    rotated_fit = [rotate(point[:3], rotation_axis, rotation_angle) for point in fit_points]
    floor_height = sorted(
        sum(rotated_fit[index][axis] * output_up[axis] for axis in range(3))
        for index in inlier_indices
    )[len(inlier_indices) // 2]
    transformed = [
        tuple(rotated_point[axis] - output_up[axis] * floor_height for axis in range(3))
        for rotated_point in rotated
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    date_match = re.search(r"20\d{6}", args.ply.stem)
    date_name = date_match.group(0) if date_match else "calibrated"
    output_ply = args.output_dir / f"{date_name}_floor_calibrated.ply"
    write_ply(output_ply, points, transformed)
    residuals = [
        abs(sum(
            (rotated_fit[index][axis] - output_up[axis] * floor_height) * output_up[axis]
            for axis in range(3)
        ))
        for index in inlier_indices
    ]
    metadata = {
        "format_version": 1,
        "input_ply": str(args.ply),
        "output_ply": str(output_ply),
        "input_up_axis": args.input_up_axis,
        "output_up_axis": args.output_up_axis,
        "input_stride": stride,
        "fit_points": len(fit_points),
        "output_points": len(points),
        "inlier_count": len(inlier_indices),
        "inlier_ratio": len(inlier_indices) / len(points),
        "ransac_threshold_m": args.inlier_threshold_m,
        "floor_height_after_rotation_m": floor_height,
        "floor_residual_mean_abs_m": sum(residuals) / len(residuals),
        "floor_residual_p95_m": sorted(residuals)[int(0.95 * (len(residuals) - 1))],
        "plane_normal_input": normal,
        "rotation_axis": rotation_axis,
        "rotation_angle_rad": rotation_angle,
        "translation_after_rotation_m": [-output_up[axis] * floor_height for axis in range(3)],
    }
    (args.output_dir / f"{date_name}_floor_calibration.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Fitted {len(inlier_indices):,}/{len(points):,} floor inliers ({metadata['inlier_ratio']:.1%}).")
    print(f"Input axis: {args.input_up_axis}; output axis: {args.output_up_axis}; floor residual p95: {metadata['floor_residual_p95_m']:.4f} m")
    print(f"Wrote {output_ply}")


if __name__ == "__main__":
    main()