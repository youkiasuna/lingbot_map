#!/usr/bin/env python3
"""Scan project data and classify files for cleanup review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_SCAN_ROOTS = (
    "Integrated_version",
    "map_localization_test",
    "car",
    "visual_navigation",
    "lingbot-map-main",
    "data",
    "models",
    "outputs",
)


@dataclass
class FileRecord:
    path: str
    size_bytes: int
    category: str
    action: str
    reason: str
    sha256: str | None = None


def classify(path: Path) -> tuple[str, str, str]:
    parts = path.parts
    name = path.name
    suffix = path.suffix.lower()
    path_text = path.as_posix()

    if "__pycache__" in parts or suffix == ".pyc":
        return "cache", "delete_candidate", "Python cache; can be regenerated."
    if ".pytest_cache" in parts:
        return "cache", "delete_candidate", "Test cache; can be regenerated."
    if parts[:1] == ("models",):
        return "model_weight", "keep", "Model assets required for inference."
    if parts[:2] == ("data", "frames"):
        return "extracted_frame", "keep", "Reproducible from video, but active scene links depend on these frames."
    if parts[:1] == ("data",):
        return "source_data", "keep", "Original captures, query images, or scene inputs."
    if parts[:2] == ("outputs", "tmp"):
        return "temporary_demo", "review", "Pending save/discard decision; never delete automatically."
    if parts[:2] == ("outputs", "archive"):
        return "historical_result", "review", "Old research results; some overview pages remain in use."
    if parts[:1] == ("outputs",):
        if suffix == ".html":
            return "generated_viewer", "keep", "Retained overview or explicitly saved demo viewer."
        return "research_result", "keep", "Mapping package, metrics, or explicitly saved results."
    if parts[:1] in (("Integrated_version",), ("car",), ("lingbot-map-main",), ("map_localization_test",), ("visual_navigation",)):
        return "code_config_docs", "keep", "Program source, tests, configuration, or documentation."
    return "other", "review", "No specific rule matched; review manually."


def hash_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_files(root: Path, scan_roots: list[str]) -> list[Path]:
    files: list[Path] = []
    for scan_root in scan_roots:
        base = root / scan_root
        if not base.exists():
            continue
        if base.is_file():
            files.append(base)
            continue
        files.extend(path for path in base.rglob("*") if path.is_file() and "manifests" not in path.parts)
    return sorted(files)


def scan(root: Path, scan_roots: list[str], hash_large: bool, hash_threshold_mb: int) -> list[FileRecord]:
    records: list[FileRecord] = []
    threshold = hash_threshold_mb * 1024 * 1024
    for path in iter_files(root, scan_roots):
        relative = path.relative_to(root)
        category, action, reason = classify(relative)
        size = path.lstat().st_size
        if path.is_symlink():
            category, action, reason = "input_link", "keep", "Link to retained original data; not another copy."
        sha256 = None
        if hash_large and size >= threshold and not path.is_symlink():
            sha256 = hash_file(path)
        records.append(
            FileRecord(
                path=relative.as_posix(),
                size_bytes=size,
                category=category,
                action=action,
                reason=reason,
                sha256=sha256,
            )
        )
    return records


def summarize(records: list[FileRecord]) -> dict[str, object]:
    by_action: dict[str, dict[str, int]] = {}
    by_category: dict[str, dict[str, int]] = {}
    for record in records:
        for bucket, key in ((by_action, record.action), (by_category, record.category)):
            item = bucket.setdefault(key, {"files": 0, "size_bytes": 0})
            item["files"] += 1
            item["size_bytes"] += record.size_bytes
    return {
        "file_count": len(records),
        "total_size_bytes": sum(record.size_bytes for record in records),
        "by_action": by_action,
        "by_category": by_category,
    }


def write_csv(path: Path, records: list[FileRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(asdict(records[0]).keys()) if records else list(FileRecord.__annotations__))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root to scan.")
    parser.add_argument("--output-dir", default="outputs/manifests")
    parser.add_argument("--scan-root", action="append", dest="scan_roots", help="Relative path to scan. Can be repeated.")
    parser.add_argument("--hash-large", action="store_true", help="Hash large files to confirm duplicates.")
    parser.add_argument("--hash-threshold-mb", type=int, default=1024)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = (root / args.output_dir).resolve()
    scan_roots = args.scan_roots or list(DEFAULT_SCAN_ROOTS)

    records = scan(root, scan_roots, args.hash_large, args.hash_threshold_mb)
    summary = summarize(records)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "research_data_manifest.csv", records)
    (output_dir / "research_data_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Scanned {summary['file_count']} files")
    print(f"Wrote {output_dir / 'research_data_manifest.csv'}")
    print(f"Wrote {output_dir / 'research_data_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
