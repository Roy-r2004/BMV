"""Parallel execution helpers for preview-app generation."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def split_codegen_phases(files: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split file specs into foundation → components → pages batches."""
    foundation: list[dict] = []
    components: list[dict] = []
    pages: list[dict] = []
    for spec in files:
        kind = spec.get("kind", "page")
        if kind == "data":
            foundation.append(spec)
        elif kind in ("component", "layout", "router", "theme"):
            components.append(spec)
        elif kind == "page":
            pages.append(spec)
        else:
            components.append(spec)
    return foundation, components, pages


def parallel_map(
    items: list[T],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    on_done: Callable[[int, int, T, R | None, Exception | None], None] | None = None,
) -> list[tuple[T, R | None, Exception | None]]:
    """Run `worker` over `items` with a bounded thread pool. Preserves input order in results."""
    if not items:
        return []
    if max_workers <= 1 or len(items) == 1:
        out: list[tuple[T, R | None, Exception | None]] = []
        for i, item in enumerate(items, 1):
            try:
                result = worker(item)
                out.append((item, result, None))
                if on_done:
                    on_done(i, len(items), item, result, None)
            except Exception as exc:
                out.append((item, None, exc))
                if on_done:
                    on_done(i, len(items), item, None, exc)
        return out

    indexed = list(enumerate(items))
    results: dict[int, tuple[T, R | None, Exception | None]] = {}
    done_count = 0
    lock = threading.Lock()

    def _run(index: int, item: T) -> tuple[int, T, R | None, Exception | None]:
        try:
            return index, item, worker(item), None
        except Exception as exc:
            return index, item, None, exc

    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        futures = [pool.submit(_run, i, item) for i, item in indexed]
        for fut in as_completed(futures):
            index, item, result, exc = fut.result()
            results[index] = (item, result, exc)
            with lock:
                done_count += 1
                current_done = done_count
            # Call on_done outside the counter lock so callbacks can do their own
            # locking / DB work without nesting locks.
            if on_done:
                on_done(current_done, len(items), item, result, exc)

    return [results[i] for i in range(len(items))]
