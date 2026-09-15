#!/usr/bin/env python3
"""Export a self-contained HTML viewer for online replay map growth."""

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPLAY_DIR = ROOT / "outputs/scenes/scene_20260818/online_replay"


def pgm_to_png_data_url(path: Path, scale: int) -> str:
    image = Image.open(path).convert("L")
    rgb = Image.new("RGB", image.size)
    src = image.load()
    dst = rgb.load()
    for y in range(image.height):
        for x in range(image.width):
            value = src[x, y]
            if value <= 100:
                color = (31, 39, 45)
            elif value == 205:
                color = (174, 183, 189)
            else:
                color = (238, 243, 241)
            dst[x, y] = color
    if scale > 1:
        rgb = rgb.resize((rgb.width * scale, rgb.height * scale), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def load_frames(replay_dir: Path, scale: int) -> list[dict[str, object]]:
    frames = []
    for map_path in sorted(replay_dir.glob("frame_*/map.pgm")):
        frame_dir = map_path.parent
        metadata = json.loads((frame_dir / "map.json").read_text(encoding="utf-8"))
        counts = metadata.get("counts", {})
        frames.append(
            {
                "name": frame_dir.name,
                "frame": int(frame_dir.name.rsplit("_", 1)[1]),
                "image": pgm_to_png_data_url(map_path, scale),
                "width": metadata["width_px"],
                "height": metadata["height_px"],
                "free": counts.get("free_cells", 0),
                "occupied": counts.get("occupied_cells", 0),
                "unknown": counts.get("unknown_cells", 0),
                "components": counts.get("free_components", 0),
                "largest": counts.get("largest_free_component_cells", 0),
            }
        )
    if not frames:
        raise ValueError(f"No frame_*/map.pgm files found under {replay_dir}")
    return frames


def write_html(frames: list[dict[str, object]], summary: dict[str, object], output: Path) -> None:
    payload = json.dumps({"frames": frames, "summary": summary}, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Online Mapping Replay</title>
<style>
:root {{ color-scheme: light; --bg:#f3f5f6; --panel:#fff; --text:#172026; --muted:#65717a; --line:#ccd5db; --accent:#087f8c; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; }}
header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; background: var(--panel); border-bottom: 1px solid var(--line); }}
h1 {{ margin: 0; font-size: 18px; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; padding: 16px; }}
.stage {{ min-height: calc(100vh - 96px); display: grid; place-items: center; overflow: auto; background: #d6dde1; border: 1px solid var(--line); border-radius: 8px; }}
.stage img {{ image-rendering: pixelated; max-width: 100%; max-height: calc(100vh - 132px); }}
.panel {{ align-self: start; display: grid; gap: 14px; padding: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
label {{ display: grid; gap: 8px; color: var(--muted); font-size: 13px; }}
input[type=range] {{ width: 100%; }}
.stats {{ display: grid; gap: 10px; }}
.stat {{ border-top: 1px solid var(--line); padding-top: 10px; display: grid; gap: 3px; }}
.stat span {{ color: var(--muted); font-size: 12px; }}
.stat strong {{ font-size: 15px; }}
.legend {{ display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
.swatch {{ display: inline-block; width: 12px; height: 12px; margin-right: 4px; vertical-align: -2px; border: 1px solid #9aa5ab; }}
button {{ height: 36px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text); font: inherit; cursor: pointer; }}
button:hover {{ border-color: var(--accent); }}
@media(max-width: 860px) {{ main {{ grid-template-columns: 1fr; }} .stage {{ min-height: 55vh; }} }}
</style>
</head>
<body>
<header><h1>Online Mapping Replay</h1><span id="subtitle"></span></header>
<main>
  <section class="stage"><img id="map" alt="online replay map"></section>
  <aside class="panel">
    <label>Frame <input id="slider" type="range" min="0" value="0" step="1"></label>
    <button id="play">播放</button>
    <div class="legend">
      <span><i class="swatch" style="background:#eef3f1"></i>free</span>
      <span><i class="swatch" style="background:#1f272d"></i>occupied</span>
      <span><i class="swatch" style="background:#aeb7bd"></i>unknown</span>
    </div>
    <div class="stats" id="stats"></div>
  </aside>
</main>
<script>
const data = {payload};
const frames = data.frames;
const slider = document.getElementById("slider");
const image = document.getElementById("map");
const stats = document.getElementById("stats");
const play = document.getElementById("play");
const subtitle = document.getElementById("subtitle");
let timer = null;
slider.max = frames.length - 1;
function stat(label, value) {{
  return `<div class="stat"><span>${{label}}</span><strong>${{value}}</strong></div>`;
}}
function show(index) {{
  const f = frames[index];
  image.src = f.image;
  subtitle.textContent = `${{f.name}} / ${{f.width}}x${{f.height}}`;
  stats.innerHTML =
    stat("frame", f.frame) +
    stat("free cells", f.free) +
    stat("occupied cells", f.occupied) +
    stat("unknown cells", f.unknown) +
    stat("free components", f.components) +
    stat("largest free component", f.largest);
}}
slider.oninput = () => show(Number(slider.value));
play.onclick = () => {{
  if (timer) {{
    clearInterval(timer);
    timer = null;
    play.textContent = "播放";
    return;
  }}
  play.textContent = "暫停";
  timer = setInterval(() => {{
    let next = Number(slider.value) + 1;
    if (next >= frames.length) next = 0;
    slider.value = next;
    show(next);
  }}, 700);
}};
show(0);
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
    parser.add_argument("--scale", type=int, default=10)
    args = parser.parse_args()
    if args.scale < 1:
        parser.error("--scale must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    replay_dir = args.replay_dir.resolve()
    summary_path = replay_dir / "online_replay_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    frames = load_frames(replay_dir, args.scale)
    output = args.output.resolve() if args.output else replay_dir / "online_replay_viewer.html"
    write_html(frames, summary, output)
    print(f"Wrote {output}")
    print(f"Frames: {len(frames)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
