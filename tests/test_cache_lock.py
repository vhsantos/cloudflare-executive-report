import os
import time
from pathlib import Path

import pytest

from cloudflare_executive_report.cache.lock import CacheLockTimeout, cache_lock


def test_cache_lock_basic(tmp_path: Path):
    """Test that we can acquire and release the lock."""
    lock_path = tmp_path / ".lock"

    with cache_lock(tmp_path):
        assert lock_path.exists()
        # Verify PID is in the file
        pid = int(lock_path.read_text().strip())
        assert pid == os.getpid()

    assert not lock_path.exists()


def test_cache_lock_contention(tmp_path: Path):
    """Test that a second lock wait fails after timeout."""
    with cache_lock(tmp_path):
        with pytest.raises(CacheLockTimeout):
            # Try to acquire again with a very short timeout
            with cache_lock(tmp_path, wait_seconds=0.1):
                pass


def test_cache_lock_stale_recovery(tmp_path: Path):
    """Test that we can steal a lock from a dead PID."""
    lock_path = tmp_path / ".lock"

    # Manually create a lock file with a PID that (likely) doesn't exist.
    # We use a very high PID or one we know is dead.
    # On Linux, /proc/sys/kernel/pid_max is usually 32768 or higher.
    # We'll use a PID that is not running.
    stale_pid = 999999

    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(stale_pid))

    # This should detect the PID is dead and take the lock.
    start_time = time.monotonic()
    with cache_lock(tmp_path, wait_seconds=1.0):
        assert lock_path.exists()
        current_pid = int(lock_path.read_text().strip())
        assert current_pid == os.getpid()

    # Should be fast (not wait the full 1.0s)
    assert time.monotonic() - start_time < 0.5
    assert not lock_path.exists()
