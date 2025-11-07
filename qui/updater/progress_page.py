# coding=utf-8
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023  Piotr Bartman <prbartman@invisiblethingslab.com>
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
import re
import signal
import subprocess
import threading
import time
import gi
from typing import Dict

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, Gdk, GLib, GObject  # isort:skip
from locale import gettext as l

from qubes_config.widgets.gtk_utils import (
    copy_to_global_clipboard,
    load_icon_at_gtk_size,
)
from qui.updater.updater_settings import Settings
from qui.updater.utils import UpdateStatus, RowWrapper


class ProgressPage:

    def __init__(
        self, builder, log, header_label, next_button, cancel_button, callback
    ):
        self.builder = builder
        self.log = log
        self.header_label = header_label
        self.next_button = next_button
        self.cancel_button = cancel_button
        self.vms_to_update = None
        self.exit_triggered = False
        self.update_thread = None
        self.after_update_callback = callback
        self.retcode = None

        self.update_details = QubeUpdateDetails(self.builder)

        self.stack: Gtk.Stack = self.builder.get_object("main_stack")
        self.page: Gtk.Box = self.builder.get_object("progress_page")
        self.progressbar: Gtk.TreeView = self.builder.get_object("progressbar")
        progress_store = self.progressbar.get_model()
        progress_store.append([0])
        self.total_progress = progress_store[-1]
        self.progressbar_renderer: Gtk.CellRendererProgress = self.builder.get_object(
            "progressbar_renderer"
        )
        self.progressbar_renderer.set_fixed_size(-1, 26)

        self.progress_list: Gtk.TreeView = self.builder.get_object("progress_list")
        self.selection: Gtk.TreeSelection = self.progress_list.get_selection()
        self.progress_list.connect("row-activated", self.row_selected)
        progress_column: Gtk.TreeViewColumn = self.builder.get_object("progress_column")
        renderer = CellRendererProgressWithResult()
        renderer.props.ypad = 10
        progress_column.pack_start(renderer, True)
        progress_column.add_attribute(renderer, "pulse", 7)
        progress_column.add_attribute(renderer, "value", 7)
        progress_column.add_attribute(renderer, "status", 8)

    @property
    def is_visible(self):
        """Returns True if page is shown by stack."""
        return self.stack.get_visible_child() == self.page

    def init_update(self, vms_to_update, settings):
        """Starts `perform_update` in new thread."""
        self.log.info("Prepare updating")
        self.vms_to_update = vms_to_update
        self.progress_list.set_model(vms_to_update.list_store_raw)
        self.next_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_label(l("_Cancel updates"))
        self.cancel_button.show()

        self.header_label.set_text(l("Update in progress..."))
        self.header_label.set_halign(Gtk.Align.CENTER)

        self.update_thread = threading.Thread(
            target=self.perform_update, args=(settings,)
        )
        self.update_thread.start()

    def interrupt_update(self):
        """
        Finish ongoing updates, but skip the ones that haven't started yet.
        """
        self.log.debug("Interrupting updates")
        self.exit_triggered = True
        GLib.idle_add(self.header_label.set_text, l("Interrupting the update..."))

    def perform_update(self, settings):
        """Uses qubes-vm-update to update dom0 and then other vms."""
        GLib.idle_add(self.set_total_progress, 0)

        if self.vms_to_update:
            self.update_selected(self.vms_to_update, settings)

        GLib.idle_add(self.header_label.set_text, l("Update finished"))
        GLib.idle_add(self.cancel_button.set_visible, False)
        GLib.idle_add(self.next_button.set_sensitive, True)
        self.after_update_callback()

    def update_selected(self, to_update, settings):
        """Updates templates and standalones and then sets update statuses."""
        if self.exit_triggered:
            self.log.info("Update canceled: skip templateVM updating")
            for row in to_update:
                GLib.idle_add(row.set_status, UpdateStatus.Cancelled)
                GLib.idle_add(
                    row.append_text_view,
                    l("Canceled update for {}\n").format(row.vm.name),
                )
                GLib.idle_add(self.set_total_progress, 100)
                self.update_details.update_buffer()
                return
        self.log.debug("Start templateVM updating")

        for row in to_update:
            GLib.idle_add(row.append_text_view, l("Updating {}\n").format(row.name))
            GLib.idle_add(row.set_status, UpdateStatus.InProgress)
        self.update_details.update_buffer()

        try:
            rows = {row.name: row for row in to_update}
            self.do_update_selected(rows, settings)
            GLib.idle_add(self.set_total_progress, 100)
        except subprocess.CalledProcessError as ex:
            for row in to_update:
                GLib.idle_add(
                    row.append_text_view,
                    l("Error on updating {}: {}\n{}").format(
                        row.name, str(ex), ex.output.decode()
                    ),
                )
                GLib.idle_add(row.set_status, UpdateStatus.Error)
        self.update_details.update_buffer()

    def do_update_selected(self, rows: Dict[str, RowWrapper], settings: Settings):
        """Runs `qubes-vm-update` command."""
        targets = ",".join((name for name in rows.keys()))

        args = []
        if settings.max_concurrency is not None:
            args.extend(("--max-concurrency", str(settings.max_concurrency)))

        # pylint: disable=consider-using-with
        proc = subprocess.Popen(
            [
                "sudo",
                "qubes-vm-update",
                "--show-output",
                "--just-print-progress",
                "--force-update",
                *args,
                "--targets",
                targets,
            ],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

        read_err_thread = threading.Thread(target=self.read_stderrs, args=(proc, rows))
        read_out_thread = threading.Thread(target=self.read_stdouts, args=(proc, rows))
        read_err_thread.start()
        read_out_thread.start()

        while (
            proc.poll() is None
            or read_out_thread.is_alive()
            or read_err_thread.is_alive()
        ):
            time.sleep(1)
            if self.exit_triggered and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                proc.wait()
                read_err_thread.join()
                read_out_thread.join()
        self.retcode = proc.returncode

    def read_stderrs(self, proc, rows):
        for untrusted_line in iter(proc.stderr.readline, ""):
            if untrusted_line:
                self.handle_err_line(untrusted_line, rows)
            else:
                break
        proc.stderr.close()

    def handle_err_line(self, untrusted_line, rows):
        line = self._sanitize_line(untrusted_line)
        try:
            name, status, info = line.split()
            if status == "updating":
                progress = int(float(info))
                GLib.idle_add(rows[name].set_update_progress, progress)
                total_progress = sum(
                    row.get_update_progress() for row in rows.values()
                ) / len(rows)
                GLib.idle_add(self.set_total_progress, total_progress)

        except ValueError:
            return

        try:
            if status == "done":
                update_status = UpdateStatus.from_name(info)
                GLib.idle_add(rows[name].set_update_progress, 100)
                GLib.idle_add(rows[name].set_status, update_status)
        except KeyError:
            return

    def read_stdouts(self, proc, rows):
        curr_name_out = ""
        for untrusted_line in iter(proc.stdout.readline, ""):
            if untrusted_line:
                line = self._sanitize_line(untrusted_line)
                try:
                    maybe_name, text = line.split(" ", 1)
                except ValueError:
                    continue
                suffix = len(":out:")
                if maybe_name[:-suffix] in rows.keys():
                    curr_name_out = maybe_name[:-suffix]
                if curr_name_out:
                    rows[curr_name_out].append_text_view(text)
                if (
                    self.update_details.active_row is not None
                    and curr_name_out == self.update_details.active_row.name
                ):
                    self.update_details.update_buffer()
            else:
                break
        self.update_details.update_buffer()
        proc.stdout.close()

    @staticmethod
    def _sanitize_line(untrusted_line: bytes) -> str:
        ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]")
        line = ansi_escape.sub("", untrusted_line.decode())
        return line

    def set_total_progress(self, progress):
        """Set the value of main big progressbar."""
        self.total_progress[0] = progress

    def back_by_row_selection(self, _emitter, path, *args):
        """Show this page and select row selected on summary page."""
        self.show()
        self.row_selected(_emitter, path, *args)

    def show(self):
        """Show this page and handle buttons."""
        self.log.debug("Show progress page")
        self.selection.unselect_all()
        self.update_details.set_active_row(None)
        self.stack.set_visible_child(self.page)

        self.next_button.set_label(l("_Next"))
        self.cancel_button.hide()

    def row_selected(self, _emitter, path, _col):
        """Handle clicking on a row to show more info.

        Set updated details (name of vm and textview)."""
        self.selection.unselect_all()
        self.selection.select_path(path)
        self.update_details.set_active_row(self.vms_to_update[path.get_indices()[0]])

    def get_update_summary(self):
        """Returns update summary.

        It is a triple of:
        1. number of updated vms,
        2. number of vms that tried to update but no update was found,
        3. vms that update was canceled before starting.
        """
        updated = len(
            [row for row in self.vms_to_update if row.status == UpdateStatus.Success]
        )
        no_updates = len(
            [
                row
                for row in self.vms_to_update
                if row.status == UpdateStatus.NoUpdatesFound
            ]
        )
        failed = len(
            [row for row in self.vms_to_update if row.status == UpdateStatus.Error]
        )
        cancelled = len(
            [row for row in self.vms_to_update if row.status == UpdateStatus.Cancelled]
        )
        return updated, no_updates, failed, cancelled


