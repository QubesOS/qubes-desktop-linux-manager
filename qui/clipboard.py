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

''' Sends notifications via Gio.Notification when something is Copy-Pasted
via Qubes RPC '''
# pylint: disable=invalid-name,wrong-import-position

import asyncio
import contextlib
import math
import os
import fcntl
import qubesadmin
import qubesadmin.events

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Gio, Gdk, GLib  # isort:skip

import gbulb
import pyinotify

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

from .utils import run_asyncio_and_show_errors

gbulb.install()

DATA = "/var/run/qubes/qubes-clipboard.bin"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"
FROM_DIR = "/var/run/qubes/"
XEVENT = "/var/run/qubes/qubes-clipboard.bin.xevent"
APPVIEWER_LOCK = "/var/run/qubes/appviewer.lock"
COPY_FEATURE = 'gui-default-secure-copy-sequence'
PASTE_FEATURE = 'gui-default-secure-paste-sequence'


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
        '''  This method is called from ProcessEvent.__init__(). '''
        self.gtk_app = gtk_app
        self.loop = loop if loop else asyncio.get_event_loop()

    def _copy(self, vmname: str = None):
        ''' Sends Copy notification via Gio.Notification
        '''
        if vmname is None:
            with appviewer_lock():
                with open(FROM, 'r', encoding='ascii') as vm_from_file:
                    vmname = vm_from_file.readline().strip('\n')

        size = clipboard_formatted_size()

        body = _("Clipboard contents fetched from qube: <b>'{vmname}'</b>\n"
                 "Copied <b>{size}</b> to the global clipboard.\n"
                 "<small>Press {shortcut} in qube "
                 "to paste to local clipboard.</small>".format(
            vmname=vmname, size=size, shortcut=self.gtk_app.paste_shortcut))

        self.gtk_app.update_clipboard_contents(vmname, size, message=body)

        if self.gtk_app.clear_event_source_id is not None:
            # If there is any clipboard clearing event in event loop, cancel it
            GLib.source_remove(self.gtk_app.clear_event_source_id)
            self.gtk_app.clear_event_source_id = None

        try:
            clear_timeout = self.gtk_app.qapp.domains[vmname].features[ \
                "global-clipboard-timeout"]
        except qubesadmin.exc.QubesException:
            clear_timeout = None
        if clear_timeout is None:
            try:
                clear_timeout = self.gtk_app.qapp.domains[ \
                    self.gtk_app.qapp.local_name].features[ \
                    "global-clipboard-timeout"]
            except qubesadmin.exc.QubesException:
                clear_timeout = None
        if clear_timeout is not None and clear_timeout.isnumeric() and \
                int(clear_timeout) > 0:
            self.gtk_app.clear_event_source_id = GLib.timeout_add_seconds(
                int(clear_timeout), self.gtk_app.clear_clipboard_event, \
                os.path.getmtime(DATA))

    def _paste(self):
        ''' Sends Paste notification via Gio.Notification.
        '''
        body = _("Global clipboard contents copied to qube and wiped.<i/>\n"
                 "<small>Paste normally in qube (e.g. Ctrl+V).</small>")
        self.gtk_app.update_clipboard_contents(message=body)

    def process_IN_CLOSE_WRITE(self, _unused):
        ''' Reacts to modifications of the FROM file '''
        with appviewer_lock():
            with open(FROM, 'r', encoding='ascii') as vm_from_file:
                vmname = vm_from_file.readline().strip('\n')
        if vmname == "":
            self._paste()
        else:
            self._copy(vmname=vmname)

    def process_IN_MOVE_SELF(self, _unused):
        ''' Stop loop if file is moved '''
        self.loop.stop()

    def process_IN_DELETE(self, _unused):
        ''' Stop loop if file is deleted '''
        self.loop.stop()

    def process_IN_CREATE(self, event):
        if event.pathname == FROM:
            self._copy()
            self.gtk_app.setup_watcher()


def clipboard_formatted_size() -> str:
    units = ['B', 'KiB', 'MiB', 'GiB']

    try:
        file_size = os.path.getsize(DATA)
    except OSError:
        return _('? bytes')
    if file_size == 1:
        formatted_bytes = _('1 byte')
    else:
        formatted_bytes = str(file_size) + _(' bytes')

    if file_size > 0:
        magnitude = min(
            int(math.log(file_size) / math.log(2) * 0.1), len(units) - 1)
        if magnitude > 0:
            # pylint: disable=consider-using-f-string
            return '%s (%.1f %s)' % (formatted_bytes,
                                     file_size / (2.0**(10 * magnitude)),
                                     units[magnitude])
    # pylint: disable=consider-using-f-string
    return '%s' % (formatted_bytes)


