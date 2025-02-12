#!/usr/bin/env python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2017 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright (C) 2017 itinerarium <code@0n0e.com>
# Copyright (C) 2016 Jean-Philippe Ouellet <jpo@vt.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# pylint: disable=import-error

""" Sends notifications via Gio.Notification when something is Copy-Pasted
via Qubes RPC """
# pylint: disable=invalid-name,wrong-import-position

import asyncio
import contextlib
import json
import math
import os
import fcntl
import qubesadmin
import qubesadmin.events

import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, Gio, Gdk  # isort:skip

import gbulb
import pyinotify

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

from .utils import run_asyncio_and_show_errors

gbulb.install()

DATA = "/var/run/qubes/qubes-clipboard.bin"
METADATA = "/var/run/qubes/qubes-clipboard.bin.metadata"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"
FROM_DIR = "/var/run/qubes/"
XEVENT = "/var/run/qubes/qubes-clipboard.bin.xevent"
APPVIEWER_LOCK = "/var/run/qubes/appviewer.lock"
COPY_FEATURE = "gui-default-secure-copy-sequence"
PASTE_FEATURE = "gui-default-secure-paste-sequence"

# Defining all messages in one place for easy modification
ERROR_MALFORMED_DATA = _(
    "Malformed clipboard data received from qube: <b>{vmname}</b>"
)
ERROR_ON_COPY = _("Failed to fetch clipboard data from qube: <b>{vmname}</b>")
ERROR_ON_PASTE = _(
    "Failed to paste global clipboard contents to qube: <b>{vmname}</b>"
)
ERROR_OVERSIZED_DATA = _(
    "Global clipboard size exceeded.\n"
    "qube: <b>{vmname}</b> attempted to send {size} bytes to global clipboard."
    "\nCurrent global clipboard limit is {limit}, increase limit or use "
    "<i>qvm-copy</i> to transfer large amounts of data between qubes."
)
WARNING_POSSIBLE_TRUNCATION = _(
    "Global clipboard size limit exceed.\n"
    "qube: <b>{vmname}</b> attempted to send {size} bytes to global clipboard."
    "\nGlobal clipboard might have been truncated.\n"
    "<small>Use <i>qvm-copy</i> to transfer large amounts of data between "
    "qubes.</small>"
)
WARNING_EMPTY_CLIPBOARD = _(
    "Empty source qube clipboard.\n"
    "qube: <b>{vmname}</b> attempted to send <b>0</b> bytes to global "
    "clipboard."
)
MSG_COPY_SUCCESS = _(
    "Clipboard contents fetched from qube: <b>'{vmname}'</b>\n"
    "Copied <b>{size}</b> to the global clipboard.\n"
    "<small>Press {shortcut} in qube to paste to local clipboard.</small>"
)
MSG_WIPED = _("\n<small>Global clipboard has been wiped</small>")
MSG_PASTE_SUCCESS_METADATA = _(
    "Global clipboard copied <b>{size}</b> to <b>{vmname}</b>.\n"
    "Global clipboard has been wiped.\n"
    "<small>Paste normally in qube (e.g. Ctrl+V).</small>"
)
MSG_PASTE_SUCCESS_LEGACY = _(
    "Global clipboard copied to qube and wiped.<i/>\n"
    "<small>Paste normally in qube (e.g. Ctrl+V).</small>"
)


