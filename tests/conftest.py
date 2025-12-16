import os
import sys
from pathlib import Path
import importlib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def m():
    """Lazily import the main module for tests to avoid module-level import."""
    return importlib.import_module("main")


@pytest.fixture()
def no_progress(monkeypatch, m):
    """Suppress progress rendering in main module during tests."""
    calls = []

    def _stub(line: str):
        calls.append(line)

    monkeypatch.setattr(m, "_print_progress", _stub)
    return calls


@pytest.fixture()
def progress_recorder():
    """Provide a reusable progress callback and its call log."""
    calls = []

    def cb(done, total):
        calls.append((done, total))

    return cb, calls


@pytest.fixture()
def fake_chown(monkeypatch):
    """Neutralize os.chown to avoid PermissionError in CI environments."""
    if hasattr(os, "chown"):
        monkeypatch.setattr(os, "chown", lambda *a, **k: None)


@pytest.fixture()
def temp_tree(tmp_path: Path):
    """Create a small directory tree with files for archive/e2e tests.

    Structure:
        rootdir/
            a.txt
            sub/
                b.bin
    """
    root = tmp_path / "rootdir"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (root / "a.txt").write_text("Hello World!\n", encoding="utf-8")
    (sub / "b.bin").write_bytes(b"\x00\x01\x02\x03\x04\x05")
    return root


def collect_files(base: Path):
    """Return mapping of relative path -> bytes for all regular files."""
    result = {}
    for p in base.rglob("*"):
        if p.is_file():
            result[p.relative_to(base).as_posix()] = p.read_bytes()
    return result


@pytest.fixture()
def collect_files_fn():
    """
    Fixture that provides the collect_files helper without importing conftest.
    """
    return collect_files