class NotificationApp(Gtk.Application):
    def __init__(self, wm, qapp, dispatcher, **properties):
        super().__init__(**properties)
        self.set_application_id("org.qubes.qui.clipboard")
        self.register()  # register Gtk Application

        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]
        self.dispatcher = dispatcher

        self.icon = Gtk.StatusIcon()
        self.icon.set_from_icon_name('edit-copy')
        self.icon.set_tooltip_markup(
            _('<b>Global Clipboard</b>\nInformation about the current'
              ' state of the global clipboard.'))
        self.icon.connect('button-press-event', self.show_menu)

        self.menu = Gtk.Menu()
        self.clipboard_label = Gtk.Label(xalign=0)

        self.copy_shortcut = None
        self.paste_shortcut = None
        self.setup_ui()

        self.wm = wm
        self.temporary_watch = None

        self.clear_event_source_id: int = None

        if not os.path.exists(FROM):
            # pylint: disable=no-member
            self.temporary_watch = \
                self.wm.add_watch(FROM_DIR, pyinotify.IN_CREATE, rec=False)
        else:
            self.setup_watcher()

        for feature in [COPY_FEATURE, PASTE_FEATURE]:
            self.dispatcher.add_handler(f'domain-feature-set:{feature}',
                                        self.setup_ui)
            self.dispatcher.add_handler(f'domain-feature-delete:{feature}',
                                        self.setup_ui)

    def setup_watcher(self):
        if self.temporary_watch:
            for wd in self.temporary_watch.values():
                self.wm.rm_watch(wd)
        mask = pyinotify.ALL_EVENTS
        self.wm.add_watch(FROM, mask)

    def show_menu(self, _unused, event):
        self.menu.show_all()
        self.menu.popup(None,  # parent_menu_shell
                        None,  # parent_menu_item
                        None,  # func
                        None,  # data
                        event.button,  # button
                        Gtk.get_current_event_time())  # activate_time

    def update_clipboard_contents(self, vm=None, size=0, message=None):
        if not vm or not size:
            self.clipboard_label.set_markup(_(
                "<i>Global clipboard is empty</i>"))
            self.icon.set_from_icon_name("edit-copy")
            # todo the icon should be empty and full depending on state

        else:
            self.clipboard_label.set_markup(
                _("<i>Global clipboard contents: {0} from "
                  "<b>{1}</b></i>").format(size, vm))
            self.icon.set_from_icon_name("edit-copy")

        if message:
            self.send_notify(message)

    def setup_ui(self, *_args, **_kwargs):
        self.copy_shortcut = self._prettify_shortcut(self.vm.features.get(
            COPY_FEATURE, 'Ctrl-Shift-C'))
        self.paste_shortcut = self._prettify_shortcut(self.vm.features.get(
            PASTE_FEATURE, 'Ctrl-Shift-V'))

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
            _("<i>Use <b>{copy}</b> to copy and "
              "<b>{paste}</b> to paste.</i>").format(
                copy=self.copy_shortcut, paste=self.paste_shortcut))
        help_item = Gtk.MenuItem()
        help_item.set_margin_left(10)
        help_item.set_sensitive(False)
        help_item.add(help_label)
        self.menu.append(help_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        dom0_item = Gtk.MenuItem(_("Copy dom0 clipboard"))
        dom0_item.connect('activate', self.copy_dom0_clipboard)
        self.menu.append(dom0_item)

        clear_item = Gtk.MenuItem(_("Clear global clipboard"))
        clear_item.connect('activate', self.clear_clipboard)
        self.menu.append(clear_item)

    def copy_dom0_clipboard(self, *_args, **_kwargs):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()

        if not text:
            self.send_notify(_("Dom0 clipboard is empty!"))
            return

        try:
            with appviewer_lock():
                with open(DATA, "w", encoding='utf-8') as contents:
                    contents.write(text)
                with open(FROM, "w", encoding='ascii') as source:
                    source.write("dom0")
                with open(XEVENT, "w", encoding='ascii') as timestamp:
                    timestamp.write(str(Gtk.get_current_event_time()))
        except Exception:  # pylint: disable=broad-except
            self.send_notify(_("Error while accessing global clipboard!"))

    def send_notify(self, body):
        # pylint: disable=attribute-defined-outside-init
        notification = Gio.Notification.new(_("Global Clipboard"))
        notification.set_body(body)
        notification.set_priority(Gio.NotificationPriority.NORMAL)
        self.send_notification(self.get_application_id(), notification)

    def _prettify_shortcut(self, shortcut: str):
        """Turn a keyboard shortcut into a nicer, more readable version,
        e.g. convert 'Ctrl-Mod4-c' into 'Ctrl-Win-C'"""
        parts = shortcut.split('-')
        return "+".join([self._convert_to_readable(part) for part in parts])

    @staticmethod
    def _convert_to_readable(key: str):
        if key == 'Mod4':
            return 'Win'
        if key == 'Ins':
            return "Insert"
        if len(key) == 1:
            return key.upper()
        return key

    def clear_clipboard(self, *_args, **_kwargs):
        try:
            with appviewer_lock():
                if os.path.exists(DATA):
                    os.unlink(DATA)
                if os.path.exists(FROM):
                    os.unlink(FROM)
                if os.path.exists(XEVENT):
                    os.unlink(XEVENT)
                self.update_clipboard_contents(vm=None, size=0, message= \
                        _("Global clipboard cleared"))
        except Exception:  # pylint: disable=broad-except
            self.send_notify(_("Error while clearing global clipboard!"))

    def clear_clipboard_event(self, modification_time: float) -> bool:
        """ this event is called via GLib if source VM and/or GUIVM has
        `global-clipboard-timeout=<SECONDS>` feature set and it times out """
        if self.clear_event_source_id:
            # first we remove the event from event loop
            GLib.source_remove(self.clear_event_source_id)
            self.clear_event_source_id = None
        if os.path.getmtime(DATA) != modification_time:
            # some other clipboard copy action has happened in the meantime
            return False
        self.clear_clipboard()
        return False

def main():
    loop = asyncio.get_event_loop()
    wm = pyinotify.WatchManager()

    qubes_app = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qubes_app)

    gtk_app = NotificationApp(wm, qubes_app, dispatcher)

    handler = EventHandler(loop=loop, gtk_app=gtk_app)
    pyinotify.AsyncioNotifier(wm, loop, default_proc_fun=handler)

    return run_asyncio_and_show_errors(loop, [asyncio.ensure_future(
        dispatcher.listen_for_events())], _("Qubes Clipboard Widget"))


if __name__ == '__main__':
    main()
