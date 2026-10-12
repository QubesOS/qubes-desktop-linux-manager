#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2026  Akshat Lakhera <akshatlnct2024@gmail.com>
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
"""Copy text from dom0 to the Qubes global clipboard.

This is the command line equivalent of the "Copy dom0 clipboard" action of
the clipboard widget. It does not need a graphical session.

Exit codes:
  0  success
  1  cannot read the input or write the global clipboard, or empty input
  2  invalid arguments, or input is not UTF-8 text
  3  input is larger than the clipboard buffer and --truncate was not given
"""

import argparse
import sys

from qui.global_clipboard import (
    MAX_BUFFER_SIZE,
    MIN_BUFFER_SIZE,
    copy_to_global_clipboard,
)


def _buffer_size(value: str) -> int:
    size = int(value)
    if not MIN_BUFFER_SIZE <= size <= MAX_BUFFER_SIZE:
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_BUFFER_SIZE} and {MAX_BUFFER_SIZE}"
        )
    return size


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qubes-dom0-copy-to-clipboard",
        description="Copy text from dom0 to the Qubes global clipboard. "
        "Reads FILE, or standard input when FILE is omitted or '-'.",
        epilog="Then use the secure paste shortcut (Ctrl+Shift+V by default) "
        "in a qube to paste it there.",
    )
    parser.add_argument("file", metavar="FILE", nargs="?", default="-")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="wipe the global clipboard instead of copying to it",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="truncate input larger than the buffer size instead of failing",
    )
    parser.add_argument(
        "--max-size",
        metavar="BYTES",
        type=_buffer_size,
        default=MAX_BUFFER_SIZE,
        help=f"clipboard buffer size (default: {MAX_BUFFER_SIZE} bytes)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="do not print informational messages",
    )
    return parser


def _read_input(file_arg: str, quiet: bool) -> bytes:
    if file_arg == "-":
        if sys.stdin.isatty() and not quiet:
            print(
                "Reading from standard input, press Ctrl+D to finish...",
                file=sys.stderr,
            )
        return sys.stdin.buffer.read()
    with open(file_arg, "rb") as input_file:
        return input_file.read()


def _is_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _truncate_utf8(data: bytes, size: int) -> bytes:
    """Cut valid UTF-8 *data*, longer than *size* bytes, to at most *size*
    bytes without splitting a character."""
    # step back over continuation bytes (0b10xxxxxx) of a split character
    while size > 0 and data[size] & 0xC0 == 0x80:
        size -= 1
    return data[:size]


def main() -> int:
    args = _build_parser().parse_args()

    if args.clear:
        try:
            copy_to_global_clipboard(b"", buffer_size=args.max_size, cleared=True)
        except OSError as exc:
            print(f"Cannot wipe the global clipboard: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            print("Global clipboard wiped.", file=sys.stderr)
        return 0

    try:
        data = _read_input(args.file, args.quiet)
    except OSError as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 1

    if not data:
        print("Input is empty, nothing to copy.", file=sys.stderr)
        return 1

    if not _is_text(data):
        print(
            "Input contains binary data or invalid UTF-8. The global clipboard "
            "only supports UTF-8 text, use qvm-copy to transfer files.",
            file=sys.stderr,
        )
        return 2

    if len(data) > args.max_size:
        if not args.truncate:
            print(
                f"Input size ({len(data)} bytes) exceeds the global clipboard "
                f"buffer size ({args.max_size} bytes). Use qvm-copy to transfer "
                "large amounts of data, or pass --truncate.",
                file=sys.stderr,
            )
            return 3
        data = _truncate_utf8(data, args.max_size)
        if not args.quiet:
            print(f"Input truncated to {len(data)} bytes.", file=sys.stderr)

    try:
        copy_to_global_clipboard(data, buffer_size=args.max_size)
    except OSError as exc:
        print(f"Cannot write to the global clipboard: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Copied {len(data)} bytes to the global clipboard.", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
