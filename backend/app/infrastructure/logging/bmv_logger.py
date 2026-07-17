"""Injectable logger with caller class, line number, and timestamp."""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Any

# TRACE sits below DEBUG (stdlib has no TRACE level).
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def _trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]


class BmvLogger:
    """Factory-produced logger bound to an owner (class or module name).

    Usage::

        class MyService:
            def __init__(self) -> None:
                self.log = get_logger(self.__class__)

            def run(self) -> None:
                self.log.info("starting")
    """

    __slots__ = ("_owner", "_logger")

    def __init__(self, owner: str) -> None:
        self._owner = owner
        self._logger = logging.getLogger(f"bmv.{owner}")

    @property
    def owner(self) -> str:
        return self._owner

    def _emit(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        if not self._logger.isEnabledFor(level):
            return
        frame = inspect.currentframe()
        caller = frame.f_back.f_back if frame and frame.f_back else None  # skip _emit + level method
        line = caller.f_lineno if caller else 0
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        prefix = f"{ts} | {self._owner}:{line}"
        self._logger.log(level, f"{prefix} | {message}", *args, **kwargs)

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(TRACE_LEVEL, message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.ERROR, message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit(logging.ERROR, message, *args, **kwargs)


def get_logger(owner: type | str) -> BmvLogger:
    """Return a logger bound to a class or module name string."""
    if isinstance(owner, type):
        name = owner.__name__
    else:
        name = str(owner).rsplit(".", 1)[-1]
    return BmvLogger(name)
