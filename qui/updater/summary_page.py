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
import asyncio
import threading
import time
from enum import Enum
from gettext import ngettext

import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk  # isort:skip
from typing import Optional, Any

import qubesadmin
from qubesadmin.events.utils import wait_for_domain_shutdown

from qubes_config.widgets.gtk_utils import (
    load_icon,
    show_dialog,
    show_dialog_with_icon,
    show_error,
    RESPONSES_OK,
)
from qubes_config.widgets.utils import get_boolean_feature
from qui.updater.utils import (
    disable_checkboxes,
    pass_through_event_window,
    HeaderCheckbox,
    QubeClass,
    QubeName,
    RowWrapper,
    ListWrapper,
    on_head_checkbox_toggled,
)

from locale import gettext as l


class SummaryPage:
    """
    Last content page of updater.

    Show the summary of vm updates and appms that should be restarted.
    """

    def __init__(
        self, builder, log, next_button, cancel_button, back_by_row_selection
    ):
        self.builder = builder
        self.log = log
        self.next_button = next_button
        self.cancel_button = cancel_button
        self.restart_thread = None
        self.disable_checkboxes = False
        self.status = RestartStatus.NONE
        self.err = ""

        self.updated_tmpls: Optional[list] = None

        self.restart_list: Gtk.TreeView = self.builder.get_object(
            "restart_list"
        )
        self.list_store: Optional[ListWrapper] = None

        self.stack: Gtk.Stack = self.builder.get_object("main_stack")
        self.page: Gtk.Box = self.builder.get_object("restart_page")
        self.label_summary: Gtk.Label = self.builder.get_object("label_summary")

        self.restart_list.connect("row-activated", self.on_checkbox_toggled)
        self.app_vm_list: Gtk.ListStore = self.builder.get_object(
            "restart_list_store"
        )
        restart_checkbox_column: Gtk.TreeViewColumn = self.builder.get_object(
            "restart_checkbox_column"
        )
        restart_checkbox_column.connect("clicked", self.on_header_toggled)
        restart_header_button: Gtk.Button = restart_checkbox_column.get_button()
        restart_header_button.connect("realize", pass_through_event_window)
        self.restart_header: Gtk.Label = self.builder.get_object(
            "restart_header"
        )
        self.restart_scrolled_window: Gtk.ScrolledWindow = (
            self.builder.get_object("restart_scrolled_window")
        )

        self.head_checkbox_button: Gtk.CheckButton = self.builder.get_object(
            "restart_checkbox_header"
        )
        self.head_checkbox_button.set_inconsistent(True)
        self.head_checkbox_button.connect("toggled", self.on_header_toggled)
        self.head_checkbox = RestartHeaderCheckbox(
            self.head_checkbox_button, self.next_button
        )

        self.summary_list: Gtk.TreeView = self.builder.get_object(
            "summary_list"
        )
        self.summary_list.connect("row-activated", back_by_row_selection)

    @disable_checkboxes
    def on_checkbox_toggled(self, _emitter, path, *_args):
        """Handles (un)selection of single row."""
        if path is None:
            return

        self.list_store.invert_selection(path)
        self.refresh_buttons()

    def refresh_buttons(self):
        """Refresh additional info column and finish button info."""
        for row in self.list_store:
            row.refresh_additional_info()
        selected_num = sum(row.selected for row in self.list_store)
        if selected_num == 0:
            self.head_checkbox.state = HeaderCheckbox.NONE
        elif selected_num == len(self.list_store):
            self.head_checkbox.state = HeaderCheckbox.ALL
        else:
            self.head_checkbox.state = HeaderCheckbox.SELECTED
        self.head_checkbox.set_buttons(selected_num)

    @disable_checkboxes
    def on_header_toggled(self, _emitter):
        """Handles clicking on header checkbox.

        Cycle between selection from appvms which templates was updated:
         <1> only servicevms
         <2> servicevms + other appvms but without excluded in settings
         <3> all appvms
         <4> no vm. (nothing)

        If the user has selected any vms that do not match the defined states,
        the cycle will start from (1).
        """
        on_head_checkbox_toggled(
            self.list_store, self.head_checkbox, self.select_rows
        )

    @property
    def is_populated(self) -> bool:
        """Returns True if restart list is populated."""
        return self.list_store is not None

    @property
    def is_visible(self):
        """Returns True if page is shown by stack."""
        return self.stack.get_visible_child() == self.page

    @disable_checkboxes
    def show(
        self,
        qube_updated_num: int,
        qube_no_updates_num: int,
        qube_failed_num: int,
    ):
        """Show this page and handle buttons."""
        self.log.debug("Show summary page")
        self.stack.set_visible_child(self.page)
        summary_1 = ngettext(
            "%(num)d qube updated successfully.",
            "%(num)d qubes updated successfully.",
            qube_updated_num,
        ) % {"num": qube_updated_num}
        summary_2 = ngettext(
            "%(num)d qube attempted to update but found no updates.",
            "%(num)d qubes attempted to update but found no updates.",
            qube_no_updates_num,
        ) % {"num": qube_no_updates_num}
        summary_3 = ngettext(
            "%(num)d qube failed to update.",
            "%(num)d qubes failed to update.",
            qube_failed_num,
        ) % {"num": qube_failed_num}
        summary = "\n".join((summary_1, summary_2, summary_3))
        self.label_summary.set_label(summary)
        self.cancel_button.set_label(l("_Back"))
        self.cancel_button.show()
        self.refresh_buttons()
        if len(self.list_store) == 0:
            self.restart_scrolled_window.set_visible(False)
            self.restart_header.set_text(l("No qubes need to be restarted."))

    @disable_checkboxes
    def populate_restart_list(self, restart, vm_updated, settings):
        """
        Adds to list any appvms/dispvm which template was successfully updated.

        DispVM with auto_cleanup are skipped.
        """
        self.log.debug("populate restart list")
        self.summary_list.set_model(vm_updated.list_store_raw)
        self.updated_tmpls = [
            row
            for row in vm_updated
            if bool(row.status)
            and QubeClass[row.vm.klass] == QubeClass.TemplateVM
        ]
        possibly_changed_vms = set()
        for template in self.updated_tmpls:
            possibly_changed_vms.update(template.vm.derived_vms)

        self.list_store = ListWrapper(
            RestartRowWrapper, self.restart_list.get_model()
        )

        for vm in possibly_changed_vms:
            if vm.is_running() and (
                vm.klass != "DispVM" or not vm.auto_cleanup
            ):
                self.list_store.append_vm(vm)

        if settings.restart_service_vms:
            self.head_checkbox.allow_service_vms()
        if settings.restart_other_vms:
            self.head_checkbox.allow_non_service_vms()
        if not restart:
            self.head_checkbox.state = HeaderCheckbox.NONE
        else:
            if settings.restart_service_vms:
                self.head_checkbox.state = HeaderCheckbox.SAFE
            if settings.restart_other_vms:
                self.head_checkbox.state = HeaderCheckbox.EXTENDED
        self.select_rows()

    def select_rows(self):
        for row in self.list_store:
            row.selected = (
                row.is_service_qube
                and not row.is_excluded
                and AppVMType.SERVICEVM in self.head_checkbox.allowed
                or not row.is_service_qube
                and not row.is_excluded
                and AppVMType.NON_SERVICEVM in self.head_checkbox.allowed
                or AppVMType.EXCLUDED in self.head_checkbox.allowed
            )

    def restart_selected_vms(self, show_only_error: bool):
        self.log.debug("Start restarting")
        self.restart_thread = threading.Thread(target=self.perform_restart)

        self.restart_thread.start()

        spinner = None
        dialog = None
        # wait a little to check if waiting dialog is needed at all
        time.sleep(0.01)

        if self.restart_thread.is_alive():
            # show waiting dialog
            spinner = Gtk.Spinner()
            spinner.start()
            dialog = show_dialog(
                None,
                l("Applying updates to qubes"),
                l("Waiting for qubes to be restarted/shutdown."),
                {},
                spinner,
            )
            dialog.set_deletable(False)
            dialog.show()
            self.log.debug("Show restart dialog")

        # wait for thread and spin spinner
        while self.restart_thread.is_alive():
            while Gtk.events_pending():
                Gtk.main_iteration()
            time.sleep(0.1)

        # cleanup
        if dialog:
            spinner.stop()
            dialog.destroy()
            self.log.debug("Hide restart dialog")
        self._show_status_dialog(show_only_error)

    def perform_restart(self):

        tmpls_to_shutdown = [
            row.vm for row in self.updated_tmpls if row.vm.is_running()
        ]
        to_restart = [
            qube_row.vm
            for qube_row in self.list_store
            if qube_row.selected and qube_row.is_service_qube
        ]
        to_shutdown = [
            qube_row.vm
            for qube_row in self.list_store
            if qube_row.selected and not qube_row.is_service_qube
        ]

        if not any([tmpls_to_shutdown, to_restart, to_shutdown]):
            self.status = RestartStatus.NOTHING_TO_DO
            return

        # clear err and perform shutdown/start
        self.err = ""
        self.shutdown_domains(tmpls_to_shutdown)
        self.restart_vms(to_restart)
        self.shutdown_domains(to_shutdown)

        if self.status is RestartStatus.NONE:
            self.status = RestartStatus.OK

    def shutdown_domains(self, to_shutdown):
        """
        Try to shut down vms and wait to finish.
        """
        wait_for = []
        for vm in to_shutdown:
            try:
                vm.shutdown(force=True)
                wait_for.append(vm)
                self.log.info("Shutdown %s", vm.name)
            except qubesadmin.exc.QubesVMError as err:
                self.err += vm.name + " cannot shutdown: " + str(err) + "\n"
                self.log.error(
                    "Cannot shutdown %s because %s", vm.name, str(err)
                )
                self.status = RestartStatus.ERROR_TMPL_DOWN

        asyncio.run(wait_for_domain_shutdown(wait_for))

        return wait_for

    def restart_vms(self, to_restart):
        """
        Try to restart vms.
        """
        shutdowns = self.shutdown_domains(to_restart)

        # restart shutdown qubes
        for vm in shutdowns:
            try:
                vm.start()
                self.log.info("Restart %s", vm.name)
            except qubesadmin.exc.QubesVMError as err:
                self.err += vm.name + " cannot start: " + str(err) + "\n"
                self.log.error("Cannot start %s because %s", vm.name, str(err))
                self.status = RestartStatus.ERROR_APP_DOWN

    def _show_status_dialog(self, show_only_error: bool):
        if self.status == RestartStatus.OK and not show_only_error:
            show_dialog_with_icon(
                None,
                l("Success"),
                l("All qubes were restarted/shutdown successfully."),
                buttons=RESPONSES_OK,
                icon_name="qubes-check-yes",
            )
        elif self.status.is_error():
            show_error(
                None,
                "Failure",
                l("During restarting following errors occurs: ") + self.err,
            )
            self.log.error("Restart error: %s", self.err)
            self.status = RestartStatus.ERROR_APP_START


