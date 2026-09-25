#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2025  Akshat Lakhera <dummy@example.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
"""Tests for qui.tools.qubes_dom0_copy_to_clipboard and the
copy_to_global_clipboard() helper in qui.clipboard."""

import json
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures: redirect clipboard file paths to a tmp directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def clipboard_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Redirect all clipboard file paths to a temporary directory."""
    data = str(tmp_path / "qubes-clipboard.bin")
    metadata = str(tmp_path / "qubes-clipboard.bin.metadata")
    source = str(tmp_path / "qubes-clipboard.bin.source")
    xevent = str(tmp_path / "qubes-clipboard.bin.xevent")
    lock = str(tmp_path / "appviewer.lock")

    with (
        patch("qui.clipboard.DATA", data),
        patch("qui.clipboard.METADATA", metadata),
        patch("qui.clipboard.FROM", source),
        patch("qui.clipboard.XEVENT", xevent),
        patch("qui.clipboard.APPVIEWER_LOCK", lock),
    ):
        yield tmp_path


# ---------------------------------------------------------------------------
# Tests for copy_to_global_clipboard()
# ---------------------------------------------------------------------------

# Import here so the module-level patch applies cleanly in the fixture above.
from qui.clipboard import copy_to_global_clipboard  # noqa: E402


class TestCopyToGlobalClipboard:
    """Unit tests for the copy_to_global_clipboard() helper."""

    def test_stdin_text_written_to_data_file(self, clipboard_dir: Path) -> None:
        """Copy from a text string; DATA file should contain its UTF-8 bytes."""
        text = "Hello, Qubes OS!"
        copy_to_global_clipboard(text, source="dom0")

        data_bytes = (clipboard_dir / "qubes-clipboard.bin").read_bytes()
        assert data_bytes == text.encode("utf-8")

    def test_source_file_contains_trailing_newline(self, clipboard_dir: Path) -> None:
        """SOURCE file must end with '\\n' so qui-clipboard parses it correctly."""
        copy_to_global_clipboard("hello", source="dom0")

        source_content = (clipboard_dir / "qubes-clipboard.bin.source").read_text(
            encoding="ascii"
        )
        assert source_content == "dom0\n"

    def test_metadata_is_valid_json(self, clipboard_dir: Path) -> None:
        """METADATA file must be parseable by json.loads (no trailing commas)."""
        copy_to_global_clipboard("test data", source="dom0")

        raw = (clipboard_dir / "qubes-clipboard.bin.metadata").read_text(
            encoding="ascii"
        )
        # Raises json.JSONDecodeError if the file contains a trailing comma.
        parsed = json.loads(raw)
        assert parsed["vmname"] == "dom0"
        assert parsed["successful"] == 1
        assert parsed["copy_action"] == 1
        assert parsed["cleared"] == 0

    def test_metadata_no_trailing_comma(self, clipboard_dir: Path) -> None:
        """Explicit regression test: no trailing comma before closing brace."""
        copy_to_global_clipboard("regression check", source="dom0")

        raw = (clipboard_dir / "qubes-clipboard.bin.metadata").read_text(
            encoding="ascii"
        )
        # The old code had '\"protocol_version_vmside\":65544,\n}}'
        # A trailing comma would cause json.loads to raise.
        assert ",\n}" not in raw, "Trailing comma found before closing brace"

    def test_returns_byte_count(self, clipboard_dir: Path) -> None:
        """Return value should equal the number of UTF-8 bytes written."""
        text = "αβγ"  # 6 bytes in UTF-8 (3 × 2-byte characters)
        result = copy_to_global_clipboard(text, source="dom0")
        assert result == len(text.encode("utf-8"))

    def test_cleared_flag_sets_metadata(self, clipboard_dir: Path) -> None:
        """When cleared=True the METADATA JSON must reflect that."""
        copy_to_global_clipboard("", source="dom0", cleared=True)

        raw = (clipboard_dir / "qubes-clipboard.bin.metadata").read_text(
            encoding="ascii"
        )
        parsed = json.loads(raw)
        assert parsed["cleared"] == 1
        assert parsed["copy_action"] == 0
        assert parsed["sent_size"] == 0

    def test_write_order_source_is_last(self, clipboard_dir: Path) -> None:
        """SOURCE must be written after DATA and METADATA (inotify ordering)."""
        write_order: list[str] = []

        original_open = open  # noqa: A001

        def tracking_open(path: str, *args, **kwargs):  # type: ignore[override]
            fh = original_open(path, *args, **kwargs)
            if str(clipboard_dir) in str(path):
                write_order.append(os.path.basename(str(path)))
            return fh

        with patch("builtins.open", side_effect=tracking_open):
            copy_to_global_clipboard("order test", source="dom0")

        # SOURCE ("qubes-clipboard.bin.source") must be the very last write.
        assert (
            write_order[-1] == "qubes-clipboard.bin.source"
        ), f"Expected SOURCE to be written last. Actual order: {write_order}"

    def test_xevent_file_written(self, clipboard_dir: Path) -> None:
        """XEVENT file must be written and contain an integer timestamp."""
        copy_to_global_clipboard("xevent test", source="dom0", timestamp=12345)

        xevent = (clipboard_dir / "qubes-clipboard.bin.xevent").read_text(
            encoding="ascii"
        )
        assert xevent.strip().isdigit()

    def test_custom_buffer_size_in_metadata(self, clipboard_dir: Path) -> None:
        """buffer_size argument should be reflected in METADATA JSON."""
        copy_to_global_clipboard("buf size", source="dom0", buffer_size=128_000)

        raw = (clipboard_dir / "qubes-clipboard.bin.metadata").read_text(
            encoding="ascii"
        )
        parsed = json.loads(raw)
        assert parsed["buffer_size"] == 128_000


# ---------------------------------------------------------------------------
# Tests for the CLI tool (qubes_dom0_copy_to_clipboard.main)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_copy(clipboard_dir: Path):
    """Patch copy_to_global_clipboard inside the CLI module."""
    with patch(
        "qui.tools.qubes_dom0_copy_to_clipboard.copy_to_global_clipboard"
    ) as mock_copy:
        mock_copy.return_value = 42
        yield mock_copy


class TestCLI:
    """Integration tests for the CLI entry point."""

    def _run(
        self,
        argv: list[str],
        stdin_bytes: bytes = b"",
    ) -> tuple[int, str, str]:
        """Run main() with mocked argv and stdin; return (exit_code, stdout, stderr)."""
        import io
        from unittest.mock import patch as _patch

        from qui.tools.qubes_dom0_copy_to_clipboard import main

        mock_stdin = MagicMock()
        mock_stdin.buffer.read.return_value = stdin_bytes
        mock_stdin.isatty.return_value = False

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with (
            _patch("sys.argv", ["qubes-dom0-copy-to-clipboard"] + argv),
            _patch("sys.stdin", mock_stdin),
            _patch("sys.stdout", stdout_buf),
            _patch("sys.stderr", stderr_buf),
        ):
            exit_code = main()

        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_copy_from_stdin(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 0 when valid text is piped through stdin."""
        exit_code, _, _ = self._run([], stdin_bytes=b"hello from stdin")
        assert exit_code == 0
        _patch_copy.assert_called_once()

    def test_copy_from_file(
        self,
        tmp_path: Path,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 0 when a valid text file path is supplied."""
        src = tmp_path / "input.txt"
        src.write_text("hello from file", encoding="utf-8")

        exit_code, _, _ = self._run([str(src)])
        assert exit_code == 0
        _patch_copy.assert_called_once()

    def test_reject_binary_null_byte(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 2 on null bytes; copy_to_global_clipboard must not be called."""
        exit_code, _, stderr = self._run([], stdin_bytes=b"hello\x00world")
        assert exit_code == 2
        assert "Binary data detected" in stderr
        _patch_copy.assert_not_called()

    def test_reject_invalid_utf8(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 2 on invalid UTF-8; copy_to_global_clipboard must not be called."""
        exit_code, _, stderr = self._run([], stdin_bytes=b"\xff\xfe invalid utf8")
        assert exit_code == 2
        assert "Binary data detected" in stderr
        _patch_copy.assert_not_called()

    def test_reject_oversized_without_truncate(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 3 when data exceeds buffer limit and --truncate is not set."""
        big = b"x" * 300_000
        exit_code, _, stderr = self._run([], stdin_bytes=big)
        assert exit_code == 3
        assert "exceeds" in stderr
        _patch_copy.assert_not_called()

    def test_accept_oversized_with_truncate(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 0 when data exceeds limit but --truncate is passed."""
        big = b"y" * 300_000
        exit_code, _, _ = self._run(["--truncate"], stdin_bytes=big)
        assert exit_code == 0
        _patch_copy.assert_called_once()

    def test_quiet_suppresses_output(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """--quiet should produce no output on stderr."""
        exit_code, _, stderr = self._run(["-q"], stdin_bytes=b"quiet test")
        assert exit_code == 0
        assert stderr == ""

    def test_clear_flag(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """--clear should call copy_to_global_clipboard with cleared=True."""
        exit_code, _, _ = self._run(["--clear"])
        assert exit_code == 0
        _patch_copy.assert_called_once()
        call_kwargs = _patch_copy.call_args
        assert call_kwargs.kwargs.get("cleared") is True

    def test_exit_code_1_on_io_error(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 1 when copy_to_global_clipboard raises OSError."""
        _patch_copy.side_effect = OSError("disk full")
        exit_code, _, stderr = self._run([], stdin_bytes=b"some text")
        assert exit_code == 1
        assert "cannot write" in stderr

    def test_missing_file_exits_1(
        self,
        clipboard_dir: Path,
        _patch_copy: MagicMock,
    ) -> None:
        """Exit 1 when the supplied file path does not exist."""
        exit_code, _, stderr = self._run(["/nonexistent/path/file.txt"])
        assert exit_code == 1
        assert "cannot read" in stderr
        _patch_copy.assert_not_called()
