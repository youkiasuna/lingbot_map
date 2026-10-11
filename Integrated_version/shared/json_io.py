"""Durable atomic JSON output shared across project modules."""

import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(
    path: Path,
    payload: dict,
    *,
    indent: int | None = None,
    ensure_ascii: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    separators = (",", ":") if indent is None else None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=ensure_ascii, indent=indent, separators=separators)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
