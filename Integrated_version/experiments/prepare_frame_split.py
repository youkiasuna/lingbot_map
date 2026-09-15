#!/usr/bin/env python3
"""Prepare mapping/query frame splits for visual localization demos."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
ROOT = Path(__file__).resolve().parents[2]


def scene_inputs(scene_dir: Path) -> Path:
    scene_dir = scene_dir.absolute()
    inputs = scene_dir / "inputs"
    if inputs.exists():
        return inputs
    try:
        scene_name = scene_dir.relative_to(ROOT / "outputs/scenes")
    except ValueError:
        return inputs
    target = ROOT / "data/scenes" / scene_name / "inputs"
    target.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    inputs.symlink_to(os.path.relpath(target, scene_dir), target_is_directory=True)
    return inputs


def list_images(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source frame directory not found: {source_dir}")
    images = sorted(path for path in source_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise ValueError(f"No images found in {source_dir}")
    return images


def clear_existing_links(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in target_dir.iterdir():
        if path.is_symlink():
            path.unlink()


def write_links(images: list[Path], target_dir: Path) -> list[dict[str, object]]:
    clear_existing_links(target_dir)
    records: list[dict[str, object]] = []
    for output_index, source_path in enumerate(images):
        link_path = target_dir / f"{output_index:06d}{source_path.suffix.lower()}"
        if link_path.exists() and not link_path.is_symlink():
            raise FileExistsError(f"Refusing to replace non-symlink file: {link_path}")
        if link_path.exists():
            link_path.unlink()
        os.symlink(os.path.relpath(source_path.resolve(), link_path.parent.resolve()), link_path)
        records.append(
            {
                "split_index": output_index,
                "split_path": str(link_path),
                "source_path": str(source_path.resolve()),
                "source_frame_id": source_path.stem,
            }
        )
    return records


def select_frames(images: list[Path], step: int, offset: int) -> list[Path]:
    if step <= 0:
        raise ValueError("step must be positive")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    return images[offset::step]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--scene-dir", required=True, type=Path)
    parser.add_argument("--mapping-step", type=int, default=50)
    parser.add_argument("--query-step", type=int, default=50)
    parser.add_argument("--query-offset", type=int, default=25)
    parser.add_argument("--max-mapping", type=int)
    parser.add_argument("--max-query", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    images = list_images(args.source_dir)
    mapping = select_frames(images, args.mapping_step, 0)
    queries = select_frames(images, args.query_step, args.query_offset)
    if args.max_mapping is not None:
        mapping = mapping[: args.max_mapping]
    if args.max_query is not None:
        queries = queries[: args.max_query]
    if not mapping:
        raise ValueError("Mapping split is empty")
    if not queries:
        raise ValueError("Query split is empty")

    inputs_dir = scene_inputs(args.scene_dir)
    mapping_records = write_links(mapping, inputs_dir / "mapping_frames")
    query_records = write_links(queries, inputs_dir / "query_images")
    manifest = {
        "schema_version": 1,
        "source_dir": str(args.source_dir.resolve()),
        "mapping_step": args.mapping_step,
        "query_step": args.query_step,
        "query_offset": args.query_offset,
        "source_frame_count": len(images),
        "mapping_count": len(mapping_records),
        "query_count": len(query_records),
        "mapping": mapping_records,
        "queries": query_records,
    }
    args.scene_dir.mkdir(parents=True, exist_ok=True)
    (args.scene_dir / "split_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scene_dir": str(args.scene_dir),
                "source_frame_count": len(images),
                "mapping_count": len(mapping_records),
                "query_count": len(query_records),
                "manifest": str(args.scene_dir / "split_manifest.json"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
