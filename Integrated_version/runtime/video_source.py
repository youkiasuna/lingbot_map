"""Helpers for normalizing OpenCV video source arguments."""


def camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value
