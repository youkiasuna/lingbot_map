#!/usr/bin/env python3
"""Fuse LingBot-MAP depth predictions into a TSDF mesh.

This script consumes the ``predictions.npz`` archive written by
``run_lingbot_mapping.py`` and exports:

* ``tsdf_mesh.ply``: the full triangle mesh for research/demo use.
* ``live_mesh.json``: a compact mesh preview for the browser demo.

Open3D is intentionally used for the TSDF backend. If it is not installed, the
script fails clearly instead of silently producing a point-cloud-only fallback.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np


def require_open3d():
    try:
        import open3d as o3d
    except ImportError as exc:
        raise SystemExit(
            "Open3D is required for TSDF mesh fusion. Install it in the "
            "lingbot-map environment, for example: "
            "conda run -n lingbot-map python -m pip install open3d"
        ) from exc
    return o3d


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_metadata(archive: Path) -> dict:
    metadata_path = archive.with_suffix(".json")
    if metadata_path.is_file():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return {}


def resolve_preprocessed_dir(archive: Path, metadata: dict, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    value = metadata.get("preprocessed_image_dir")
    if value:
        return Path(value).resolve()
    candidate = archive.parent / "preprocessed"
    if candidate.is_dir():
        return candidate.resolve()
    raise FileNotFoundError("Cannot find preprocessed image directory for TSDF color integration.")


def resize_intrinsic(intrinsic: np.ndarray, from_wh: tuple[int, int], to_wh: tuple[int, int]) -> np.ndarray:
    if from_wh == to_wh:
        return intrinsic.astype(np.float64, copy=True)
    sx = to_wh[0] / from_wh[0]
    sy = to_wh[1] / from_wh[1]
    scaled = intrinsic.astype(np.float64, copy=True)
    scaled[0, 0] *= sx
    scaled[0, 2] *= sx
    scaled[1, 1] *= sy
    scaled[1, 2] *= sy
    return scaled


def load_color(path: Path, width: int, height: int) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise OSError(f"Cannot read color image: {path}")
    original_wh = (image.shape[1], image.shape[0])
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if image.shape[1] != width or image.shape[0] != height:
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return image, original_wh


def make_rgbd(o3d, color: np.ndarray, depth: np.ndarray, depth_trunc: float):
    depth = np.asarray(depth, dtype=np.float32)
    valid = np.isfinite(depth) & (depth > 0) & (depth <= depth_trunc)
    cleaned = np.where(valid, depth, 0.0).astype(np.float32)
    return o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(color.astype(np.uint8)),
        o3d.geometry.Image(cleaned),
        depth_scale=1.0,
        depth_trunc=depth_trunc,
        convert_rgb_to_intensity=False,
    )


def sampled_mesh_payload(mesh, frame_count: int, update_index: int, max_faces: int) -> dict:
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    colors = np.asarray(mesh.vertex_colors)
    if len(triangles) > max_faces:
        step = max(1, math.ceil(len(triangles) / max_faces))
        triangles = triangles[::step]
    else:
        step = 1
    if len(colors) != len(vertices):
        colors = np.full((len(vertices), 3), 0.72, dtype=np.float64)
    used = sorted({int(index) for face in triangles for index in face})
    remap = {old: new for new, old in enumerate(used)}
    preview_vertices = [
        [
            round(float(vertices[index, 0]), 4),
            round(float(vertices[index, 1]), 4),
            round(float(vertices[index, 2]), 4),
            int(np.clip(colors[index, 0] * 255.0, 0, 255)),
            int(np.clip(colors[index, 1] * 255.0, 0, 255)),
            int(np.clip(colors[index, 2] * 255.0, 0, 255)),
        ]
        for index in used
    ]
    preview_faces = [[remap[int(a)], remap[int(b)], remap[int(c)]] for a, b, c in triangles]
    if preview_vertices:
        arr = np.asarray(preview_vertices, dtype=np.float64)
        bounds = {
            "minX": float(arr[:, 0].min()), "maxX": float(arr[:, 0].max()),
            "minY": float(arr[:, 1].min()), "maxY": float(arr[:, 1].max()),
            "minZ": float(arr[:, 2].min()), "maxZ": float(arr[:, 2].max()),
        }
    else:
        bounds = {"minX": 0, "maxX": 1, "minY": 0, "maxY": 1, "minZ": 0, "maxZ": 1}
    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "frame_count": frame_count,
        "update_index": update_index,
        "source_vertices": int(len(vertices)),
        "source_faces": int(len(mesh.triangles)),
        "sample_stride": int(step),
        "vertices": preview_vertices,
        "faces": preview_faces,
        "bounds": bounds,
        "coordinate_hint": "LingBot world coordinates; viewer treats -Y as vertical.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output-mesh", required=True, type=Path)
    parser.add_argument("--preview-json", type=Path, default=None)
    parser.add_argument("--preprocessed-dir", type=Path, default=None)
    parser.add_argument("--max-frames", type=int, default=0, help="0 uses all frames in the archive.")
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--voxel-length", type=float, default=0.035)
    parser.add_argument("--sdf-trunc", type=float, default=0.12)
    parser.add_argument("--depth-trunc", type=float, default=8.0)
    parser.add_argument("--max-preview-faces", type=int, default=35000)
    parser.add_argument("--update-index", type=int, default=0)
    args = parser.parse_args()
    if args.frame_stride < 1:
        parser.error("--frame-stride must be positive")
    if args.voxel_length <= 0 or args.sdf_trunc <= 0 or args.depth_trunc <= 0:
        parser.error("TSDF numeric parameters must be positive")
    return args


def main() -> int:
    args = parse_args()
    o3d = require_open3d()
    archive = args.archive.resolve()
    data = np.load(archive, allow_pickle=True)
    if "depth" not in data:
        raise SystemExit("Archive does not contain depth; cannot run TSDF fusion.")
    depth = np.asarray(data["depth"], dtype=np.float32)
    intrinsics = np.asarray(data["intrinsic"], dtype=np.float64)
    extrinsics_c2w = np.asarray(data["extrinsic_c2w"], dtype=np.float64)
    frame_count = int(depth.shape[0])
    limit = frame_count if args.max_frames <= 0 else min(frame_count, args.max_frames)
    metadata = read_metadata(archive)
    preprocessed_dir = resolve_preprocessed_dir(archive, metadata, args.preprocessed_dir)

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=args.voxel_length,
        sdf_trunc=args.sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    integrated = 0
    for index in range(0, limit, args.frame_stride):
        depth_frame = depth[index]
        height, width = depth_frame.shape[:2]
        color_path = preprocessed_dir / f"{index:06d}.png"
        color, original_wh = load_color(color_path, width, height)
        intrinsic = resize_intrinsic(intrinsics[index], original_wh, (width, height))
        camera = o3d.camera.PinholeCameraIntrinsic(
            width, height,
            float(intrinsic[0, 0]), float(intrinsic[1, 1]),
            float(intrinsic[0, 2]), float(intrinsic[1, 2]),
        )
        c2w = np.eye(4, dtype=np.float64)
        c2w[:3, :4] = extrinsics_c2w[index]
        w2c = np.linalg.inv(c2w)
        volume.integrate(make_rgbd(o3d, color, depth_frame, args.depth_trunc), camera, w2c)
        integrated += 1

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    args.output_mesh.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(args.output_mesh.resolve()), mesh, write_ascii=False, compressed=False):
        raise OSError(f"Failed to write mesh: {args.output_mesh}")
    if args.preview_json is not None:
        payload = sampled_mesh_payload(mesh, integrated, args.update_index, args.max_preview_faces)
        payload["mesh_path"] = str(args.output_mesh.resolve())
        atomic_json(args.preview_json.resolve(), payload)
    print(f"Wrote {args.output_mesh.resolve()}")
    print(f"Integrated frames: {integrated}")
    print(f"Mesh vertices/faces: {len(mesh.vertices)} / {len(mesh.triangles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
