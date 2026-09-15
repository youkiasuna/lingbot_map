#!/usr/bin/env python3
"""Colored point-cloud rendered-view localizer (方案 A baseline).

The query remains a normal RGB image. The colored PLY is projected from each
mapping camera pose into a sparse synthetic RGB view. ORB retrieval is then
performed against those rendered views, and the rendered pixel-to-point buffer
provides the 2D/3D correspondences for PnP.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path

import cv2
import numpy as np

INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
if str(INTEGRATED_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATED_ROOT))

from experiments.orb_keyframe_localizer import (  # noqa: E402
    confidence_score,
    extract_orb,
    match_descriptors,
    pose_from_pnp,
)


PLY_TYPES = {
    "char": "b", "int8": "b", "uchar": "B", "uint8": "B",
    "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
    "int": "i", "int32": "i", "uint": "I", "uint32": "I",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}


def read_ply_sample(path: Path, max_points: int) -> tuple[np.ndarray, np.ndarray, int]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError("Input is not a PLY file.")
        vertex_count = 0
        properties: list[tuple[str, str]] = []
        in_vertex = False
        while True:
            line = handle.readline().decode("ascii", errors="strict").strip()
            parts = line.split()
            if parts[0] == "format" and parts[1] != "binary_little_endian":
                raise ValueError("Only binary_little_endian PLY is supported.")
            if parts[0] == "element":
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    vertex_count = int(parts[2])
            elif parts[0] == "property" and in_vertex:
                if len(parts) != 3 or parts[1] not in PLY_TYPES:
                    raise ValueError("PLY contains an unsupported vertex property.")
                properties.append((parts[1], parts[2]))
            elif parts[0] == "end_header":
                break
        names = {name for _, name in properties}
        required = {"x", "y", "z", "red", "green", "blue"}
        if not required.issubset(names):
            raise ValueError("PLY must contain x/y/z and red/green/blue properties.")
        stride = max(1, math.ceil(vertex_count / max_points))
        fmt = struct.Struct("<" + "".join(PLY_TYPES[data_type] for data_type, _ in properties))
        indices = {name: index for index, (_, name) in enumerate(properties)}
        points: list[tuple[float, float, float]] = []
        colors: list[tuple[int, int, int]] = []
        for index in range(vertex_count):
            raw = handle.read(fmt.size)
            if len(raw) != fmt.size:
                raise ValueError("PLY vertex data ended unexpectedly.")
            if index % stride:
                continue
            values = fmt.unpack(raw)
            xyz = tuple(float(values[indices[name]]) for name in ("x", "y", "z"))
            if not all(math.isfinite(value) for value in xyz):
                continue
            points.append(xyz)
            colors.append(tuple(int(values[indices[name]]) for name in ("red", "green", "blue")))
    return np.asarray(points, dtype=np.float32), np.asarray(colors, dtype=np.uint8), stride


def render_view(
    points: np.ndarray,
    colors: np.ndarray,
    intrinsic: np.ndarray,
    extrinsic_c2w: np.ndarray,
    image_size: tuple[int, int],
    splat_radius: int,
) -> tuple[np.ndarray, np.ndarray]:
    width, height = image_size
    rotation = np.asarray(extrinsic_c2w[:, :3], dtype=np.float32)
    center = np.asarray(extrinsic_c2w[:, 3], dtype=np.float32)
    camera_points = (points - center) @ rotation
    depth = camera_points[:, 2]
    valid = depth > 0.05
    camera_points = camera_points[valid]
    point_indices = np.flatnonzero(valid)
    depth = depth[valid]
    pixels = camera_points @ intrinsic[:2, :3].T
    pixels[:, 0] /= depth
    pixels[:, 1] /= depth
    px = np.rint(pixels).astype(np.int32)
    valid = (px[:, 0] >= 0) & (px[:, 0] < width) & (px[:, 1] >= 0) & (px[:, 1] < height)
    px, depth, point_indices = px[valid], depth[valid], point_indices[valid]
    order = np.argsort(depth)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    ids = np.full((height, width), -1, dtype=np.int32)
    for order_index in order:
        x, y = px[order_index]
        for dy in range(-splat_radius, splat_radius + 1):
            for dx in range(-splat_radius, splat_radius + 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < width and 0 <= yy < height and ids[yy, xx] < 0:
                    point_index = point_indices[order_index]
                    ids[yy, xx] = int(point_index)
                    image[yy, xx] = colors[point_index]
    return image, ids


def localize(query_path: Path, points, colors, intrinsics, extrinsics, image_size, stride, args):
    width, height = image_size
    query = cv2.imread(str(query_path), cv2.IMREAD_COLOR)
    if query is None:
        raise ValueError(f"Failed to read query image: {query_path}")
    query = cv2.resize(query, (width, height), interpolation=cv2.INTER_AREA)
    query_xy, query_descriptors = extract_orb(query, args.max_features)
    started = time.perf_counter()
    candidates = []
    for frame_index, (intrinsic, extrinsic) in enumerate(zip(intrinsics, extrinsics)):
        rendered, point_ids = render_view(points, colors, intrinsic, extrinsic, (width, height), args.splat_radius)
        ref_xy, ref_descriptors = extract_orb(rendered, args.max_features)
        matches = match_descriptors(query_descriptors, ref_descriptors, args.ratio)
        object_points, image_points = [], []
        for match in matches[:args.max_pnp_points]:
            rx, ry = np.rint(ref_xy[match.trainIdx]).astype(int)
            if not (0 <= rx < width and 0 <= ry < height):
                continue
            point_id = int(point_ids[ry, rx])
            if point_id < 0:
                continue
            object_points.append(points[point_id])
            image_points.append(query_xy[match.queryIdx])
        object_points = np.asarray(object_points, dtype=np.float32)
        image_points = np.asarray(image_points, dtype=np.float32)
        pnp = None
        if len(matches) >= args.min_matches:
            pnp = pose_from_pnp(object_points, image_points, intrinsic, args.reprojection_error_px, args.pnp_iterations)
        if pnp is None:
            position = yaw = reprojection = None
            inlier_count = 0
            pnp_status = "not_enough_geometry"
        else:
            center, yaw, inlier_count, reprojection = pnp
            position = [round(float(value), 5) for value in center]
            pnp_status = "ok" if inlier_count >= args.min_inliers else "low_inliers"
        confidence = confidence_score(len(matches), inlier_count, reprojection, args.min_inliers)
        candidates.append({
            "frame_index": frame_index,
            "match_count": len(matches),
            "inlier_count": inlier_count,
            "reprojection_error_px": None if reprojection is None else round(float(reprojection), 4),
            "confidence": confidence,
            "position_xyz": position,
            "yaw_deg": None if yaw is None else round(float(yaw), 2),
            "pnp_status": pnp_status,
        })
    candidates.sort(key=lambda item: (item["confidence"], item["inlier_count"], item["match_count"]), reverse=True)
    best = candidates[0] if candidates else None
    status = "localized" if best and best["pnp_status"] == "ok" else "low_confidence"
    return {
        "schema_version": 1,
        "method": "colored_pointcloud_render_orb_pnp",
        "query_image": str(query_path),
        "status": status,
        "best": best,
        "candidates": candidates[:args.top_k],
        "point_count": int(len(points)),
        "ply_stride": stride,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "coordinate_note": "PLY and predictions.npz must use the same reconstruction coordinate frame; use raw dense PLY, not floor-calibrated PLY.",
    }


def build_colored_viewer_html(
    *, mapping_dir: Path, query_image: Path, points: np.ndarray,
    colors: np.ndarray, extrinsics: np.ndarray, result: dict,
) -> str:
    best = result.get("best") if isinstance(result.get("best"), dict) else None
    references = [
        {
            "frame_index": index,
            "position": np.round(extrinsic[:, 3], 5).tolist(),
            "rotation": np.round(extrinsic[:, :3], 5).tolist(),
        }
        for index, extrinsic in enumerate(extrinsics)
    ]
    payload = {
        "points": np.round(points, 5).tolist(),
        "colors": colors.tolist(),
        "references": references,
        "result": result,
        "query_camera": None if not best else best.get("position_xyz"),
        "best_frame": None if not best else best.get("frame_index"),
        "query_image": str(query_image),
        "mapping_dir": str(mapping_dir),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>彩色 3D 點雲定位 | {query_image.name}</title>
<style>
* {{ box-sizing: border-box; }}
html,body,#viewer {{ margin:0;width:100%;height:100%;overflow:hidden;background:#08100d;color:#edf7f0;font-family:system-ui,sans-serif; }}
#panel {{ position:fixed;left:16px;top:16px;width:min(410px,calc(100vw - 32px));padding:15px 17px;border:1px solid #496b5d;border-radius:8px;background:rgba(8,16,13,.93);box-shadow:0 14px 34px rgba(0,0,0,.32); }}
#panel.panel-collapsed {{ width:44px;height:44px;padding:5px;overflow:hidden; }}
#panel.panel-collapsed > :not(#collapsePanel) {{ display:none; }}
#collapsePanel {{ position:absolute;top:5px;right:5px;width:32px;height:32px;margin:0;padding:0;font-size:18px;line-height:1; }}
h1 {{ margin:0 0 8px;font-size:18px; }} .meta {{ color:#b7c9be;font-size:12px;line-height:1.55;overflow-wrap:anywhere; }}
.status {{ display:inline-block;margin:8px 0;padding:3px 7px;border-radius:5px;background:#163226;color:#8df0b7;font-size:12px; }}
button {{ margin:10px 6px 0 0;padding:8px 10px;border:1px solid #49705f;border-radius:6px;color:#edf7f0;background:#132b21;cursor:pointer; }}
button:hover {{ background:#1d3a2d; }} .legend {{ margin-top:10px;color:#d7e7dc;font-size:12px;line-height:1.6; }}
</style></head>
<body><div id="viewer"></div><section id="panel"><button id="collapsePanel" type="button" title="收合工具列" aria-label="收合工具列">−</button>
<h1>彩色 3D 點雲定位</h1><div class="meta" id="summary"></div><div class="status" id="status"></div>
<div class="legend">彩色點雲：PLY RGB<br>黃色：最符合影像的 mapping camera<br>紅色：query 定位相機</div>
<button id="overview">總覽</button><button id="focusQuery">定位相機</button><button id="matchingView">符合影像視角</button>
</section>
<script type="importmap">{{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}}}</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';
const data={data}; const scene=new THREE.Scene(); scene.background=new THREE.Color(0x08100d);
const camera=new THREE.PerspectiveCamera(55,innerWidth/innerHeight,.01,100000);
const renderer=new THREE.WebGLRenderer({{antialias:true}}); renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.setSize(innerWidth,innerHeight); document.querySelector('#viewer').appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true;
const positions=new Float32Array(data.points.length*3), colors=new Float32Array(data.colors.length*3);
for(let i=0;i<data.points.length;i++){{ positions.set(data.points[i],i*3); colors[i*3]=data.colors[i][0]/255; colors[i*3+1]=data.colors[i][1]/255; colors[i*3+2]=data.colors[i][2]/255; }}
const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.BufferAttribute(positions,3)); geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
const cloud=new THREE.Points(geometry,new THREE.PointsMaterial({{size:.018,vertexColors:true,sizeAttenuation:true}})); scene.add(cloud);
const box=new THREE.Box3().setFromObject(cloud), center=box.getCenter(new THREE.Vector3()), size=box.getSize(new THREE.Vector3());
const radius=Math.max(size.length()*.65,.5), markers=new THREE.Group(); scene.add(markers);
function marker(p,color,r){{const m=new THREE.Mesh(new THREE.SphereGeometry(r,16,10),new THREE.MeshBasicMaterial({{color}}));m.position.fromArray(p);markers.add(m);return m;}}
for(const ref of data.references) marker(ref.position,ref.frame_index===data.best_frame?0xffe45c:0x82958c,Math.max(radius*.012,.018));
let queryMarker=null; if(data.query_camera) queryMarker=marker(data.query_camera,0xff405d,Math.max(radius*.025,.035));
function overview(){{camera.position.set(center.x+radius,center.y-radius*.7,center.z+radius);camera.up.set(0,-1,0);controls.target.copy(center);controls.update();}}
function focusQuery(){{if(!queryMarker)return;const p=queryMarker.position;const yaw=Number(data.result.best?.yaw_deg??0)*Math.PI/180;const forward=new THREE.Vector3(Math.sin(yaw),0,Math.cos(yaw));const lookDistance=Math.max(radius*.25,.5);camera.position.copy(p);camera.up.set(0,-1,0);controls.target.copy(p).add(forward.multiplyScalar(lookDistance));camera.lookAt(controls.target);controls.update();}}
function matchingView(){{const ref=data.references.find(item=>item.frame_index===data.best_frame);if(!ref)return;const p=new THREE.Vector3().fromArray(ref.position);const r=ref.rotation;const forward=new THREE.Vector3(r[0][2],r[1][2],r[2][2]).normalize();camera.position.copy(p);camera.up.set(0,-1,0);controls.target.copy(p).add(forward.multiplyScalar(Math.max(radius*.18,.3)));camera.lookAt(controls.target);controls.update();document.querySelector('#status').textContent=`目前視角：frame ${{data.best_frame}}（最符合 query 影像）`;}}
document.querySelector('#summary').innerHTML=`query：${{data.query_image}}<br>mapping：${{data.mapping_dir}}<br>best frame：${{data.best_frame??'none'}}<br>matches：${{data.result.best?.match_count??0}}，inliers：${{data.result.best?.inlier_count??0}}，confidence：${{data.result.best?.confidence??0}}<br>latency：${{data.result.latency_ms}} ms`;
document.querySelector('#status').textContent=`定位狀態：${{data.result.status}}`;document.querySelector('#overview').onclick=overview;document.querySelector('#focusQuery').onclick=focusQuery;document.querySelector('#matchingView').onclick=matchingView;
const collapsePanel=document.querySelector('#collapsePanel');collapsePanel.onclick=()=>{{const collapsed=document.querySelector('#panel').classList.toggle('panel-collapsed');collapsePanel.textContent=collapsed?'+':'−';collapsePanel.title=collapsed?'展開工具列':'收合工具列';collapsePanel.setAttribute('aria-label',collapsePanel.title);}};
addEventListener('resize',()=>{{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);}}); overview();
function animate(){{requestAnimationFrame(animate);controls.update();renderer.render(scene,camera);}} animate();
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ply", required=True, type=Path)
    parser.add_argument("--mapping-dir", required=True, type=Path)
    parser.add_argument("--query-image", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-html", type=Path, help="Optional 3D pose viewer output")
    parser.add_argument("--max-points", type=int, default=150_000)
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--splat-radius", type=int, default=2)
    parser.add_argument("--ratio", type=float, default=0.75)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-matches", type=int, default=25)
    parser.add_argument("--min-inliers", type=int, default=12)
    parser.add_argument("--max-pnp-points", type=int, default=300)
    parser.add_argument("--reprojection-error-px", type=float, default=5.0)
    parser.add_argument("--pnp-iterations", type=int, default=200)
    args = parser.parse_args()
    with np.load(args.mapping_dir / "predictions.npz", allow_pickle=False) as archive:
        intrinsics = archive["intrinsic"]
        extrinsics = archive["extrinsic_c2w"]
        image_size = (int(archive["world_points"].shape[2]), int(archive["world_points"].shape[1]))
    points, colors, stride = read_ply_sample(args.ply, args.max_points)
    result = localize(args.query_image, points, colors, intrinsics, extrinsics, image_size, stride, args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.output_html:
        args.output_html.parent.mkdir(parents=True, exist_ok=True)
        args.output_html.write_text(
            build_colored_viewer_html(
                mapping_dir=args.mapping_dir,
                query_image=args.query_image,
                points=points,
                colors=colors,
                extrinsics=extrinsics,
                result=result,
            ),
            encoding="utf-8",
        )
    print(json.dumps({"status": result["status"], "best": result["best"], "output": str(args.output_json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
