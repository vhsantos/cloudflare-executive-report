"""Exclusive cache directory lock (.lock)."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


class CacheLockTimeout(Exception):
    pass


def _is_pid_alive(pid: int) -> bool:
    """Return True if a process with the given PID exists."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it.
        return True
    return True


def _read_lock_pid(lock_path: Path) -> int | None:
    """Read the PID stored in the lock file, or None if unreadable."""
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
        return int(content)
    except (OSError, ValueError):
        return None


def _try_steal_stale_lock(lock_path: Path) -> bool:
    """Remove the lock file if the owning process is no longer alive.

    Returns True if the lock was removed (caller should retry), False otherwise.
    """
    pid = _read_lock_pid(lock_path)
    if pid is None:
        log.warning(
            "Lock file %s exists but has unreadable PID; cannot verify staleness", lock_path
        )
        return False
    if _is_pid_alive(pid):
        return False
    log.warning("Removing stale lock file %s (PID %d is no longer running)", lock_path, pid)
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


@contextmanager
def cache_lock(cache_root: Path, wait_seconds: float = 30.0) -> Generator[None, None, None]:
    """Acquire an exclusive file-system lock on the cache directory.

    Writes the current PID into the lock file so stale locks from crashed
    processes can be detected and removed automatically.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / ".lock"
    deadline = time.monotonic() + wait_seconds
    fd: int | None = None
    stale_checked = False
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            fd = None
            break
        except FileExistsError:
            if not stale_checked:
                stale_checked = True
                if _try_steal_stale_lock(lock_path):
                    continue
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
