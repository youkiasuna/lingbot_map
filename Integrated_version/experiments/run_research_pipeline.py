#!/usr/bin/env python3
"""Run the reproducible 20260818 localization research workflow.

Stages are resumable: split, mapping, orb, viewer, and colored. Existing
outputs are reused unless --rerun is set.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
INTEGRATED = ROOT / "Integrated_version"
EXPERIMENTS = INTEGRATED / "experiments"
STAGE_NAMES = {"split", "mapping", "orb", "viewer", "colored"}


def run(command: list[str]) -> None:
    print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data/frames/20260818_frames")
    parser.add_argument("--scene-dir", type=Path, default=ROOT / "outputs/scenes/scene_20260818")
    parser.add_argument("--model-path", type=Path, default=ROOT / "models/lingbot-map.pt")
    parser.add_argument("--viewer-up-axis", choices=("auto", "x", "-x", "y", "-y", "z", "-z"), default="-y", help="Signed vertical axis for the raw 20260818 map")
    parser.add_argument("--stages", default="all", help="Comma-separated: split,mapping,orb,viewer,colored")
    parser.add_argument("--colored-limit", type=int, default=1, help="Number of queries for the slow colored-Ply stage")
    parser.add_argument("--rerun", action="store_true", help="Rerun selected stages even when outputs exist")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.source_dir = args.source_dir.resolve()
    args.scene_dir = args.scene_dir.resolve()
    args.model_path = args.model_path.resolve()
    if args.colored_limit < 0:
        raise SystemExit("--colored-limit cannot be negative")
    scene = args.scene_dir
    mapping = scene / "mapping"
    stages = STAGE_NAMES if args.stages == "all" else {
        stage.strip() for stage in args.stages.split(",") if stage.strip()
    }
    unknown = stages - STAGE_NAMES
    if unknown:
        raise SystemExit(f"Unknown stages: {', '.join(sorted(unknown))}")

    manifest = scene / "split_manifest.json"
    if "split" in stages and (args.rerun or not manifest.exists()):
        run([PYTHON, str(EXPERIMENTS / "prepare_frame_split.py"),
             "--source-dir", str(args.source_dir), "--scene-dir", str(scene),
             "--mapping-step", "50", "--query-step", "50", "--query-offset", "25"])
    elif "split" in stages:
        print(f"Reuse split: {manifest}")

    archive = mapping / "predictions.npz"
    ply = mapping / "rebuilt_colored_map.ply"
    if "mapping" in stages and (args.rerun or not archive.exists() or not ply.exists()):
        run([PYTHON, str(EXPERIMENTS / "run_lingbot_mapping.py"),
             "--image-folder", str(scene / "inputs/mapping_frames"),
             "--model-path", str(args.model_path), "--output-dir", str(mapping),
             "--camera-num-iterations", "1", "--use-sdpa",
             "--output-ply", str(ply), "--downsample-factor", "4"])
    elif "mapping" in stages:
        print(f"Reuse mapping: {archive}")

    orb_dir = scene / "results/orb"
    if "orb" in stages and (args.rerun or not (orb_dir / "summary.json").exists()):
        run([PYTHON, str(EXPERIMENTS / "analyze_external_queries.py"),
             "--scene-dir", str(scene), "--mapping-dir", str(mapping),
             "--query-dir", str(scene / "inputs/query_images"),
             "--output-dir", str(orb_dir), "--pose-file", str(scene / "current_pose.json")])
    elif "orb" in stages:
        print(f"Reuse ORB results: {orb_dir / 'summary.json'}")

    viewer = scene / "visualization/auto_floor_viewer.html"
    if "viewer" in stages and (args.rerun or not viewer.exists()):
        run([PYTHON, str(INTEGRATED / "map/export_height_color_viewer.py"),
             "--ply", str(ply), "--output", str(viewer), f"--up-axis={args.viewer_up_axis}",
             "--max-points", "121231"])
    elif "viewer" in stages:
        print(f"Reuse viewer: {viewer}")

    if "colored" in stages:
        queries = sorted((scene / "inputs/query_images").glob("*.jpg"))[:args.colored_limit]
        colored_dir = scene / "results/colored"
        for query in queries:
            output_json = colored_dir / f"{query.stem}_result.json"
            output_html = colored_dir / f"{query.stem}_viewer.html"
            if output_json.exists() and output_html.exists() and not args.rerun:
                print(f"Reuse colored result: {output_json}")
                continue
            run([PYTHON, str(EXPERIMENTS / "colored_pointcloud_localizer.py"),
                 "--ply", str(ply), "--mapping-dir", str(mapping),
                 "--query-image", str(query), "--output-json", str(output_json),
                 "--output-html", str(output_html), "--max-points", "150000"])

    print("\nPipeline complete.")
    print(f"Scene: {scene}")
    print(f"ORB summary: {orb_dir / 'summary.json'}")
    print(f"3D viewer: http://127.0.0.1:18101/{viewer.relative_to(ROOT)}")
    if "colored" in stages:
        print(f"Colored results: {scene / 'results/colored'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
