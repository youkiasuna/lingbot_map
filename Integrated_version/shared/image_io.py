"""OpenCV image loading that supports Unicode paths on Windows."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_bgr_image(path: str | Path) -> np.ndarray | None:
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)
