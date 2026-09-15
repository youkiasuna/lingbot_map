"""Temporary demo sessions with explicit save/discard decisions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMP_ROOT = ROOT / "outputs/tmp"


def new_session(name: str = "demo", root: Path = TEMP_ROOT) -> Path:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Session name must be a single directory name.")
    root.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix=name + "_", dir=root)).resolve()
    (session / "storage.json").write_text(json.dumps({"state": "temporary", "name": name, "active_pid": os.getpid()}) + "\n")
    return session


def validate_session(session: Path, root: Path = TEMP_ROOT) -> Path:
    if session.is_symlink():
        raise ValueError("Session cannot be a symbolic link.")
    session = session.resolve()
    if session.parent != root.resolve() or not (session / "storage.json").is_file():
        raise ValueError("Only managed temporary sessions can be saved or discarded.")
    pid = json.loads((session / "storage.json").read_text()).get("active_pid")
    if pid and pid != os.getpid():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError("Session is still in use; stop its process before deciding storage.")
    return session


def rewrite_metadata(root: Path, old: Path, new: Path) -> None:
    def rewrite(value):
        if isinstance(value, str):
            return value.replace(str(old), str(new))
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if isinstance(value, dict):
            return {k: rewrite(v) for k, v in value.items()}
        return value

    for path in root.rglob("*.json"):
        if path.is_symlink():
            continue
        original = json.loads(path.read_text())
        updated = rewrite(original)
        if original != updated:
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")


def save_session(session: Path, destination: Path, root: Path = TEMP_ROOT,
                 capture_root: Path = ROOT / "data/captures") -> Path:
    session = validate_session(session, root)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / session.name
    captures = capture_root.resolve() / session.name
    if target.exists() or captures.exists():
        raise FileExistsError("Saved session already exists; nothing was overwritten.")
    # Finish a separate copy before removing the user's only temporary result.
    staging = Path(tempfile.mkdtemp(prefix=".saving_", dir=destination))
    try:
        shutil.copytree(session, staging, dirs_exist_ok=True, symlinks=True)
        rewrite_metadata(staging, session, target)
        for frames in list(staging.rglob("frames")):
            if not frames.is_dir() or frames.is_symlink():
                continue
            raw = captures / frames.relative_to(staging)
            raw.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(frames), str(raw))
            final_link = target / frames.relative_to(staging)
            frames.symlink_to(os.path.relpath(raw, final_link.parent), target_is_directory=True)
        (staging / "storage.json").write_text(json.dumps({"state": "saved", "source_session": str(session)}) + "\n")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if captures.exists():
            shutil.rmtree(captures)
        raise
    shutil.rmtree(session)
    return target


def discard_session(session: Path, root: Path = TEMP_ROOT) -> None:
    shutil.rmtree(validate_session(session, root))


def finish_session(session: Path, destination: Path, root: Path = TEMP_ROOT) -> None:
    (session / "storage.json").write_text(json.dumps({"state": "pending"}) + "\n")
    print(f"Temporary results: {session}", flush=True)
    if sys.stdin.isatty():
        try:
            choice = input("Save / discard / decide later? [s/d/l, default l]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "l"
        if choice == "s":
            print(f"Saved: {save_session(session, destination, root)}")
            return
        if choice == "d":
            discard_session(session, root)
            print("Temporary results discarded.")
            return
    print("Pending decision; results have NOT been deleted or saved permanently.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "save", "discard"))
    parser.add_argument("session", nargs="?", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / "outputs/saved_demos")
    args = parser.parse_args()
    if args.action == "list":
        for marker in sorted(TEMP_ROOT.glob("*/storage.json")):
            print(marker.parent)
    elif args.session is None:
        parser.error("session is required")
    elif args.action == "save":
        print(save_session(args.session, args.destination))
    else:
        discard_session(args.session)


if __name__ == "__main__":
    main()