class RestartRowWrapper(RowWrapper):
    COLUMN_NUM = 5
    _SELECTION = 1
    _ICON = 2
    _NAME = 3
    _ADDITIONAL_INFO = 4

    def __init__(self, list_store, vm, _selection: Any):
        raw_row = [
            False,
            load_icon(vm.icon),
            QubeName(vm.name, str(vm.label)),
            "",
        ]
        super().__init__(list_store, vm, raw_row)

    @property
    def selected(self):
        return self.raw_row[self._SELECTION]

    @selected.setter
    def selected(self, value):
        self.raw_row[self._SELECTION] = value
        self.refresh_additional_info()

    def refresh_additional_info(self):
        self.raw_row[RestartRowWrapper._ADDITIONAL_INFO] = ""
        if self.selected and not self.is_service_qube:
            self.raw_row[RestartRowWrapper._ADDITIONAL_INFO] = (
                "This qube and all running applications within will be shutdown"
            )
        if self.selected and self.is_excluded:
            self.raw_row[RestartRowWrapper._ADDITIONAL_INFO] = (
                '<span foreground="red">This qube has been explicitly '
                "disabled from restarting in settings</span>"
            )

    @property
    def icon(self):
        return self.raw_row[self._ICON]

    @property
    def name(self):
        return self.vm.name

    @property
    def color_name(self):
        return self.raw_row[self._NAME]

    @property
    def additional_info(self):
        return self.raw_row[self._ADDITIONAL_INFO]

    @property
    def is_service_qube(self):
        return get_boolean_feature(self.vm, "servicevm", False)

    @property
    def is_excluded(self):
        return not get_boolean_feature(self.vm, "restart-after-update", True)


