"""Consistent no-cache JSON and byte responses for local HTTP handlers."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler


def send_bytes(
    handler: BaseHTTPRequestHandler,
    data: bytes,
    content_type: str,
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def send_json(
    handler: BaseHTTPRequestHandler,
    payload: object,
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    send_bytes(handler, data, "application/json; charset=utf-8", status)
