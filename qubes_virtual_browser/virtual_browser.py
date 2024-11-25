#!/usr/bin/env python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2024 Ali Mirjamali <ali@mirjamali.com>
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
# pylint: disable=import-error,invalid-name,wrong-import-position

""" Qubes Virtual Browser: A simple program which allows user to handle URLs """

import argparse
import importlib.resources
import os
import subprocess
import sys
from urllib.parse import urlparse

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio
from gi.repository.GdkPixbuf import Pixbuf

import qubesadmin

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

DATA = "/var/run/qubes/qubes-clipboard.bin"
METADATA = "/var/run/qubes/qubes-clipboard.bin.metadata"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"
XEVENT = "/var/run/qubes/qubes-clipboard.bin.xevent"

class QubesVirtualBrowser(Gtk.Application):
    """ Simple dialog to show URL and available actions. Also responsible for
    saving the default action """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, qapp, url):
        super().__init__(
            application_id="org.qubes-os.virtual-browser",
            flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.qapp = qapp
        self.action: str = 'discard'
        self.builder = Gtk.Builder()
        glade_ref = (importlib.resources.files('qubes_virtual_browser') /
                     'virtual_browser.glade')
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.main_dialog: Gtk.Dialog = \
                self.builder.get_object("qubes_virtual_browser")
        self.main_dialog.connect("delete-event", Gtk.main_quit)
        self.url: Gtk.Label = \
                self.builder.get_object("url")
        self.url.set_text(url)
        self.disp_templates: Gtk.ComboBox = \
                self.builder.get_object("disp_templates")
        self.save_default: Gtk.CheckBox = \
                self.builder.get_object("save_default")
        self.button_disposable: Gtk.Button = \
                self.builder.get_object("button_disposable")
        self.button_disposable.connect('clicked', self.take_action)
        self.button_clipboard: Gtk.Button = \
                self.builder.get_object("button_clipboard")
        self.button_clipboard.connect('clicked', self.take_action)
        self.button_discard: Gtk.Button = \
                self.builder.get_object("button_discard")
        self.button_discard.connect('clicked', self.take_action)

        self.disposables = Gtk.ListStore(object, Pixbuf, str)
        self.disp_templates.set_model(self.disposables)
        self.renderer_icon = Gtk.CellRendererPixbuf()
        self.renderer_vmname = Gtk.CellRendererText()
        self.disp_templates.pack_start(self.renderer_icon, True)
        self.disp_templates.pack_start(self.renderer_vmname, True)
        self.disp_templates.add_attribute(self.renderer_icon, "pixbuf", 1)
        self.disp_templates.add_attribute(self.renderer_vmname, "text", 2)

    def do_activate(self, *_args, **_kwargs):
        """ Populate DispVM list. Show dialog """
        default_dispvm = getattr(self.qapp, "default_dispvm", None)
        for domain in self.qapp.domains:
            if getattr(domain, "template_for_dispvms", False):
                # pylint: disable=no-member
                icon = Gtk.IconTheme.get_default().load_icon(
                    getattr(domain, "icon", "qubes-manager"), 32, 0)
                row = self.disposables.append([domain, icon, domain.name])
                if domain.name == default_dispvm:
                    self.disposables[row][2] += " (Default DispVM Template)"
                    self.disp_templates.set_active(len(self.disposables) - 1)
        if len(self.disposables) == 0:
            # pylint: disable=fixme
            # TODO: Decide what to do if there is no DispVM Template
            pass
        self.main_dialog.show_all()
        Gtk.main()

    def take_action(self, button) -> None:
        """ Return user action to main function. Save default if selected """
        match button:
            case self.button_disposable:
                row = self.disp_templates.get_active_iter()
                self.action = "disposable:" + self.disposables[row][0].name
            case self.button_clipboard:
                self.action = "clipboard"
            case self.button_discard:
                self.action = "discard"
        if self.save_default.get_active():
            self.qapp.domains[self.qapp.local_name].features[ \
                "virtual-browser-action"] = self.action
        self.main_dialog.hide()
        while Gtk.events_pending():
            Gtk.main_iteration()
        Gtk.main_quit()

def _open_url_in_dvm(url, dvm: qubesadmin.vm.QubesVM):
    print(url, dvm)
    subprocess.run(
        ['qvm-run', '-p', '--service', f'--dispvm={dvm}',
         'qubes.OpenURL'], input=url.encode(), check=False,
        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

def _copy_to_global_clipboard(url, vmname):
    with open(DATA, "w", encoding='utf-8') as contents:
        contents.write(url)
    with open(FROM, "w", encoding='ascii') as source:
        source.write(vmname)
    with open(XEVENT, "w", encoding='ascii') as timestamp:
        timestamp.write(str(Gtk.get_current_event_time()))
    with open(METADATA, "w", encoding='ascii') as metadata:
        metadata.write(
            '{{\n'   \
            f'"vmname":"{vmname}",\n'   \
            '"xevent_timestamp":0,\n'   \
            '"successful":1,\n'   \
            '"copy_action":1,\n'   \
            '"paste_action":0,\n'   \
            '"malformed_request":0,\n'   \
            '"cleared":0,\n'   \
            '"qrexec_clipboard":0,\n'   \
            f'"sent_size":{os.path.getsize(DATA)},\n'   \
            '"buffer_size":2048,\n'   \
            '"protocol_version_xside":65544,\n'   \
            '"protocol_version_vmside":65544,\n'   \
            '}}\n')

def URL(url: str) -> str:
    """ URL validation helper function for argument parser """
    if len(url) > 2048:
        raise ValueError
    result = urlparse(url)
    if not result.scheme.lower() in ['http', 'https']:
        # pylint: disable=fixme
        # TODO: Fix qubes.OpenURL bug of rejecting uppercase URL schemes
        raise ValueError
    if result.netloc == '':
        raise ValueError
    return url

def main():
    """ Main function and argument parser """
    parser = argparse.ArgumentParser(
        description='Qubes OS Virtual Browser',
        epilog='Defaults could be changed in Qubes Global Config')
    parser.add_argument('URL', type=URL,
        help='Valid HTTP or HTTPS URL')
    parser.add_argument('--ask', action='store_true',
        help='Ask for action even if "virtual-browser-action" feature is set.')
    args = parser.parse_args()
    qapp = qubesadmin.Qubes()
    action = qapp.domains[qapp.local_name].features.get( \
        "virtual-browser-action", "")
    if args.ask or not action in ['clipboard', 'discard'] and not \
            (action.startswith('disposable:') and action[11:] in qapp.domains):
        app = QubesVirtualBrowser(qapp, args.URL)
        app.run()
        action = app.action
    if action.startswith('disposable:'):
        _open_url_in_dvm(args.URL, action[11:])
    elif action == 'clipboard':
        _copy_to_global_clipboard(args.URL, qapp.local_name)
    sys.exit()

if __name__ == "__main__":
    main()
