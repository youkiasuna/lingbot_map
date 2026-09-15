#!/usr/bin/env python3
"""Analyze external query images against a prepared 20260818 mapping package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


INTEGRATED_ROOT = Path(__file__).resolve().parents[1]
if str(INTEGRATED_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATED_ROOT))

from experiments.localize_query_in_3d_viewer import (  # noqa: E402
    build_viewer_html,
    camera_centers,
    load_archive,
    sample_world_points,
)
from experiments.orb_keyframe_localizer import OrbKeyframeLocalizer, result_to_pose  # noqa: E402
from localization.localizer_interface import FilePosePublisher  # noqa: E402


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def safe_stem(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._") or "query"


def list_query_images(query_dir: Path) -> list[Path]:
    if not query_dir.is_dir():
        raise FileNotFoundError(f"Query image directory not found: {query_dir}")
    images = sorted(path for path in query_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    readme_names = {"readme"}
    return [path for path in images if path.stem.lower() not in readme_names]


def status_for_result(result: dict[str, Any], min_confidence: float) -> str:
    best = result.get("best")
    if not isinstance(best, dict):
        return "lost"
    if result.get("status") != "localized":
        return str(result.get("status", "lost"))
    confidence = float(best.get("confidence", 0.0))
    if confidence < min_confidence:
        return "low_confidence"
    return "localized"


def compact_record(query_image: Path, result: dict[str, Any], min_confidence: float, viewer_path: Path | None, json_path: Path) -> dict[str, Any]:
    best = result.get("best") if isinstance(result.get("best"), dict) else {}
    return {
        "query_image": str(query_image),
        "status": status_for_result(result, min_confidence),
        "best_frame_index": best.get("frame_index"),
        "match_count": best.get("match_count", 0),
        "inlier_count": best.get("inlier_count", 0),
        "reprojection_error_px": best.get("reprojection_error_px"),
        "confidence": best.get("confidence", 0.0),
        "position_xyz": best.get("position_xyz"),
        "yaw_deg": best.get("yaw_deg"),
        "latency_ms": result.get("latency_ms"),
        "result_json": str(json_path),
        "viewer_html": str(viewer_path) if viewer_path else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", type=Path, default=Path("outputs/scenes/scene_20260818"))
    parser.add_argument("--mapping-dir", type=Path)
    parser.add_argument("--query-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--pose-file", type=Path)
    parser.add_argument("--publish-min-confidence", type=float, default=0.35)
    parser.add_argument("--max-viewer-points", type=int, default=60000)
    parser.add_argument("--write-viewers", action="store_true", help="Generate per-query HTML in addition to research JSON")
    parser.add_argument("--max-features", type=int, default=2000)
    parser.add_argument("--frame-stride", type=int, default=1)
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
    scene_dir = args.scene_dir
    mapping_dir = args.mapping_dir or scene_dir / "mapping"
    query_dir = args.query_dir or scene_dir / "external_query_images"
    output_dir = args.output_dir or scene_dir / "external_query_results"
    pose_file = args.pose_file or scene_dir / "current_pose.json"

    query_images = list_query_images(query_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not query_images:
        (output_dir / "summary.json").write_text(
            json.dumps(
                {
                    "status": "no_query_images",
                    "query_dir": str(query_dir),
                    "message": "Put non-mapping .jpg/.jpeg/.png query photos into this folder and rerun.",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"No query images found in {query_dir}")
        return 2

    localizer = OrbKeyframeLocalizer(
        mapping_dir=mapping_dir,
        max_features=args.max_features,
        frame_stride=args.frame_stride,
        ratio=args.ratio,
        top_k=args.top_k,
        min_matches=args.min_matches,
        min_inliers=args.min_inliers,
        max_pnp_points=args.max_pnp_points,
        reprojection_error_px=args.reprojection_error_px,
        pnp_iterations=args.pnp_iterations,
    )
    if args.write_viewers:
        archive = load_archive(mapping_dir)
        points = sample_world_points(archive, args.max_viewer_points, min_norm=1e-6)
        references = camera_centers(archive)

    records: list[dict[str, Any]] = []
    publisher = FilePosePublisher(pose_file)
    for query_image in query_images:
        stem = safe_stem(query_image)
        result = localizer.localize(query_image)
        result_path = output_dir / f"{stem}_result.json"
        viewer_path = output_dir / f"{stem}_viewer.html" if args.write_viewers else None
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if viewer_path is not None:
            viewer_path.write_text(
                build_viewer_html(
                    mapping_dir=mapping_dir, query_image=query_image,
                    points=points, references=references, result=result,
                ), encoding="utf-8",
            )
        pose = result_to_pose(result, args.publish_min_confidence)
        publisher.publish(pose)
        records.append(compact_record(query_image, result, args.publish_min_confidence, viewer_path, result_path))

    localized = sum(1 for record in records if record["status"] == "localized")
    summary = {
        "schema_version": 1,
        "scene_dir": str(scene_dir),
        "mapping_dir": str(mapping_dir),
        "query_dir": str(query_dir),
        "output_dir": str(output_dir),
        "pose_file": str(pose_file),
        "query_count": len(records),
        "localized_count": localized,
        "localized_rate": round(localized / max(len(records), 1), 4),
        "records": records,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"query_count": len(records), "localized_count": localized, "summary": str(summary_path)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
