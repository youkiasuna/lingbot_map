#!/usr/bin/env python3
"""Localize one query image and render its camera pose in a 3D map viewer."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
if str(INTEGRATED_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATED_ROOT))

from experiments.orb_keyframe_localizer import OrbKeyframeLocalizer, result_to_pose  # noqa: E402
from localization.localizer_interface import FilePosePublisher  # noqa: E402


def load_archive(mapping_dir: Path) -> dict[str, np.ndarray]:
    archive_path = mapping_dir / "predictions.npz"
    if not archive_path.is_file():
        raise FileNotFoundError(f"Missing map archive: {archive_path}")
    with np.load(archive_path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def sample_world_points(archive: dict[str, np.ndarray], max_points: int, min_norm: float) -> list[list[float]]:
    world_points = np.asarray(archive["world_points"], dtype=np.float32)
    flat = world_points.reshape(-1, 3)
    valid = np.all(np.isfinite(flat), axis=1) & (np.linalg.norm(flat, axis=1) > min_norm)
    valid_points = flat[valid]
    if len(valid_points) == 0:
        return []
    if len(valid_points) > max_points:
        indices = np.linspace(0, len(valid_points) - 1, max_points, dtype=np.int64)
        valid_points = valid_points[indices]
    return np.round(valid_points.astype(np.float64), 5).tolist()


def camera_centers(archive: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    extrinsics = np.asarray(archive["extrinsic_c2w"], dtype=np.float64)
    centers: list[dict[str, Any]] = []
    for index, extrinsic in enumerate(extrinsics):
        centers.append(
            {
                "frame_index": index,
                "position": np.round(extrinsic[:, 3], 5).tolist(),
            }
        )
    return centers


def build_viewer_html(
    *,
    mapping_dir: Path,
    query_image: Path,
    points: list[list[float]],
    references: list[dict[str, Any]],
    result: dict[str, Any],
) -> str:
    best = result.get("best") if isinstance(result.get("best"), dict) else None
    payload = {
        "mapping_dir": str(mapping_dir),
        "query_image": str(query_image),
        "points": points,
        "references": references,
        "result": result,
        "query_camera": None if not best else best.get("position_xyz"),
        "best_frame": None if not best else best.get("frame_index"),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    title = html.escape(f"Query Camera Pose | {query_image.name}")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: #08100d; color: #edf7f0; font-family: system-ui, sans-serif; }}
#viewer {{ width: 100vw; height: 100vh; }}
#panel {{ position: fixed; left: 16px; top: 16px; width: min(380px, calc(100vw - 32px)); padding: 14px 16px; border: 1px solid #315344; border-radius: 8px; background: rgba(8, 16, 13, .92); box-shadow: 0 14px 34px rgba(0, 0, 0, .32); }}
#panel.panel-collapsed {{ width: 44px; height: 44px; padding: 5px; overflow: hidden; }}
#panel.panel-collapsed > :not(#collapsePanel) {{ display: none; }}
#collapsePanel {{ position: absolute; top: 5px; right: 5px; width: 32px; height: 32px; margin: 0; padding: 0; font-size: 18px; line-height: 1; }}
h1 {{ margin: 0 0 8px; font-size: 17px; font-weight: 700; letter-spacing: 0; }}
.meta {{ color: #b7c9be; font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }}
.status {{ display: inline-block; margin: 8px 0; padding: 3px 7px; border-radius: 6px; background: #163226; color: #8df0b7; font-size: 12px; }}
.legend {{ display: grid; gap: 5px; margin-top: 10px; color: #d7e7dc; font-size: 12px; }}
.row {{ display: flex; align-items: center; gap: 7px; }}
.swatch {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
button {{ margin: 10px 6px 0 0; padding: 7px 10px; border: 1px solid #49705f; border-radius: 6px; color: #edf7f0; background: #132b21; cursor: pointer; }}
button:hover {{ background: #1d3a2d; }}
</style>
</head>
<body>
<div id="viewer"></div>
<section id="panel">
  <button id="collapsePanel" type="button" title="收合工具列" aria-label="收合工具列">−</button>
  <h1>Query Camera Pose</h1>
  <div class="meta" id="summary"></div>
  <div class="status" id="status"></div>
  <div class="legend">
    <div class="row"><span class="swatch" style="background:#73d7ff"></span><span>3D map points</span></div>
    <div class="row"><span class="swatch" style="background:#b7c0ba"></span><span>mapping camera centers</span></div>
    <div class="row"><span class="swatch" style="background:#ffe45c"></span><span>best matched keyframe</span></div>
    <div class="row"><span class="swatch" style="background:#ff4d64"></span><span>query camera pose</span></div>
  </div>
  <button id="overview">斜角視角</button>
  <button id="top">俯視</button>
  <button id="focusQuery">定位相機</button>
</section>
<script type="importmap">
{{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}}}
</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';

const data = {payload_json};
const container = document.querySelector('#viewer');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x08100d);
const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.01, 100000);
const renderer = new THREE.WebGLRenderer({{antialias: true}});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
container.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const positions = new Float32Array(data.points.length * 3);
const colors = new Float32Array(data.points.length * 3);
for (let i = 0; i < data.points.length; i++) {{
  const p = data.points[i];
  positions[i * 3] = p[0];
  positions[i * 3 + 1] = p[1];
  positions[i * 3 + 2] = p[2];
  colors[i * 3] = 0.45;
  colors[i * 3 + 1] = 0.84;
  colors[i * 3 + 2] = 1.0;
}}
const pointGeometry = new THREE.BufferGeometry();
pointGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
pointGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
scene.add(new THREE.Points(pointGeometry, new THREE.PointsMaterial({{size: 0.018, vertexColors: true, sizeAttenuation: true}})));

const markerGroup = new THREE.Group();
scene.add(markerGroup);
const refMaterial = new THREE.MeshBasicMaterial({{color: 0xb7c0ba}});
const bestMaterial = new THREE.MeshBasicMaterial({{color: 0xffe45c}});
const queryMaterial = new THREE.MeshBasicMaterial({{color: 0xff4d64}});
function addMarker(position, material, radius, label) {{
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 10), material);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.userData.label = label;
  markerGroup.add(mesh);
  return mesh;
}}
const box = new THREE.Box3();
for (const p of data.points) box.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
for (const ref of data.references) box.expandByPoint(new THREE.Vector3(ref.position[0], ref.position[1], ref.position[2]));
if (data.query_camera) box.expandByPoint(new THREE.Vector3(data.query_camera[0], data.query_camera[1], data.query_camera[2]));
const center = box.getCenter(new THREE.Vector3());
const size = box.getSize(new THREE.Vector3());
const radius = Math.max(size.length() * 0.006, 0.015);
for (const ref of data.references) {{
  addMarker(ref.position, ref.frame_index === data.best_frame ? bestMaterial : refMaterial, radius, `frame ${{ref.frame_index}}`);
}}
let queryMarker = null;
if (data.query_camera) {{
  queryMarker = addMarker(data.query_camera, queryMaterial, radius * 2.0, 'query');
  const axes = new THREE.AxesHelper(radius * 8);
  axes.position.copy(queryMarker.position);
  axes.scale.y = -1;
  markerGroup.add(axes);
}}

const gridSize = Math.max(size.x, size.z, 0.5) * 1.2;
const grid = new THREE.GridHelper(gridSize, 20, 0x315344, 0x1b3028);
grid.position.y = center.y;
scene.add(grid);

const result = data.result;
const best = result.best || {{}};
document.querySelector('#summary').innerHTML =
  `query：${{data.query_image}}<br>` +
  `mapping：${{data.mapping_dir}}<br>` +
  `best frame：${{best.frame_index ?? 'none'}}<br>` +
  `matches：${{best.match_count ?? 0}}，inliers：${{best.inlier_count ?? 0}}，confidence：${{best.confidence ?? 0}}<br>` +
  `latency：${{result.latency_ms}} ms`;
document.querySelector('#status').textContent = result.status;

function setOverview() {{
  const distance = Math.max(size.length() * 0.9, 1.0);
  camera.up.set(0, -1, 0);
  camera.position.set(center.x + distance, center.y - distance * 0.65, center.z + distance);
  controls.target.copy(center);
  controls.update();
}}
function setTop() {{
  const distance = Math.max(size.length() * 0.9, 1.0);
  camera.up.set(0, -1, 0);
  camera.position.set(center.x, center.y - distance, center.z + 0.001);
  controls.target.copy(center);
  controls.update();
}}
function focusQuery() {{
  if (!queryMarker) return;
  const yaw = Number(best.yaw_deg ?? 0) * Math.PI / 180;
  const forward = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
  const lookDistance = Math.max(size.length() * 0.25, 0.5);
  camera.up.set(0, -1, 0);
  camera.position.copy(queryMarker.position);
  controls.target.copy(queryMarker.position).add(forward.multiplyScalar(lookDistance));
  camera.lookAt(controls.target);
  controls.update();
}}
document.querySelector('#overview').addEventListener('click', setOverview);
document.querySelector('#top').addEventListener('click', setTop);
document.querySelector('#focusQuery').addEventListener('click', focusQuery);
const collapsePanel = document.querySelector('#collapsePanel');
collapsePanel.addEventListener('click', () => {{
  const collapsed = document.querySelector('#panel').classList.toggle('panel-collapsed');
  collapsePanel.textContent = collapsed ? '+' : '−';
  collapsePanel.title = collapsed ? '展開工具列' : '收合工具列';
  collapsePanel.setAttribute('aria-label', collapsePanel.title);
}});
addEventListener('resize', () => {{
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}});
setOverview();
function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}
animate();
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--query-image", required=True, type=Path)
    parser.add_argument("--output-html", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--pose-file", type=Path)
    parser.add_argument("--max-viewer-points", type=int, default=60000)
    parser.add_argument("--min-world-norm", type=float, default=1e-6)
    parser.add_argument("--publish-min-confidence", type=float, default=0.35)
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--frame-stride", type=int, default=5)
    parser.add_argument("--ratio", type=float, default=0.75)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-matches", type=int, default=25)
    parser.add_argument("--min-inliers", type=int, default=12)
    parser.add_argument("--max-pnp-points", type=int, default=300)
    parser.add_argument("--reprojection-error-px", type=float, default=5.0)
    parser.add_argument("--pnp-iterations", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    localizer = OrbKeyframeLocalizer(
        mapping_dir=args.mapping_dir,
        max_features=args.max_features,
        frame_stride=args.frame_stride,
        ratio=args.ratio,
        top_k=args.top_k,
        min_matches=args.min_matches,
        min_inliers=args.min_inliers,
        max_pnp_points=args.max_pnp_points,
        reprojection_error_px=args.reprojection_error_px,
        pnp_iterations=args.pnp_iterations,
        min_world_norm=args.min_world_norm,
    )
    result = localizer.localize(args.query_image)
    archive = load_archive(args.mapping_dir)
    points = sample_world_points(archive, args.max_viewer_points, args.min_world_norm)
    references = camera_centers(archive)
    viewer_html = build_viewer_html(
        mapping_dir=args.mapping_dir,
        query_image=args.query_image,
        points=points,
        references=references,
        result=result,
    )

    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.write_text(viewer_html, encoding="utf-8")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.pose_file:
        pose = result_to_pose(result, args.publish_min_confidence)
        FilePosePublisher(args.pose_file).publish(pose)

    print(json.dumps({
        "status": result["status"],
        "best": result["best"],
        "viewer": str(args.output_html),
        "point_count": len(points),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
