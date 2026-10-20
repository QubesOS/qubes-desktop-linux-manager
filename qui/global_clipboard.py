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
"""Write access to the Qubes global clipboard files.

This module intentionally does not import GTK, so it can be used by command
line tools running outside of a graphical session.
"""

import contextlib
import fcntl
import json
import os

DATA = "/var/run/qubes/qubes-clipboard.bin"
METADATA = "/var/run/qubes/qubes-clipboard.bin.metadata"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"
XEVENT = "/var/run/qubes/qubes-clipboard.bin.xevent"
APPVIEWER_LOCK = "/var/run/qubes/appviewer.lock"

# GUI protocol 1.8, the first one using the .metadata file
PROTOCOL_VERSION = 0x00010008
# MIN_CLIPBOARD_BUFFER_SIZE and MAX_CLIPBOARD_BUFFER_SIZE from
# qubes-gui-protocol.h
MIN_BUFFER_SIZE = 256
MAX_BUFFER_SIZE = 256000


@contextlib.contextmanager
def appviewer_lock():
    fd = os.open(APPVIEWER_LOCK, os.O_RDWR | os.O_CREAT, 0o0666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def copy_to_global_clipboard(
    data: bytes,
    timestamp: int = 0,
    buffer_size: int = MAX_BUFFER_SIZE,
    cleared: bool = False,
) -> None:
    """Put UTF-8 encoded *data* into the global clipboard as copied from dom0.

    *timestamp* is the X server time of the user action that triggered the
    copy. qubes-guid ignores a secure paste key press older than it, so
    callers without an X event must keep the default 0, which never blocks a
    paste.

    With *cleared* set, the clipboard is wiped instead (pass empty *data*).
    """
    metadata = {
        "vmname": "dom0",
        "xevent_timestamp": timestamp,
        "successful": 1,
        "copy_action": int(not cleared),
        "paste_action": 0,
        "malformed_request": 0,
        "oversized_request": 0,
        "cleared": int(cleared),
        "qrexec_clipboard": 0,
        "sent_size": len(data),
        "buffer_size": buffer_size,
        "protocol_version_xside": PROTOCOL_VERSION,
        "protocol_version_vmside": PROTOCOL_VERSION,
    }

    with appviewer_lock():
        with open(DATA, "wb") as contents:
            contents.write(data)
        with open(XEVENT, "w", encoding="ascii") as xevent:
            xevent.write(str(timestamp))
        with open(METADATA, "w", encoding="ascii") as metadata_file:
            # qubes-guid parses this file line by line, expecting exactly one
            # "key":value pair per line and no whitespace
            metadata_file.write(
                json.dumps(metadata, indent=0, separators=(",", ":")) + "\n"
            )
        # qui-clipboard watches the source file, so write it last
        with open(FROM, "w", encoding="ascii") as source:
            source.write("dom0")
