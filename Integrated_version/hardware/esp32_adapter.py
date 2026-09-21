"""ESP32 velocity adapter with a safe dry-run-only command sink."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time

from planner.pure_pursuit import TwistCommand


@dataclass(frozen=True)
class Esp32Config:
    host: str = "dry-run-only"
    port: int = 8888
    command_timeout_s: float = 0.4
    dry_run: bool = True
    command_log_path: Path | None = None


class Esp32Adapter:
    """Record velocity commands without opening a hardware connection."""

    def __init__(self, config: Esp32Config) -> None:
        if not config.dry_run:
            raise ValueError("ESP32 hardware output is disabled; use dry_run=True for this prototype.")
        self.config = config
        self._last_send = 0.0

    def send(self, command: TwistCommand) -> bool:
        payload = {
            "event": "velocity_command",
            "linear_mps": float(command.linear_mps),
            "angular_rps": float(command.angular_rps),
            "status": command.status,
            "dry_run": True,
            "timestamp_unix": time.time(),
        }
        self._emit(payload)
        self._last_send = time.time()
        return True

    def stop(self) -> None:
        payload = {
            "event": "velocity_command",
            "linear_mps": 0.0,
            "angular_rps": 0.0,
            "status": "safety_stop",
            "dry_run": True,
            "timestamp_unix": time.time(),
        }
        self._emit(payload)
        self._last_send = time.time()

    def watchdog_expired(self) -> bool:
        return (
            self._last_send > 0.0
            and time.time() - self._last_send > self.config.command_timeout_s
        )

    def close(self) -> None:
        return None

    def _emit(self, payload: dict[str, object]) -> None:
        line = json.dumps(payload)
        print("[DRY-RUN] ESP32", line, flush=True)
        if self.config.command_log_path is not None:
            self.config.command_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config.command_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