class AppVMType:
    SERVICEVM = 0
    NON_SERVICEVM = 1
    EXCLUDED = 2


class RestartStatus(Enum):
    OK = 0
    NOTHING_TO_DO = 100
    NONE = -1
    ERROR_TMPL_DOWN = 11
    ERROR_APP_DOWN = 12
    ERROR_APP_START = 13

    def is_error(self: "RestartStatus") -> bool:
        return self in [
            RestartStatus.ERROR_TMPL_DOWN,
            RestartStatus.ERROR_APP_DOWN,
            RestartStatus.ERROR_APP_START,
        ]


class RestartHeaderCheckbox(HeaderCheckbox):
    def __init__(self, checkbox_column_button, next_button):
        super().__init__(
            checkbox_column_button, [None, None, AppVMType.EXCLUDED]
        )
        self.next_button = next_button

    def allow_service_vms(self, value=True):
        if value:
            self._allowed[0] = AppVMType.SERVICEVM
        else:
            self._allowed[0] = None

    def allow_non_service_vms(self, value=True):
        if value:
            self._allowed[1] = AppVMType.NON_SERVICEVM
        else:
            self._allowed[1] = None

    # pylint: disable=arguments-differ
    def all_action(self, num, *args, **kwargs):
        text = ngettext(
            "_Finish and restart/shutdown %(num)d qube",
            "_Finish and restart/shutdown %(num)d qubes",
            num,
        ) % {"num": num}
        self.next_button.set_label(text)

    def inconsistent_action(self, *args, **kwargs):
        self.all_action(*args, **kwargs)

    def none_action(self, *args, **kwargs):
        self.next_button.set_label("_Finish")
