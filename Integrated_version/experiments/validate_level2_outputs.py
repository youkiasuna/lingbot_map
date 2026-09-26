#!/usr/bin/env python3
"""Read-only validator for Level 2 live mapping outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REQUIRED_FILES = (
    "live_map.json",
    "live_points.npz",
    "live_pose.json",
    "live_status.json",
)


def read_object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def validate(output_dir: Path, require_rgb: bool = False) -> dict:
    issues: list[str] = []
    files = {name: (output_dir / name).is_file() for name in REQUIRED_FILES}
    for name, exists in files.items():
        if not exists:
            issues.append(f"missing file: {name}")

    result: dict[str, object] = {
        "output_dir": str(output_dir),
        "files": files,
        "geometry_only_compatible": True,
        "rgb_available": False,
        "pose_valid": False,
        "issues": issues,
    }
    if issues:
        return result

    try:
        live_map = read_object(output_dir / "live_map.json")
        live_pose = read_object(output_dir / "live_pose.json")
        live_status = read_object(output_dir / "live_status.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(f"invalid JSON: {exc}")
        return result

    try:
        with np.load(output_dir / "live_points.npz", allow_pickle=False) as archive:
            if "points_xyz" not in archive or "map_version" not in archive:
                issues.append("live_points.npz requires points_xyz and map_version")
            points = np.asarray(archive["points_xyz"], dtype=np.float32).reshape(-1, 3)
            npz_version = int(np.asarray(archive["map_version"]).item())
            colors = None
            if "colors_rgb" in archive:
                colors = np.asarray(archive["colors_rgb"])
    except (OSError, KeyError, ValueError, TypeError) as exc:
        issues.append(f"invalid live_points.npz: {exc}")
        return result

    if not np.isfinite(points).all():
        issues.append("points_xyz contains non-finite values")
    if colors is not None:
        if colors.shape != (len(points), 3):
            issues.append("colors_rgb is not aligned with points_xyz")
        elif colors.dtype != np.uint8:
            issues.append(f"colors_rgb must be uint8, got {colors.dtype}")
        else:
            result["rgb_available"] = True
    if require_rgb and colors is None:
        issues.append("RGB is required but colors_rgb is missing")

    versions = {
        "live_map": live_map.get("map_version"),
        "live_status": live_status.get("map_version"),
        "npz": npz_version,
    }
    if len(set(versions.values())) != 1:
        issues.append(f"map_version mismatch: {versions}")

    quality = live_map.get("quality", {})
    if isinstance(quality, dict) and quality.get("point_count") != len(points):
        issues.append("live_map quality.point_count does not match points_xyz")

    record = live_map.get("record", {})
    if isinstance(record, dict) and record.get("point_count") != len(points):
        issues.append("live_map record.point_count does not match points_xyz")

    position = live_pose.get("position_xyz")
    status = str(live_pose.get("status", "")).lower()
    confidence = live_pose.get("confidence")
    pose_valid = (
        isinstance(position, list)
        and len(position) == 3
        and all(isinstance(value, (int, float)) and np.isfinite(value) for value in position)
        and status in {"ok", "localized", "tracking"}
        and isinstance(confidence, (int, float))
        and 0.0 <= float(confidence) <= 1.0
    )
    result["pose_valid"] = pose_valid
    result["pose_status"] = status or None
    result["point_count"] = len(points)
    result["map_version"] = npz_version
    result["issues"] = issues
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-dir", required=True, type=Path)
    parser.add_argument("--require-rgb", action="store_true")
    args = parser.parse_args()

    report = validate(args.live_dir.resolve(), require_rgb=args.require_rgb)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
