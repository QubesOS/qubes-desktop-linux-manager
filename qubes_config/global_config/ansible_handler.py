# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2026 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
"""
Use AnsibleHandler to execute ansible playbooks, and show progress.
"""
import re
import threading
from typing import Callable

import ansible_runner
import gi

from ..widgets.gtk_utils import (
    ask_question,
    load_icon,
)

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

# regular expression to remove colors from console output
ANSI_ESCAPE = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")

# TODO:
# - list of qubes to install ctap in seems too long


class AnsibleProgressDialog(Gtk.Dialog):
    """
    Main progress dialog for executing an ansible playbook.
    """

    def __init__(self, parent: Gtk.Window):
        """
        :param parent: parent Gtk object; needed to make this modal.
        """
        super().__init__(
            title="Operation in progress", modal=True, destroy_with_parent=True
        )
        self.set_transient_for(parent)
        self.set_default_size(600, 120)
        self.set_deletable(False)
        self.set_resizable(True)

        content = self.get_content_area()
        content.get_style_context().add_class("modal_dialog")

        # current status line
        self.status_label = Gtk.Label(label="Starting...")
        self.status_label.set_halign(Gtk.Align.START)
        content.pack_start(self.status_label, False, False, 20)

        # progress bar
        self.progress = Gtk.ProgressBar()
        self.progress.set_pulse_step(0.1)
        self.progress.get_style_context().add_class("loading")
        self.progress.set_margin_start(25)
        self.progress.set_margin_end(25)
        content.pack_start(self.progress, False, False, 5)

        # collapsible log
        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer)
        log_view.set_editable(False)
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        log_view.set_monospace(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_margin_top(10)
        scroll.set_vexpand(True)
        scroll.set_size_request(-1, 250)
        scroll.add(log_view)

        expander = Gtk.Expander(label="Details")
        expander.add(scroll)
        expander.connect("notify::expanded", self._on_expander_toggled)
        content.pack_end(expander, False, False, 10)

        self.show_all()
        self._pulse_source = GLib.timeout_add(150, self._pulse_progress)

    def _on_expander_toggled(self, expander: Gtk.Expander, _):
        # resize the dialog when the expander is toggled
        if expander.get_expanded():
            self.set_default_size(600, 400)
            self.resize(600, 400)
        else:
            self.set_default_size(600, 120)
            self.resize(600, 120)

    def _pulse_progress(self):
        self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def set_status(self, text: str):
        self.status_label.set_text(text)

    def append_log(self, text: str):
        self.log_buffer.insert(self.log_buffer.get_end_iter(), text + "\n")
        self.log_buffer.place_cursor(self.log_buffer.get_end_iter())

    def finish(self, success: bool):
        """
        Run after playbook is done.
        :param success: was execution successful?
        :return:
        """
        GLib.source_remove(self._pulse_source)

        # remove progress bar and status label
        self.progress.destroy()
        self.status_label.destroy()

        # big result icon + label
        result_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        result_box.set_halign(Gtk.Align.CENTER)

        icon_name = "check_yes" if success else "check_no"
        image = Gtk.Image()
        image.set_from_pixbuf(load_icon(icon_name, 32, 32))
        result_box.pack_start(image, False, False, 20)

        label_text = "Success" if success else "Error"
        self.set_title(label_text)
        label = Gtk.Label()
        label.set_markup(f"<big><b>{label_text}</b></big>")
        result_box.pack_start(label, False, False, 20)

        self.get_content_area().pack_start(result_box, False, False, 0)

        # close button in action area
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda d, r: d.destroy())
        self.set_deletable(True)

        self.get_content_area().show_all()
        self.get_action_area().show_all()


class AnsibleHandler:
    """
    This class handles all operations related to Ansible execution.
    """

    def __init__(
        self,
        playbook_file: str,
        operation_name: str,
        parent_window: Gtk.Window,
        finalize_callback: Callable | None = None,
    ):
        """

        :param playbook_file: path to the playbook file
        :param operation_name: name of the operation to be performed; used in window
        titles
        :param parent_window: Gtk.Window that should be the parent of modal dialogues displayed by this class
        :param finalize_callback: function to call when the playbook is done and the
        window is closed TODO: DOES THIS WORK
        """
        self.playbook_file = playbook_file
        self.operation_name = operation_name
        self.parent_window = parent_window
        self.params = {}
        self.progress_dialog = None
        self.runner = None
        self.finalize_callback = finalize_callback

    def _handle_playbook_events(self, data):
        """Update log, update status bar"""
        stdout_data = data.get("stdout", "")
        if stdout_data:
            stdout_data = ANSI_ESCAPE.sub("", stdout_data)  # strip color codes
            GLib.idle_add(self.progress_dialog.append_log, stdout_data)

        event_type = data.get("event", "")
        event_data = data.get("event_data", {})

        match event_type:
            case "playbook_on_play_start":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Play: {event_data.get('play', '')}",
                )
            case "playbook_on_task_start":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Task: {event_data.get('task', '')}",
                )
            case "runner_on_failed":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Failed: {event_data.get('task', '')}",
                )
            case "runner_on_unreachable":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Unreachable: {event_data.get('host', '')}",
                )
            case "runner_on_ok":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Task complete:" f" {event_data.get('host', '')}",
                )
            case "runner_on_skipped":
                GLib.idle_add(
                    self.progress_dialog.set_status,
                    f"Task skipped:" f" {event_data.get('host', '')}",
                )

    def _on_playbook_finished(self):
        self.progress_dialog.finish(self.runner.rc == 0)
        if self.finalize_callback:
            GLib.idle_add(self.finalize_callback)

    def _run_playbook(self):
        self.runner = ansible_runner.run(
            playbook=self.playbook_file,
            extravars=self.params,
            event_handler=self._handle_playbook_events,
            quiet=True,
        )

        GLib.idle_add(self._on_playbook_finished)

    def run_playbook_for(self, params: dict, description: str):
        """
        Run the playbook for listed qubes.
        :param params: parameters to be passed through to the playbook
        :param description: description of the action, used in asking the user "Are you sure???"
        :return:
        """
        self.params = params

        # step 1: ask for confirmation
        response = ask_question(
            self.parent_window,
            self.operation_name,
            description,
        )
        if response != Gtk.ResponseType.YES:
            return

        # the signal is go:
        self.progress_dialog = AnsibleProgressDialog(self.parent_window)

        thread = threading.Thread(target=self._run_playbook, daemon=True)
        thread.start()
