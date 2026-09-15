#!/usr/bin/env python3
"""Export a browser-based height-colored 3D viewer for the 20260818 point cloud.

The source PLY contains hundreds of millions of points, so this exporter uses a
stable stride sample. The browser receives a compact JSON payload and renders it
with Three.js. Height is mapped from blue (low) through green/yellow to red
(high), while the estimated floor height is shown as a reference plane.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import struct
from pathlib import Path
from typing import BinaryIO

PLY_TYPES = {
    "char": "b", "int8": "b", "uchar": "B", "uint8": "B",
    "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
    "int": "i", "int32": "i", "uint": "I", "uint32": "I",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}


def read_header(handle: BinaryIO) -> tuple[str, int, list[tuple[str, str]]]:
    if handle.readline().decode("ascii", errors="strict").strip() != "ply":
        raise ValueError("The input is not a PLY file.")
    file_format = ""
    vertex_count = 0
    properties: list[tuple[str, str]] = []
    in_vertices = False
    while True:
        line = handle.readline().decode("ascii", errors="strict").strip()
        if not line:
            raise ValueError("PLY header ended unexpectedly.")
        parts = line.split()
        if parts[0] == "format":
            file_format = parts[1]
        elif parts[0] == "element":
            in_vertices = parts[1] == "vertex"
            if in_vertices:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertices:
            if len(parts) != 3 or parts[1] == "list" or parts[1] not in PLY_TYPES:
                raise ValueError("Only scalar supported PLY vertex properties are supported.")
            properties.append((parts[1], parts[2]))
        elif parts[0] == "end_header":
            break
    if file_format != "binary_little_endian":
        raise ValueError("This exporter currently requires binary_little_endian PLY.")
    names = {name for _, name in properties}
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError("PLY vertices must contain x, y, and z properties.")
    return file_format, vertex_count, properties


def read_sample(ply_path: Path, max_points: int) -> tuple[list[tuple[float, float, float]], int]:
    with ply_path.open("rb") as handle:
        _, vertex_count, properties = read_header(handle)
        if max_points < 1:
            raise ValueError("max_points must be positive")
        stride = max(1, math.ceil(vertex_count / max_points))
        indices = {"x": 0, "y": 0, "z": 0}
        for index, (_, name) in enumerate(properties):
            if name in indices:
                indices[name] = index
        fmt = "<" + "".join(PLY_TYPES[data_type] for data_type, _ in properties)
        row_size = struct.calcsize(fmt)
        unpack = struct.Struct(fmt).unpack
        points: list[tuple[float, float, float]] = []
        for vertex_index in range(vertex_count):
            raw = handle.read(row_size)
            if len(raw) != row_size:
                raise ValueError("Unexpected end of binary vertex data.")
            if vertex_index % stride != 0:
                continue
            values = unpack(raw)
            points.append((
                float(values[indices["x"]]),
                float(values[indices["y"]]),
                float(values[indices["z"]]),
            ))
    return points, stride


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


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


def plane_from_points(a, b, c):
    try:
        normal = normalize(cross(
            (b[0] - a[0], b[1] - a[1], b[2] - a[2]),
            (c[0] - a[0], c[1] - a[1], c[2] - a[2]),
        ))
    except ValueError:
        return None
    return (*normal, -sum(normal[index] * a[index] for index in range(3)))


def auto_orient_points(points, threshold: float = 0.05, iterations: int = 400):
    """Fit the dominant scan plane and convert the sampled cloud to Y-up."""
    if len(points) < 3:
        raise ValueError("At least three points are required for automatic orientation.")
    fit_points = points[::max(1, math.ceil(len(points) / 5_000))]
    rng = random.Random(20260818)
    best_plane = None
    best_inliers = []
    for _ in range(iterations):
        plane = plane_from_points(*rng.sample(fit_points, 3))
        if plane is None:
            continue
        a, b, c, d = plane
        inliers = [
            index for index, point in enumerate(fit_points)
            if abs(a * point[0] + b * point[1] + c * point[2] + d) <= threshold
        ]
        if len(inliers) > len(best_inliers):
            best_plane, best_inliers = plane, inliers
    if best_plane is None or len(best_inliers) < 3:
        raise ValueError("Automatic floor detection could not find a dominant plane.")

    normal = best_plane[:3]
    centroid = tuple(sum(point[index] for point in fit_points) / len(fit_points) for index in range(3))
    if sum(normal[index] * centroid[index] for index in range(3)) + best_plane[3] < 0:
        normal = tuple(-value for value in normal)

    target = (0.0, 1.0, 0.0)
    rotation_axis = cross(normal, target)
    axis_length = math.sqrt(sum(value * value for value in rotation_axis))
    dot = max(-1.0, min(1.0, sum(normal[index] * target[index] for index in range(3))))
    if axis_length < 1e-9:
        axis, angle = (1.0, 0.0, 0.0), (0.0 if dot > 0 else math.pi)
    else:
        axis, angle = tuple(value / axis_length for value in rotation_axis), math.acos(dot)
    cosine, sine = math.cos(angle), math.sin(angle)

    def rotate(point):
        dot_product = sum(point[index] * axis[index] for index in range(3))
        cross_value = cross(axis, point)
        return tuple(
            point[index] * cosine + cross_value[index] * sine
            + axis[index] * dot_product * (1.0 - cosine)
            for index in range(3)
        )

    rotated = [rotate(point) for point in points]
    rotated_fit = [rotate(point) for point in fit_points]
    floor_height = percentile([rotated_fit[index][1] for index in best_inliers], 0.5)
    transformed = [(point[0], point[1] - floor_height, point[2]) for point in rotated]
    return transformed, normal, len(best_inliers)


def build_html(
    points: list[tuple[float, float, float]],
    source_name: str,
    stride: int,
    up_axis: str,
    floor_height_override: float | None = None,
    path: list[dict[str, float]] | None = None,
) -> str:
    date_match = re.search(r"20\d{6}", source_name)
    scan_name = date_match.group(0) if date_match else "Point Cloud"
    height_index = "xyz".index(up_axis[-1])
    height_sign = -1 if up_axis.startswith("-") else 1
    plane_axes = "/".join(axis.upper() for axis in "xyz" if axis != up_axis[-1])
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    heights = [height_sign * point[height_index] for point in points]
    floor_height = floor_height_override if floor_height_override is not None else percentile(heights, 0.05)
    floor_coordinate = floor_height / height_sign
    payload = json.dumps({"points": points, "floor_height": floor_height, "floor_coordinate": floor_coordinate, "height_index": height_index, "height_sign": height_sign, "up_axis": up_axis, "path": path or []}, separators=(",", ":"))
    title = html.escape(f"{scan_name} Height Color 3D | {len(points):,} points")
    return f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: #071018; font-family: system-ui, sans-serif; }}
#viewer {{ width: 100%; height: 100%; }}
#panel {{ position: fixed; top: 16px; left: 16px; width: min(330px, calc(100vw - 32px)); padding: 14px 16px; border: 1px solid #29404c; border-radius: 10px; background: rgba(7, 16, 24, .9); box-shadow: 0 10px 30px rgba(0,0,0,.3); }}
#panel.panel-collapsed {{ width: 44px; height: 44px; padding: 5px; overflow: hidden; }}
#panel.panel-collapsed > :not(#collapsePanel) {{ display: none; }}
#collapsePanel {{ position: absolute; top: 5px; right: 5px; width: 32px; height: 32px; margin: 0; padding: 0; font-size: 18px; line-height: 1; }}
h1 {{ margin: 0 0 8px; font-size: 17px; }}
.meta {{ color: #a8c0ca; font-size: 12px; line-height: 1.5; }}
label {{ display: block; margin-top: 12px; color: #d9e8ec; font-size: 13px; }}
input[type=range] {{ width: 100%; accent-color: #61d4ff; }}
button {{ margin: 10px 6px 0 0; padding: 7px 10px; border: 1px solid #3b6575; border-radius: 6px; background: #102936; color: #eaf7fa; cursor: pointer; }}
button:hover {{ background: #184354; }}
.hint {{ margin-top: 8px; color: #8faeb8; font-size: 11px; line-height: 1.4; }}
.legend {{ height: 12px; margin-top: 12px; border-radius: 3px; background: linear-gradient(90deg, #2455d6, #16b9aa, #38b95d, #f0c52e, #d7191c); }}
.legend-labels {{ display: flex; justify-content: space-between; color: #a8c0ca; font-size: 11px; }}
#status {{ margin-top: 9px; color: #8fe3bd; font-size: 12px; }}
</style>
</head>
<body>
<div id="viewer"></div>
<section id="panel">
  <button id="collapsePanel" type="button" title="收合工具列" aria-label="收合工具列">−</button>
    <h1>{scan_name} 高度著色 3D 點雲</h1>
    <div class="meta">來源：{html.escape(source_name)}<br>抽樣：每 {stride:,} 個原始點取 1 點，共 {len(points):,} 點<br>垂直軸：{up_axis.upper()}；藍色較低，紅色較高；地板估計高度：{floor_height:.3f}</div>
  <div class="legend"></div>
    <div class="legend-labels"><span>低於地板</span><span>地板：綠</span><span>高處：紅</span></div>
  <label>點大小 <input id="pointSize" type="range" min="0.006" max="0.08" step="0.001" value="0.018"></label>
  <button id="overview">斜角視角</button><button id="top">俯視</button><button id="reset">重設</button>
    <div id="status">正在載入 3D 場景...</div>
    <div class="meta">座標：{plane_axes} 為地面平面，{up_axis.upper()} 向上</div>
    <div class="hint">按住 Shift 點擊任意點，設定新的旋轉中心</div>
</section>
<script type="importmap">
{{"imports": {{"three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}}}
</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';
const data = {payload};
const container = document.querySelector('#viewer');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x071018);
const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.01, 100000);
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
container.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const positions = new Float32Array(data.points.length * 3);
const colors = new Float32Array(data.points.length * 3);
let minHeight = Infinity, maxHeight = -Infinity;
for (const point of data.points) {{ const height = data.height_sign * point[data.height_index]; minHeight = Math.min(minHeight, height); maxHeight = Math.max(maxHeight, height); }}
function heightColor(value) {{
    const floorBand = 0.08;
    const redHeightRange = 0.45;
    let hue;
    if (value >= data.floor_height) {{
        const t = Math.max(0, Math.min(1, (value - data.floor_height) / redHeightRange));
        hue = 0.33 * (1 - t);
    }} else {{
        const t = Math.max(0, Math.min(1, (data.floor_height - value) / Math.max(data.floor_height - minHeight, 1e-6)));
        hue = 0.33 + 0.25 * t;
    }}
  const color = new THREE.Color();
    color.setHSL(hue, 0.86, Math.abs(value - data.floor_height) <= floorBand ? 0.48 : 0.52);
  return color;
}}
for (let i = 0; i < data.points.length; i++) {{
    const [x, y, z] = data.points[i];
  positions[i * 3] = x; positions[i * 3 + 1] = y; positions[i * 3 + 2] = z;
    const color = heightColor(data.height_sign * data.points[i][data.height_index]);
  colors[i * 3] = color.r; colors[i * 3 + 1] = color.g; colors[i * 3 + 2] = color.b;
}}
const geometry = new THREE.BufferGeometry();
geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
const material = new THREE.PointsMaterial({{ size: 0.018, vertexColors: true, sizeAttenuation: true }});
const cloud = new THREE.Points(geometry, material);
scene.add(cloud);
renderer.domElement.addEventListener('pointerdown', (event) => {{
    if (!event.shiftKey || event.button !== 0) return;
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObject(cloud, false);
    if (!hits.length) return;
    const target = hits[0].point;
    controls.target.copy(target);
    controls.update();
    document.querySelector('#status').textContent = `旋轉中心已設定：X=${{target.x.toFixed(3)}} Y=${{target.y.toFixed(3)}} Z=${{target.z.toFixed(3)}}`;
}});
const box = new THREE.Box3().setFromObject(cloud);
const center = box.getCenter(new THREE.Vector3());
const size = box.getSize(new THREE.Vector3());
const radius = Math.max(size.length() * 0.65, 0.5);
const upDirection = new THREE.Vector3();
upDirection.setComponent(data.height_index, data.height_sign);
const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(Math.max(size.x, size.y, size.z) * 1.2, Math.max(size.x, size.y, size.z) * 1.2),
    new THREE.MeshBasicMaterial({{ color: 0x3fae68, transparent: true, opacity: 0.12, side: THREE.DoubleSide }})
);
if (data.height_index === 0) {{ floor.rotation.y = Math.PI / 2; floor.position.x = data.floor_coordinate; }}
if (data.height_index === 1) {{ floor.rotation.x = Math.PI / 2; floor.position.y = data.floor_coordinate; }}
if (data.height_index === 2) {{ floor.position.z = data.floor_coordinate; }}
scene.add(floor);
const grid = new THREE.GridHelper(Math.max(size.x, size.y, size.z) * 1.1, 20, 0x47717d, 0x23404a);
if (data.height_index === 0) {{ grid.rotation.z = Math.PI / 2; grid.position.x = data.floor_coordinate + data.height_sign * 0.002; }}
if (data.height_index === 1) {{ grid.position.y = data.floor_coordinate + data.height_sign * 0.002; }}
if (data.height_index === 2) {{ grid.rotation.x = Math.PI / 2; grid.position.z = data.floor_coordinate + data.height_sign * 0.002; }}
scene.add(grid);
const axes = new THREE.AxesHelper(Math.max(size.x, size.y, size.z) * 0.18);
axes.position.copy(center);
axes.position.setComponent(data.height_index, data.floor_coordinate);
axes.scale.setComponent(data.height_index, data.height_sign);
scene.add(axes);
if (data.path.length > 0) {{
    const horizontal = [0, 1, 2].filter((index) => index !== data.height_index);
    const pathPositions = [];
    for (const pose of data.path) {{
        const point = [0, 0, 0];
        point[horizontal[0]] = pose.x_m;
        point[horizontal[1]] = pose.y_m;
        point[data.height_index] = data.floor_coordinate;
        pathPositions.push(...point);
    }}
    const pathGeometry = new THREE.BufferGeometry();
    pathGeometry.setAttribute('position', new THREE.Float32BufferAttribute(pathPositions, 3));
    scene.add(new THREE.Line(pathGeometry, new THREE.LineBasicMaterial({{ color: 0xff2d55, linewidth: 3 }})));
    const markerGeometry = new THREE.SphereGeometry(Math.max(radius * 0.035, 0.02), 12, 8);
    const startMarker = new THREE.Mesh(markerGeometry, new THREE.MeshBasicMaterial({{ color: 0x35e57b }}));
    const endMarker = new THREE.Mesh(markerGeometry, new THREE.MeshBasicMaterial({{ color: 0xff2d55 }}));
    startMarker.position.fromArray(pathPositions.slice(0, 3));
    endMarker.position.fromArray(pathPositions.slice(-3));
    scene.add(startMarker, endMarker);
}}
function setView(direction) {{
  camera.position.copy(center).add(direction.clone().normalize().multiplyScalar(radius));
  camera.near = Math.max(radius / 1000, 0.001); camera.far = radius * 10; camera.updateProjectionMatrix();
    camera.up.copy(upDirection);
    controls.target.copy(center); controls.update();
}}
const overviewDirection = new THREE.Vector3(0.8, 0.8, 0.8);
overviewDirection.setComponent(data.height_index, data.height_sign * 1.1);
setView(overviewDirection);
document.querySelector('#overview').onclick = () => setView(overviewDirection);
document.querySelector('#top').onclick = () => setView(upDirection);
document.querySelector('#reset').onclick = () => {{ controls.reset(); setView(overviewDirection); }};
document.querySelector('#pointSize').oninput = (event) => material.size = Number(event.target.value);
const collapsePanel = document.querySelector('#collapsePanel');
collapsePanel.onclick = () => {{
  const collapsed = document.querySelector('#panel').classList.toggle('panel-collapsed');
  collapsePanel.textContent = collapsed ? '+' : '−';
  collapsePanel.title = collapsed ? '展開工具列' : '收合工具列';
  collapsePanel.setAttribute('aria-label', collapsePanel.title);
}};
document.querySelector('#status').textContent = `場景完成：${{data.up_axis.toUpperCase()}} 軸高度 ${{minHeight.toFixed(3)}} 到 ${{maxHeight.toFixed(3)}}，地板估計 ${{data.floor_height.toFixed(3)}}`;
addEventListener('resize', () => {{ camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); }});
function animate() {{ requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }}
animate();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Export 20260818 point cloud as a height-colored web viewer.")
    parser.add_argument("--ply", type=Path, default=Path("outputs/maps/20260818_dense.ply"))
    parser.add_argument("--output", type=Path, default=Path("outputs/maps/20260818_height_color_viewer.html"))
    parser.add_argument("--max-points", type=int, default=250_000, help="Maximum sampled points embedded in HTML")
    parser.add_argument("--up-axis", choices=("auto", "x", "-x", "y", "-y", "z", "-z"), default="auto", help="Vertical axis; auto detects the dominant floor plane and converts to Y-up")
    parser.add_argument("--floor-fit-threshold", type=float, default=0.05, help="RANSAC floor-plane distance threshold in point-cloud units")
    parser.add_argument("--floor-height", type=float, default=None, help="Override the displayed floor reference height")
    parser.add_argument("--path-json", type=Path, default=None, help="Optional simulated_vehicle_path.json to draw")
    args = parser.parse_args()
    if not args.ply.exists():
        raise SystemExit(f"PLY file not found: {args.ply}")
    print(f"Sampling up to {args.max_points:,} points from {args.ply}...")
    points, stride = read_sample(args.ply, args.max_points)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    path = None
    if args.path_json is not None:
        path_payload = json.loads(args.path_json.read_text(encoding="utf-8"))
        path = path_payload.get("trajectory")
    if args.up_axis == "auto":
        points, normal, inlier_count = auto_orient_points(points, threshold=args.floor_fit_threshold)
        print(f"Detected floor normal {normal}; inliers {inlier_count:,}; exported canonical Y-up scene.")
        html_text = build_html(points, str(args.ply), stride, "y", 0.0, path)
    else:
        html_text = build_html(points, str(args.ply), stride, args.up_axis, args.floor_height, path)
    args.output.write_text(html_text, encoding="utf-8")
    print(f"Wrote {len(points):,} sampled points (stride {stride:,}) to {args.output}")


if __name__ == "__main__":
    main()
