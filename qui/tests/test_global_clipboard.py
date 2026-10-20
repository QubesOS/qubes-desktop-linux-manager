"""Tests for writing the global clipboard files."""

# pylint: disable=redefined-outer-name

import fcntl
import json
import os
import re

import pytest

from qui import global_clipboard


@pytest.fixture
def clipboard_dir(tmp_path, monkeypatch):
    for name in ("DATA", "METADATA", "FROM", "XEVENT", "APPVIEWER_LOCK"):
        path = getattr(global_clipboard, name)
        monkeypatch.setattr(
            global_clipboard, name, str(tmp_path / os.path.basename(path))
        )
    return tmp_path


def read_metadata(clipboard_dir):
    return (clipboard_dir / "qubes-clipboard.bin.metadata").read_text("ascii")


def test_copy(clipboard_dir):
    data = "zażółć gęślą jaźń\n".encode("utf-8")
    global_clipboard.copy_to_global_clipboard(data, timestamp=1234)

    assert (clipboard_dir / "qubes-clipboard.bin").read_bytes() == data
    assert (clipboard_dir / "qubes-clipboard.bin.source").read_text("ascii") == "dom0"
    assert (clipboard_dir / "qubes-clipboard.bin.xevent").read_text("ascii") == "1234"
    assert json.loads(read_metadata(clipboard_dir)) == {
        "vmname": "dom0",
        "xevent_timestamp": 1234,
        "successful": 1,
        "copy_action": 1,
        "paste_action": 0,
        "malformed_request": 0,
        "oversized_request": 0,
        "cleared": 0,
        "qrexec_clipboard": 0,
        "sent_size": len(data),
        "buffer_size": 256000,
        "protocol_version_xside": 0x00010008,
        "protocol_version_vmside": 0x00010008,
    }


def test_metadata_format(clipboard_dir):
    """qubes-guid reads metadata with sscanf, one "key":value per line"""
    global_clipboard.copy_to_global_clipboard(b"text", buffer_size=1000)

    lines = read_metadata(clipboard_dir).split("\n")
    assert lines[0] == "{"
    assert lines[-2:] == ["}", ""]
    for line in lines[1:-2]:
        assert re.fullmatch(r'"[A-Za-z0-9_-]+":["A-Za-z0-9_-]+,?', line), line
    assert '"buffer_size":1000,' in lines


def test_clear(clipboard_dir):
    (clipboard_dir / "qubes-clipboard.bin").write_bytes(b"old content")
    global_clipboard.copy_to_global_clipboard(b"", cleared=True)

    assert (clipboard_dir / "qubes-clipboard.bin").read_bytes() == b""
    metadata = json.loads(read_metadata(clipboard_dir))
    assert metadata["cleared"] == 1
    assert metadata["copy_action"] == 0
    assert metadata["sent_size"] == 0
    assert metadata["xevent_timestamp"] == 0


@pytest.mark.usefixtures("clipboard_dir")
def test_files_written_under_lock_source_last(monkeypatch):
    written = []
    real_open = open

    def tracking_open(path, *args, **kwargs):
        # the lock must be held by somebody else for every write
        with real_open(global_clipboard.APPVIEWER_LOCK, "rb") as lock_file:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        written.append(os.path.basename(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(global_clipboard, "open", tracking_open, raising=False)
    global_clipboard.copy_to_global_clipboard(b"text")

    assert sorted(written) == sorted(
        [
            "qubes-clipboard.bin",
            "qubes-clipboard.bin.metadata",
            "qubes-clipboard.bin.xevent",
            "qubes-clipboard.bin.source",
        ]
    )
    assert written[-1] == "qubes-clipboard.bin.source"
    assert written.index("qubes-clipboard.bin") < written.index(
        "qubes-clipboard.bin.metadata"
    )
