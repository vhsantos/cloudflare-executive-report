"""Exclusive cache directory lock (.lock)."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class CacheLockTimeout(Exception):
    pass


@contextmanager
def cache_lock(cache_root: Path, wait_seconds: float = 30.0) -> Generator[None, None, None]:
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / ".lock"
    deadline = time.monotonic() + wait_seconds
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            fd = None
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise CacheLockTimeout(
                    f"Cache lock still held after {wait_seconds}s: {lock_path}"
                ) from None
            time.sleep(0.25)
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
