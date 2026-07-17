"""Section timing helper for pipeline stages."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.logging.bmv_logger import BmvLogger


class WatchBmv:
    """Time a code section; supports context manager and explicit start/stop.

    Usage::

        with WatchBmv("codegen", log):
            generate_files(...)

        watch = WatchBmv("build").start()
        run_build(...)
        watch.stop()
    """

    __slots__ = ("_label", "_logger", "_start", "_stopped")

    def __init__(self, label: str, logger: BmvLogger | None = None) -> None:
        from app.infrastructure.logging.bmv_logger import get_logger

        self._label = label
        self._logger = logger or get_logger("WatchBmv")
        self._start: float | None = None
        self._stopped = False

    @property
    def label(self) -> str:
        return self._label

    def start(self) -> WatchBmv:
        self._start = time.monotonic()
        self._stopped = False
        self._logger.debug(f"▶ {self._label} started")
        return self

    def stop(self) -> float:
        if self._start is None:
            self._logger.warning(f"WatchBmv.stop() called before start() for {self._label!r}")
            return 0.0
        elapsed = time.monotonic() - self._start
        self._stopped = True
        self._logger.info(f"■ {self._label} finished in {elapsed:.2f}s")
        return elapsed

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return time.monotonic() - self._start

    def __enter__(self) -> WatchBmv:
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._stopped:
            elapsed = self.stop()
            if exc_type is not None:
                self._logger.error(
                    f"✗ {self._label} failed after {elapsed:.2f}s: {exc_type.__name__}: {exc}"
                )
