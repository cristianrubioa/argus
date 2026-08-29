import os
import subprocess

import pytest

from argus.tray import lock


def test_acquire_lock_writes_pid_when_none_exists(tmp_path, monkeypatch):
    # Setup
    monkeypatch.setattr(lock, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(lock, "_PID_FILE", tmp_path / "argus-tray.pid")
    # Action
    lock.acquire_lock()
    # Expected
    assert (tmp_path / "argus-tray.pid").read_text().strip() == str(os.getpid())


def test_acquire_lock_overwrites_a_stale_pid(tmp_path, monkeypatch):
    # Setup
    dead_process = subprocess.Popen(["true"])
    dead_process.wait()
    pid_file = tmp_path / "argus-tray.pid"
    pid_file.write_text(str(dead_process.pid))
    monkeypatch.setattr(lock, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(lock, "_PID_FILE", pid_file)
    # Action
    lock.acquire_lock()
    # Expected
    assert pid_file.read_text().strip() == str(os.getpid())


def test_acquire_lock_exits_when_already_running(tmp_path, monkeypatch):
    # Setup
    pid_file = tmp_path / "argus-tray.pid"
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(lock, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(lock, "_PID_FILE", pid_file)
    # Action & Expected
    with pytest.raises(SystemExit):
        lock.acquire_lock()


def test_release_lock_is_idempotent(tmp_path, monkeypatch):
    # Setup
    pid_file = tmp_path / "argus-tray.pid"
    monkeypatch.setattr(lock, "_PID_FILE", pid_file)
    # Action & Expected
    lock.release_lock()
    pid_file.write_text(str(os.getpid()))
    lock.release_lock()
    assert not pid_file.exists()