class QubeUpdateDetails:

    def __init__(self, builder):
        self.active_row = None
        self.builder = builder

        self.qube_details: Gtk.Box = self.builder.get_object("qube_details")
        self.details_label: Gtk.Label = self.builder.get_object("details_label")
        self.qube_icon: Gtk.Image = self.builder.get_object("qube_icon")
        self.qube_label: Gtk.Label = self.builder.get_object("qube_label")
        self.colon: Gtk.Label = self.builder.get_object("colon")

        self.copy_button: Gtk.Button = self.builder.get_object("copy_button")
        self.copy_button.connect("clicked", self.copy_content)

        self.progress_textview: Gtk.TextView = self.builder.get_object(
            "progress_textview"
        )
        self.progress_scrolled_window: Gtk.ScrolledWindow = self.builder.get_object(
            "progress_scrolled_window"
        )

    def copy_content(self, _emitter):
        if self.active_row is None:
            return

        text = self.active_row.buffer
        if not text:
            return

        copy_to_global_clipboard(text)

    def set_active_row(self, row):
        self.active_row = row
        row_activated = self.active_row is not None
        if not row_activated:
            self.details_label.set_text(l("Select a qube to see details."))
        else:
            self.details_label.set_text(l("Details for") + "  ")
            self.qube_icon.set_from_pixbuf(self.active_row.icon)
            self.qube_label.set_markup(" " + str(self.active_row.color_name))
        self.update_buffer()

        self.qube_icon.set_visible(row_activated)
        self.qube_label.set_visible(row_activated)
        self.colon.set_visible(row_activated)
        self.progress_scrolled_window.set_visible(row_activated)
        self.progress_textview.set_visible(row_activated)
        self.copy_button.set_visible(row_activated)

    def update_buffer(self):
        if self.active_row is not None:
            buffer_ = self.progress_textview.get_buffer()
            GLib.idle_add(buffer_.set_text, self.active_row.buffer)
            GLib.idle_add(self._autoscroll)

    def _autoscroll(self):
        adjustment = self.progress_scrolled_window.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())


