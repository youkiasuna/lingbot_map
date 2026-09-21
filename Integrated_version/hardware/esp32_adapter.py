"""ESP32 velocity adapter with a safe dry-run default."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import time

from planner.pure_pursuit import TwistCommand


@dataclass(frozen=True)
class Esp32Config:
    host: str
    port: int = 8888
    command_timeout_s: float = 0.4
    dry_run: bool = True


class Esp32Adapter:
    """Send velocity commands only when explicitly enabled."""

    def __init__(self, config: Esp32Config) -> None:
        self.config = config
        self._socket: socket.socket | None = None
        self._last_send = 0.0

    def send(self, command: TwistCommand) -> bool:
        payload = {
            "linear_mps": float(command.linear_mps),
            "angular_rps": float(command.angular_rps),
            "status": command.status,
            "timestamp_unix": time.time(),
        }
        if self.config.dry_run:
            print("[DRY-RUN] ESP32", json.dumps(payload), flush=True)
            self._last_send = time.time()
            return True

        try:
            if self._socket is None:
                self._socket = socket.create_connection(
                    (self.config.host, self.config.port),
                    timeout=self.config.command_timeout_s,
                )
            self._socket.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            self._last_send = time.time()
            return True
        except OSError:
            self.stop()
            return False

    def stop(self) -> None:
        stop_command = TwistCommand(0.0, 0.0, "safety_stop")
        if self.config.dry_run:
            print("[DRY-RUN] ESP32", json.dumps({
                "linear_mps": 0.0,
                "angular_rps": 0.0,
                "status": stop_command.status,
            }), flush=True)
        elif self._socket is not None:
            try:
                self._socket.sendall(b'{"linear_mps":0.0,"angular_rps":0.0,"status":"safety_stop"}\n')
            except OSError:
                pass
        self.close()

    def watchdog_expired(self) -> bool:
        return (
            self._last_send > 0.0
            and time.time() - self._last_send > self.config.command_timeout_s
        )

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
