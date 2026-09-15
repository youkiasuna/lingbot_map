#!/usr/bin/env python3
"""Export a self-contained 3D top-view viewer for online replay snapshots."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPLAY_DIR = ROOT / "outputs/scenes/scene_20260818/online_replay"
ROW = struct.Struct("<fffBBBf")


def read_snapshot(path: Path, max_points: int) -> list[list[float | int]]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"ply":
            raise ValueError(f"{path} is not a PLY file.")
        count = 0
        while True:
            line = handle.readline().decode("ascii", errors="strict").strip()
            if line.startswith("element vertex "):
                count = int(line.split()[2])
            if line == "end_header":
                break
        step = max(1, math.ceil(count / max_points))
        points: list[list[float | int]] = []
        for index in range(count):
            raw = handle.read(ROW.size)
            if len(raw) != ROW.size:
                raise ValueError(f"{path} ended unexpectedly.")
            if index % step != 0:
                continue
            x, y, z, red, green, blue, conf = ROW.unpack(raw)
            height = -y
            points.append([round(x, 4), round(z, 4), round(height, 4), red, green, blue])
    return points


def load_frames(replay_dir: Path, max_points: int) -> list[dict[str, object]]:
    frames = []
    for snapshot_path in sorted(replay_dir.glob("frame_*/snapshot.ply")):
        frame_dir = snapshot_path.parent
        metadata_path = frame_dir / "map.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        counts = metadata.get("counts", {})
        frames.append(
            {
                "name": frame_dir.name,
                "frame": int(frame_dir.name.rsplit("_", 1)[1]),
                "points": read_snapshot(snapshot_path, max_points),
                "free": counts.get("free_cells", 0),
                "occupied": counts.get("occupied_cells", 0),
                "unknown": counts.get("unknown_cells", 0),
                "components": counts.get("free_components", 0),
                "largest": counts.get("largest_free_component_cells", 0),
            }
        )
    if not frames:
        raise ValueError(f"No frame_*/snapshot.ply files found under {replay_dir}")
    return frames


def bounds(frames: list[dict[str, object]]) -> dict[str, float]:
    xs: list[float] = []
    zs: list[float] = []
    hs: list[float] = []
    for frame in frames:
        for x, z, h, *_ in frame["points"]:  # type: ignore[index]
            xs.append(float(x))
            zs.append(float(z))
            hs.append(float(h))
    return {
        "minX": min(xs),
        "maxX": max(xs),
        "minZ": min(zs),
        "maxZ": max(zs),
        "minH": min(hs),
        "maxH": max(hs),
    }


def write_html(frames: list[dict[str, object]], replay_bounds: dict[str, float], output: Path) -> None:
    payload = json.dumps({"frames": frames, "bounds": replay_bounds}, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Online 3D Top View</title>
<style>
:root {{ color-scheme: light; --bg:#f3f5f6; --panel:#fff; --text:#172026; --muted:#65717a; --line:#ccd5db; --accent:#087f8c; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; }}
header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; background: var(--panel); border-bottom: 1px solid var(--line); }}
h1 {{ margin: 0; font-size: 18px; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; padding: 16px; }}
canvas {{ width: 100%; height: calc(100vh - 96px); min-height: 520px; background: #d6dde1; border: 1px solid var(--line); border-radius: 8px; }}
.panel {{ align-self: start; display: grid; gap: 14px; padding: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
label {{ display: grid; gap: 8px; color: var(--muted); font-size: 13px; }}
input[type=range] {{ width: 100%; }}
button {{ height: 36px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text); font: inherit; cursor: pointer; }}
button:hover {{ border-color: var(--accent); }}
.stats {{ display: grid; gap: 10px; }}
.stat {{ border-top: 1px solid var(--line); padding-top: 10px; display: grid; gap: 3px; }}
.stat span {{ color: var(--muted); font-size: 12px; }}
.stat strong {{ font-size: 15px; }}
.legend {{ display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
.swatch {{ display: inline-block; width: 12px; height: 12px; margin-right: 4px; vertical-align: -2px; border: 1px solid #9aa5ab; }}
@media(max-width: 860px) {{ main {{ grid-template-columns: 1fr; }} canvas {{ height: 58vh; min-height: 360px; }} }}
</style>
</head>
<body>
<header><h1>Online Mapping 3D Top View</h1><span id="subtitle"></span></header>
<main>
  <canvas id="view"></canvas>
  <aside class="panel">
    <label>Frame <input id="frame" type="range" min="0" value="0" step="1"></label>
    <label>Pitch <input id="pitch" type="range" min="55" max="90" value="78" step="1"></label>
    <label>Yaw <input id="yaw" type="range" min="-35" max="35" value="0" step="1"></label>
    <button id="play">播放</button>
    <div class="legend">
      <span><i class="swatch" style="background:#ebf2ee"></i>floor</span>
      <span><i class="swatch" style="background:#1f272d"></i>obstacle</span>
      <span><i class="swatch" style="background:#aeb7bd"></i>unknown</span>
    </div>
    <div class="stats" id="stats"></div>
  </aside>
</main>
<script>
const data = {payload};
const frames = data.frames;
const b = data.bounds;
const canvas = document.getElementById("view");
const ctx = canvas.getContext("2d");
const frameSlider = document.getElementById("frame");
const pitchSlider = document.getElementById("pitch");
const yawSlider = document.getElementById("yaw");
const stats = document.getElementById("stats");
const subtitle = document.getElementById("subtitle");
const play = document.getElementById("play");
let timer = null;
frameSlider.max = frames.length - 1;
function stat(label, value) {{
  return `<div class="stat"><span>${{label}}</span><strong>${{value}}</strong></div>`;
}}
function resize() {{
  const r = canvas.getBoundingClientRect();
  const d = devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(r.width * d));
  canvas.height = Math.max(1, Math.floor(r.height * d));
}}
function draw() {{
  resize();
  const frame = frames[Number(frameSlider.value)];
  const yaw = Number(yawSlider.value) * Math.PI / 180;
  const pitch = Number(pitchSlider.value) * Math.PI / 180;
  const cx = (b.minX + b.maxX) / 2;
  const cz = (b.minZ + b.maxZ) / 2;
  const span = Math.max(b.maxX - b.minX, b.maxZ - b.minZ, 0.5);
  const scale = Math.min(canvas.width, canvas.height) * 0.82 / span;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#d6dde1";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const projected = frame.points.map(p => {{
    const x = p[0] - cx;
    const z = p[1] - cz;
    const h = p[2];
    const xr = x * Math.cos(yaw) - z * Math.sin(yaw);
    const zr = x * Math.sin(yaw) + z * Math.cos(yaw);
    const sy = zr * Math.sin(pitch) - h * Math.cos(pitch);
    return {{x: canvas.width / 2 + xr * scale, y: canvas.height / 2 - sy * scale, h, c:`rgb(${{p[3]}},${{p[4]}},${{p[5]}})`}};
  }});
  projected.sort((a, z) => a.h - z.h);
  for (const p of projected) {{
    ctx.fillStyle = p.c;
    ctx.fillRect(p.x - 1.3, p.y - 1.3, 2.6, 2.6);
  }}
  subtitle.textContent = `${{frame.name}} / ${{frame.points.length.toLocaleString()}} sampled points`;
  stats.innerHTML =
    stat("frame", frame.frame) +
    stat("sampled 3D points", frame.points.length.toLocaleString()) +
    stat("free cells", frame.free) +
    stat("occupied cells", frame.occupied) +
    stat("unknown cells", frame.unknown) +
    stat("free components", frame.components) +
    stat("largest free component", frame.largest);
}}
frameSlider.oninput = draw;
pitchSlider.oninput = draw;
yawSlider.oninput = draw;
play.onclick = () => {{
  if (timer) {{
    clearInterval(timer);
    timer = null;
    play.textContent = "播放";
    return;
  }}
  play.textContent = "暫停";
  timer = setInterval(() => {{
    let next = Number(frameSlider.value) + 1;
    if (next >= frames.length) next = 0;
    frameSlider.value = next;
    draw();
  }}, 750);
}};
addEventListener("resize", draw);
draw();
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=DEFAULT_REPLAY_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-points-per-frame", type=int, default=18000)
    args = parser.parse_args()
    if args.max_points_per_frame < 100:
        parser.error("--max-points-per-frame must be at least 100")
    return args


def main() -> int:
    args = parse_args()
    replay_dir = args.replay_dir.resolve()
    frames = load_frames(replay_dir, args.max_points_per_frame)
    output = args.output.resolve() if args.output else replay_dir / "online_replay_3d_top_viewer.html"
    write_html(frames, bounds(frames), output)
    print(f"Wrote {output}")
    print(f"Frames: {len(frames)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