class CellRendererProgressWithResult(Gtk.CellRendererProgress):
    """
    Custom Cell Renderer to show progressbar or finish icon.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status = None

    @GObject.Property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    # pylint: disable=arguments-differ
    def do_render(self, context, widget, background_area, cell_area, flags):
        status: UpdateStatus = self.get_property("status")
        if status == UpdateStatus.Success:
            self.draw_icon("qubes-check-yes", context, cell_area)
        elif status == UpdateStatus.NoUpdatesFound:
            self.draw_icon("qubes-check-maybe", context, cell_area)
        elif status in (UpdateStatus.Error, UpdateStatus.Cancelled):
            self.draw_icon("check_no", context, cell_area)
        elif status == UpdateStatus.ProgressUnknown:
            Gtk.CellRendererProgress.do_render(
                self, context, widget, background_area, cell_area, flags
            )
        else:
            self.set_property("pulse", -1)
            Gtk.CellRendererProgress.do_render(
                self, context, widget, background_area, cell_area, flags
            )

    def draw_icon(self, icon_name: str, context, cell_area):
        # pylint: disable=no-member
        pixbuf = load_icon_at_gtk_size(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
        Gdk.cairo_set_source_pixbuf(
            context,
            pixbuf,
            cell_area.x + self.props.xpad,
            cell_area.y + self.props.ypad,
        )
        context.paint()
