"""Shared TCP command contract for the manual ESP32 controller."""

from __future__ import annotations

import socket


COMMAND_MAP = {
    "forward": "F",
    "backward": "B",
    "left": "L",
    "right": "R",
    "stop": "S",
}


def send_command(ip: str, port: int, command: str) -> str:
    """Send one newline-terminated command and return the controller reply."""
    with socket.create_connection((ip, port), timeout=2) as connection:
        connection.sendall(command.encode("utf-8") + b"\n")
        return connection.recv(1024).decode("utf-8", errors="ignore").strip()
