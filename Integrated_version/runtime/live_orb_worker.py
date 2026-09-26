"""Bounded latest-frame worker for optional live ORB relocalization."""
from __future__ import annotations

from threading import Condition, Thread
from typing import Callable

import numpy as np


class LatestFrameOrbWorker:
    """Run ORB on at most one pending frame and drop stale frames."""

    def __init__(
        self,
        localizer: object,
        on_result: Callable[[dict], None],
    ) -> None:
        self.localizer = localizer
        self.on_result = on_result
        self._condition = Condition()
        self._pending: tuple[np.ndarray, str] | None = None
        self._stopping = False
        self._thread: Thread | None = None
        self.processed_frames = 0
        self.dropped_frames = 0
        self.error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("worker already started")
        self._thread = Thread(target=self._run, name="live-orb-localizer", daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray, query_id: str) -> None:
        with self._condition:
            if self._stopping:
                return
            if self._pending is not None:
                self.dropped_frames += 1
            self._pending = (frame, query_id)
            self._condition.notify()

    def stop(self, timeout_s: float = 5.0) -> None:
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    while self._pending is None and not self._stopping:
                        self._condition.wait()
                    if self._stopping:
                        return
                    frame, query_id = self._pending
                    self._pending = None
                result = self.localizer.localize_frame(
                    frame,
                    query_id=query_id,
                    resize_mode="cover_crop",
                )
                self.processed_frames += 1
                self.on_result(result)
        except Exception as exc:
            self.error = exc
