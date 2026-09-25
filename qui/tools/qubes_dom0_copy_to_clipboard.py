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
"""Copy text from dom0 stdin or a file to the Qubes global clipboard.

Reads from a file path or standard input and writes it to the Qubes global
clipboard using the GUI Protocol 1.8 interface (appviewer.lock + .metadata).
This is the headless, scriptable equivalent of the GUI clipboard widget's
"Copy dom0 clipboard" button.

Exit codes:
  0  Success
  1  I/O error (cannot read input, cannot write clipboard files)
  2  Binary data detected (null bytes or invalid UTF-8)
  3  Data size exceeds buffer limit and --truncate was not passed
"""

import argparse
import sys
from typing import Optional

from qui.clipboard import copy_to_global_clipboard

_DEFAULT_BUFFER_SIZE = 256_000


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qubes-dom0-copy-to-clipboard",
        description=(
            "Copy text from dom0 to the Qubes global clipboard. "
            "Reads from FILE if given, otherwise from standard input."
        ),
        epilog=(
            "Use Ctrl+Shift+V in an AppVM to paste the global clipboard "
            "contents into that qube."
        ),
    )
    parser.add_argument(
        "file",
        metavar="FILE",
        nargs="?",
        help=(
            "File to read (use '-' to read from stdin explicitly). "
            "Defaults to stdin when omitted."
        ),
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Wipe the global clipboard instead of copying data to it.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help=(
            "Silently truncate input that exceeds the buffer size limit "
            "rather than aborting with an error."
        ),
    )
    parser.add_argument(
        "--max-size",
        metavar="BYTES",
        type=int,
        default=_DEFAULT_BUFFER_SIZE,
        help=(
            f"Override the clipboard buffer size limit "
            f"(default: {_DEFAULT_BUFFER_SIZE} bytes)."
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational messages on stderr.",
    )
    return parser


def _read_input(
    file_arg: Optional[str],
    quiet: bool,
) -> bytes:
    """Return raw bytes read from *file_arg* or stdin.

    Prints a prompt when stdin is an interactive TTY so the terminal does not
    appear hung.
    """
    if file_arg is None or file_arg == "-":
        if sys.stdin.isatty() and not quiet:
            print(
                "(Reading from stdin — press Ctrl+D to copy, Ctrl+C to cancel)...",
                file=sys.stderr,
            )
        try:
            raw = sys.stdin.buffer.read()
        except KeyboardInterrupt:
            # User pressed Ctrl+C; exit cleanly without a traceback.
            print("\nCancelled.", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            with open(file_arg, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print(f"Error: cannot read '{file_arg}': {exc}", file=sys.stderr)
            sys.exit(1)
    return raw


def _validate_text(raw: bytes) -> str:
    """Decode *raw* as UTF-8 text and reject binary content.

    Raises SystemExit(2) on binary data.
    """
    if b"\x00" in raw:
        print(
            "Error: Binary data detected (null byte found). "
            "The Qubes clipboard only supports text. "
            "Use 'qvm-copy' to transfer binary files between qubes.",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        print(
            "Error: Binary data detected (invalid UTF-8 sequence). "
            "The Qubes clipboard only supports text. "
            "Use 'qvm-copy' to transfer binary files between qubes.",
            file=sys.stderr,
        )
        sys.exit(2)
    return text


def main() -> int:
    """Entry point; returns an integer exit code."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.clear:
        try:
            copy_to_global_clipboard("", source="dom0", cleared=True)
        except OSError as exc:
            print(f"Error: cannot wipe global clipboard: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            print("Global clipboard wiped.", file=sys.stderr)
        return 0

    raw = _read_input(args.file, args.quiet)
    text = _validate_text(raw)
    encoded = text.encode("utf-8")
    size = len(encoded)

    if size > args.max_size:
        if args.truncate:
            # Truncate cleanly at a UTF-8 character boundary.
            encoded = encoded[: args.max_size]
            text = encoded.decode("utf-8", errors="ignore")
            size = len(encoded)
            if not args.quiet:
                print(
                    f"Warning: input truncated to {size} bytes "
                    f"(limit: {args.max_size} bytes).",
                    file=sys.stderr,
                )
        else:
            print(
                f"Error: data size ({size} bytes) exceeds global clipboard "
                f"limit ({args.max_size} bytes). "
                "Use 'qvm-copy' for large transfers, or pass '--truncate'.",
                file=sys.stderr,
            )
            return 3

    try:
        sent = copy_to_global_clipboard(
            text,
            source="dom0",
            buffer_size=args.max_size,
        )
    except OSError as exc:
        print(
            f"Error: cannot write to global clipboard: {exc}",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"Copied {sent} bytes to global clipboard.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
