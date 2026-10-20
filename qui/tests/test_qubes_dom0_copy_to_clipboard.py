"""Tests for the qubes-dom0-copy-to-clipboard tool."""

# pylint: disable=redefined-outer-name

import io
from unittest import mock

import pytest

from qui.tools import qubes_dom0_copy_to_clipboard as tool


class FakeStdin:
    def __init__(self, data=b"", tty=False):
        self.buffer = io.BytesIO(data)
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.fixture
def copy_mock():
    with mock.patch.object(tool, "copy_to_global_clipboard") as copy:
        yield copy


def run(monkeypatch, *args, stdin=b"", tty=False):
    monkeypatch.setattr("sys.argv", ["qubes-dom0-copy-to-clipboard", *args])
    monkeypatch.setattr("sys.stdin", FakeStdin(stdin, tty))
    return tool.main()


def test_copy_stdin(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, stdin="żółw\n".encode("utf-8")) == 0
    copy_mock.assert_called_once_with("żółw\n".encode("utf-8"), buffer_size=256000)
    assert capsys.readouterr().err == "Copied 8 bytes to the global clipboard.\n"


def test_copy_file(tmp_path, monkeypatch, capsys, copy_mock):
    path = tmp_path / "input.txt"
    path.write_bytes(b"from file")
    assert run(monkeypatch, "-q", str(path), stdin=b"not this") == 0
    copy_mock.assert_called_once_with(b"from file", buffer_size=256000)
    assert capsys.readouterr().err == ""


def test_copy_tty_prompt(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, "-", stdin=b"typed", tty=True) == 0
    copy_mock.assert_called_once_with(b"typed", buffer_size=256000)
    assert "Ctrl+D" in capsys.readouterr().err


def test_copy_tty_interrupted(monkeypatch, capsys, copy_mock):
    monkeypatch.setattr("sys.argv", ["qubes-dom0-copy-to-clipboard"])
    stdin = FakeStdin(tty=True)
    stdin.buffer = mock.Mock(**{"read.side_effect": KeyboardInterrupt})
    monkeypatch.setattr("sys.stdin", stdin)
    assert tool.main() == 1
    copy_mock.assert_not_called()
    assert "Cancelled." in capsys.readouterr().err


def test_missing_file(tmp_path, monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, str(tmp_path / "missing")) == 1
    copy_mock.assert_not_called()
    assert "Cannot read" in capsys.readouterr().err


def test_empty_input(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, stdin=b"") == 1
    copy_mock.assert_not_called()
    assert "empty" in capsys.readouterr().err


@pytest.mark.parametrize(
    "data",
    [b"text\0with null", b"\xff\xfe not utf-8", "żółw".encode("utf-16")],
)
def test_reject_binary(data, monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, stdin=data) == 2
    copy_mock.assert_not_called()
    assert "qvm-copy" in capsys.readouterr().err


def test_too_big(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, "--max-size", "256", stdin=b"x" * 257) == 3
    copy_mock.assert_not_called()
    assert "--truncate" in capsys.readouterr().err


@pytest.mark.parametrize(
    "data, expected",
    [
        # cut exactly at a character boundary
        (b"x" * 300, b"x" * 256),
        # 3-byte character at offset 255 would be split
        (b"x" * 255 + "€uro".encode("utf-8"), b"x" * 255),
        # 2-byte character at offset 254 fits exactly
        (b"x" * 254 + "ł".encode("utf-8") + b"x", b"x" * 254 + "ł".encode("utf-8")),
    ],
)
def test_truncate(data, expected, monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, "--truncate", "--max-size", "256", stdin=data) == 0
    copy_mock.assert_called_once_with(expected, buffer_size=256)
    assert f"truncated to {len(expected)} bytes" in capsys.readouterr().err


@pytest.mark.parametrize("size", ["255", "256001", "abc"])
def test_invalid_max_size(size, monkeypatch, copy_mock):
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, "--max-size", size, stdin=b"text")
    assert exc.value.code == 2
    copy_mock.assert_not_called()


def test_write_error(monkeypatch, capsys, copy_mock):
    copy_mock.side_effect = PermissionError("denied")
    assert run(monkeypatch, stdin=b"text") == 1
    assert "Cannot write to the global clipboard: denied" in capsys.readouterr().err


def test_clear(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, "--clear", stdin=b"ignored") == 0
    copy_mock.assert_called_once_with(b"", buffer_size=256000, cleared=True)
    assert capsys.readouterr().err == "Global clipboard wiped.\n"


def test_clear_quiet(monkeypatch, capsys, copy_mock):
    assert run(monkeypatch, "--clear", "-q") == 0
    copy_mock.assert_called_once_with(b"", buffer_size=256000, cleared=True)
    assert capsys.readouterr().err == ""


def test_clear_error(monkeypatch, capsys, copy_mock):
    copy_mock.side_effect = OSError("failed")
    assert run(monkeypatch, "--clear") == 1
    assert "Cannot wipe the global clipboard: failed" in capsys.readouterr().err


def test_end_to_end(tmp_path, monkeypatch):
    """Real write to the clipboard files, without mocking the helper."""
    clipboard = tmp_path / "qubes-clipboard.bin"
    for name, path in {
        "DATA": clipboard,
        "METADATA": tmp_path / "metadata",
        "FROM": tmp_path / "source",
        "XEVENT": tmp_path / "xevent",
        "APPVIEWER_LOCK": tmp_path / "lock",
    }.items():
        monkeypatch.setattr(f"qui.global_clipboard.{name}", str(path))
    assert run(monkeypatch, "-q", stdin=b"hello") == 0
    assert clipboard.read_bytes() == b"hello"
    assert (tmp_path / "source").read_text("ascii") == "dom0"
