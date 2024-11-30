# Stubs for systemd.journal

import logging

from typing import Optional

class JournalHandler(logging.Handler):
    def __init__(
        self, level: Optional[int] = ..., SYSLOG_IDENTIFIER: Optional[str] = ...
    ) -> None: ...

# vim: syntax=python tw=0