@contextlib.contextmanager
def appviewer_lock():
    fd = os.open(APPVIEWER_LOCK, os.O_RDWR | os.O_CREAT, 0o0666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class EventHandler(pyinotify.ProcessEvent):
    # pylint: disable=arguments-differ
    def my_init(self, loop=None, gtk_app=None):
        """This method is called from ProcessEvent.__init__()."""
        self.gtk_app = gtk_app
        self.loop = loop if loop else asyncio.get_event_loop()

    def _copy(self, metadata: dict) -> None:
        """Sends Copy notification via Gio.Notification"""
        size = clipboard_formatted_size(metadata["sent_size"])

        if metadata["malformed_request"]:
            body = ERROR_MALFORMED_DATA.format(vmname=metadata["vmname"])
            icon = "dialog-error"
        elif (
            metadata["qrexec_clipboard"]
            and metadata["sent_size"] >= metadata["buffer_size"]
        ):
            # Microsoft Windows clipboard case
            body = WARNING_POSSIBLE_TRUNCATION.format(
                vmname=metadata["vmname"], size=size
            )
            icon = "dialog-warning"
        elif metadata["oversized_request"]:
            body = ERROR_OVERSIZED_DATA.format(
                vmname=metadata["vmname"],
                size=size,
                limit=clipboard_formatted_size(metadata["buffer_size"]),
            )
            icon = "dialog-error"
        elif (
            metadata["successful"]
            and metadata["cleared"]
            and metadata["sent_size"] == 0
        ):
            body = WARNING_EMPTY_CLIPBOARD.format(vmname=metadata["vmname"])
            icon = "dialog-warning"
        elif not metadata["successful"]:
            body = ERROR_ON_COPY.format(vmname=metadata["vmname"])
            icon = "dialog-error"
        else:
            body = MSG_COPY_SUCCESS.format(
                vmname=metadata["vmname"],
                size=size,
                shortcut=self.gtk_app.paste_shortcut,
            )
            icon = "dialog-information"

        if metadata["cleared"]:
            body += MSG_WIPED

        self.gtk_app.update_clipboard_contents(
            metadata["vmname"], size, message=body, icon=icon
        )

    def _paste(self, metadata: dict) -> None:
        """Sends Paste notification via Gio.Notification."""
        if not metadata["successful"] or metadata["malformed_request"]:
            body = ERROR_ON_PASTE.format(vmname=metadata["vmname"])
            body += MSG_WIPED
            icon = "dialog-error"
        elif (
            "protocol_version_xside" in metadata.keys()
            and metadata["protocol_version_xside"] >= 0x00010008
        ):
            body = MSG_PASTE_SUCCESS_METADATA.format(
                size=clipboard_formatted_size(metadata["sent_size"]),
                vmname=metadata["vmname"],
            )
            icon = "dialog-information"
        else:
            body = MSG_PASTE_SUCCESS_LEGACY
            icon = "dialog-information"
        self.gtk_app.update_clipboard_contents(message=body, icon=icon)

    def process_IN_CLOSE_WRITE(self, _unused=None):
        """Reacts to modifications of the FROM file"""
        metadata = {}
        with appviewer_lock():
            if os.path.isfile(METADATA) and os.path.getmtime(
                METADATA
            ) >= os.path.getmtime(DATA):
                # parse JSON .metadata file if qubes-guid protocol 1.8 or newer
                try:
                    with open(METADATA, "r", encoding="ascii") as metadata_file:
                        metadata = json.loads(metadata_file.read())
                except OSError:
                    return
                except json.decoder.JSONDecodeError:
                    return
            else:
                # revert to .source file on qubes-guid protocol 1.7 or older
                # synthesize metadata based on limited available information
                with open(FROM, "r", encoding="ascii") as vm_from_file:
                    metadata["vmname"] = vm_from_file.readline().strip("\n")

                metadata["copy_action"] = metadata["vmname"] != ""
                metadata["paste_action"] = metadata["vmname"] == ""

                try:
                    metadata["sent_size"] = os.path.getsize(DATA)
                except OSError:
                    metadata["sent_size"] = 0

                metadata["cleared"] = metadata["sent_size"] == 0
                metadata["qrexec_clipboard"] = False
                metadata["malformed_request"] = False
                metadata["oversized_request"] = metadata["sent_size"] >= 65000
                metadata["buffer_size"] = 65000

                if metadata["copy_action"] and metadata["sent_size"] == 0:
                    metadata["successful"] = False
                else:
                    metadata["successful"] = True

        if metadata["copy_action"]:
            self._copy(metadata=metadata)
        elif metadata["paste_action"]:
            self._paste(metadata=metadata)

    def process_IN_MOVE_SELF(self, _unused):
        """Stop loop if file is moved"""
        self.loop.stop()

    def process_IN_DELETE(self, _unused):
        """Stop loop if file is deleted"""
        self.loop.stop()

    def process_IN_CREATE(self, event):
        if event.pathname == FROM:
            self.process_IN_CLOSE_WRITE()
            self.gtk_app.setup_watcher()


def clipboard_formatted_size(size: int = None) -> str:
    units = ["B", "KiB", "MiB", "GiB"]

    try:
        if size:
            file_size = size
        else:
            file_size = os.path.getsize(DATA)
    except OSError:
        return _("? bytes")
    if file_size == 1:
        formatted_bytes = _("1 byte")
    else:
        formatted_bytes = str(file_size) + _(" bytes")

    if file_size > 0:
        magnitude = min(
            int(math.log(file_size) / math.log(2) * 0.1), len(units) - 1
        )
        if magnitude > 0:
            # pylint: disable=consider-using-f-string
            return "%s (%.1f %s)" % (
                formatted_bytes,
                file_size / (2.0 ** (10 * magnitude)),
                units[magnitude],
            )
    # pylint: disable=consider-using-f-string
    return "%s" % (formatted_bytes)


class NotificationApp(Gtk.Application):
    def __init__(self, wm, qapp, dispatcher, **properties):
        super().__init__(**properties)
        self.set_application_id("org.qubes.qui.clipboard")
        self.register()  # register Gtk Application

        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]
        self.dispatcher = dispatcher

        self.icon = Gtk.StatusIcon()
        self.icon.set_from_icon_name("qui-clipboard")
        self.icon.set_tooltip_markup(
            _(
                "<b>Global Clipboard</b>\nInformation about the current"
                " state of the global clipboard."
            )
        )
        self.icon.connect("button-press-event", self.show_menu)

        self.menu = Gtk.Menu()
        self.clipboard_label = Gtk.Label(xalign=0)

        self.copy_shortcut = None
        self.paste_shortcut = None
        self.setup_ui()

        self.wm = wm
        self.temporary_watch = None

        if not os.path.exists(FROM):
            # pylint: disable=no-member
            self.temporary_watch = self.wm.add_watch(
                FROM_DIR, pyinotify.IN_CREATE, rec=False
            )
        else:
            self.setup_watcher()

        for feature in [COPY_FEATURE, PASTE_FEATURE]:
            self.dispatcher.add_handler(
                f"domain-feature-set:{feature}", self.setup_ui
            )
            self.dispatcher.add_handler(
                f"domain-feature-delete:{feature}", self.setup_ui
            )

    def setup_watcher(self):
        if self.temporary_watch:
            for wd in self.temporary_watch.values():
                self.wm.rm_watch(wd)
        mask = pyinotify.ALL_EVENTS
        self.wm.add_watch(FROM, mask)

    def show_menu(self, _unused, event):
        self.menu.show_all()
        self.menu.popup(
            None,  # parent_menu_shell
            None,  # parent_menu_item
            None,  # func
            None,  # data
            event.button,  # button
            Gtk.get_current_event_time(),
        )  # activate_time

    def update_clipboard_contents(
        self, vm=None, size=0, message=None, icon=None
    ):
        if not vm or not size:
            self.clipboard_label.set_markup(
                _("<i>Global clipboard is empty</i>")
            )
            self.icon.set_from_icon_name("qui-clipboard")
            # todo the icon should be empty and full depending on state

        else:
            self.clipboard_label.set_markup(
                _(
                    "<i>Global clipboard contents: {0} from <b>{1}</b></i>"
                ).format(size, vm)
            )
            self.icon.set_from_icon_name("qui-clipboard")

        if message:
            self.send_notify(message, icon=icon)

    def setup_ui(self, *_args, **_kwargs):
        self.copy_shortcut = self._prettify_shortcut(
            self.vm.features.get(COPY_FEATURE, "Ctrl-Shift-C")
        )
        self.paste_shortcut = self._prettify_shortcut(
            self.vm.features.get(PASTE_FEATURE, "Ctrl-Shift-V")
        )

        self.menu = Gtk.Menu()

        title_label = Gtk.Label(xalign=0)
        title_label.set_markup(_("<b>Current clipboard</b>"))
        title_item = Gtk.MenuItem()
        title_item.set_sensitive(False)
        title_item.add(title_label)
        self.menu.append(title_item)

        clipboard_content_item = Gtk.MenuItem()
        clipboard_content_item.set_sensitive(False)
        clipboard_content_item.add(self.clipboard_label)
        self.update_clipboard_contents()
        self.menu.append(clipboard_content_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        help_label = Gtk.Label(xalign=0)
        help_label.set_markup(
            _(
                "<i>Use <b>{copy}</b> to copy and "
                "<b>{paste}</b> to paste.</i>"
            ).format(copy=self.copy_shortcut, paste=self.paste_shortcut)
        )
        help_item = Gtk.MenuItem()
        help_item.set_margin_left(10)
        help_item.set_sensitive(False)
        help_item.add(help_label)
        self.menu.append(help_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        dom0_item = Gtk.MenuItem(_("Copy dom0 clipboard"))
        dom0_item.connect("activate", self.copy_dom0_clipboard)
        self.menu.append(dom0_item)

    def copy_dom0_clipboard(self, *_args, **_kwargs):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()

        if not text:
            self.send_notify(
                _("Dom0 clipboard is empty!"), icon="dialog-information"
            )
            return

        try:
            with appviewer_lock():
                with open(DATA, "w", encoding="utf-8") as contents:
                    contents.write(text)
                with open(FROM, "w", encoding="ascii") as source:
                    source.write("dom0")
                with open(XEVENT, "w", encoding="ascii") as timestamp:
                    timestamp.write(str(Gtk.get_current_event_time()))
                with open(METADATA, "w", encoding="ascii") as metadata:
                    metadata.write(
                        "{{\n"
                        '"vmname":"dom0",\n'
                        '"xevent_timestamp":{xevent_timestamp},\n'
                        '"successful":1,\n'
                        '"copy_action":1,\n'
                        '"paste_action":0,\n'
                        '"malformed_request":0,\n'
                        '"cleared":0,\n'
                        '"qrexec_clipboard":0,\n'
                        '"sent_size":{sent_size},\n'
                        '"buffer_size":{buffer_size},\n'
                        '"protocol_version_xside":65544,\n'
                        '"protocol_version_vmside":65544,\n'
                        "}}\n".format(
                            xevent_timestamp=str(Gtk.get_current_event_time()),
                            sent_size=os.path.getsize(DATA),
                            buffer_size="256000",
                        )
                    )
        except Exception:  # pylint: disable=broad-except
            self.send_notify(
                _("Error while accessing global clipboard!"),
                icon="dialog-error",
            )

    def send_notify(self, body, icon=None):
        # pylint: disable=attribute-defined-outside-init
        notification = Gio.Notification.new(_("Global Clipboard"))
        notification.set_body(body)
        notification.set_priority(Gio.NotificationPriority.NORMAL)
        if icon is not None:
            notification.set_icon(Gio.ThemedIcon.new(icon))
        self.send_notification(self.get_application_id(), notification)

    def _prettify_shortcut(self, shortcut: str):
        """Turn a keyboard shortcut into a nicer, more readable version,
        e.g. convert 'Ctrl-Mod4-c' into 'Ctrl-Win-C'"""
        parts = shortcut.split("-")
        return "+".join([self._convert_to_readable(part) for part in parts])

    @staticmethod
    def _convert_to_readable(key: str):
        if key == "Mod4":
            return "Win"
        if key == "Ins":
            return "Insert"
        if len(key) == 1:
            return key.upper()
        return key


def main():
    loop = asyncio.get_event_loop()
    wm = pyinotify.WatchManager()

    qubes_app = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qubes_app)

    gtk_app = NotificationApp(wm, qubes_app, dispatcher)

    handler = EventHandler(loop=loop, gtk_app=gtk_app)
    pyinotify.AsyncioNotifier(wm, loop, default_proc_fun=handler)

    return run_asyncio_and_show_errors(
        loop,
        [asyncio.ensure_future(dispatcher.listen_for_events())],
        _("Qubes Clipboard Widget"),
    )


if __name__ == "__main__":
    main()
