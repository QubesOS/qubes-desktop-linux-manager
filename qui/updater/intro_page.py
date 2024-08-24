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
import subprocess
from enum import Enum

import gi

from datetime import datetime, timedelta
from typing import Optional

gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk  # isort:skip

from qubes_config.widgets.gtk_utils import load_icon
from qubesadmin import exc

from qui.utils import check_support
from qui.updater.utils import disable_checkboxes, HeaderCheckbox, \
    pass_through_event_window, \
    QubeName, label_color_theme, UpdateStatus, RowWrapper, \
    ListWrapper, on_head_checkbox_toggled


class IntroPage:
    """
    First content page of updater.

    Show the list of updatable vms with update info.
    """

    def __init__(self, builder, log, next_button):
        self.builder = builder
        self.log = log
        self.next_button = next_button
        self.disable_checkboxes = False
        self.active = True

        self.page: Gtk.Box = self.builder.get_object("list_page")
        self.stack: Gtk.Stack = self.builder.get_object("main_stack")
        self.vm_list: Gtk.TreeView = self.builder.get_object("vm_list")
        self.list_store: Optional[ListWrapper] = None

        checkbox_column: Gtk.TreeViewColumn = self.builder.get_object(
            "checkbox_column")
        checkbox_column.connect("clicked", self.on_header_toggled)
        header_button = checkbox_column.get_button()

        header_button.connect('realize', pass_through_event_window)

        self.checkbox_column_button: Gtk.CheckButton = self.builder.get_object(
            "checkbox_header")
        self.checkbox_column_button.set_inconsistent(True)
        self.checkbox_column_button.connect("toggled", self.on_header_toggled)
        self.head_checkbox = UpdateHeaderCheckbox(
            self.checkbox_column_button, self.next_button
        )

        self.vm_list.connect("row-activated", self.on_checkbox_toggled)

        self.info_how_it_works: Gtk.Label = self.builder.get_object(
            "info_how_it_works")
        self.info_how_it_works.set_label(
            self.info_how_it_works.get_label().format(
                MAYBE=f'<span foreground="{label_color_theme("orange")}">'
                      '<b>MAYBE</b></span>',
                OBSOLETE=f'<span foreground="{label_color_theme("red")}">'
                      '<b>OBSOLETE</b></span>'
            ))

    def populate_vm_list(self, qapp, settings):
        """Adds to list any updatable vms with update info."""
        self.log.debug("Populate update list")
        self.list_store = ListWrapper(
            UpdateRowWrapper, self.vm_list.get_model())

        for vm in qapp.domains:
            if vm.klass == 'AdminVM':
                try:
                    state = bool(vm.features.get('updates-available', False))
                except exc.QubesDaemonCommunicationError:
                    state = False
                self.list_store.append_vm(vm, state)

        for vm in qapp.domains:
            if getattr(vm, 'updateable', False) and vm.klass != 'AdminVM':
                self.list_store.append_vm(vm)

        self.refresh_update_list(settings.update_if_stale)

    def refresh_update_list(self, update_if_stale):
        """
        Refreshes "Updates Available" column if settings changed.
        """
        self.log.debug("Refreshing update list")
        if not self.active:
            return

        cmd = ['qubes-vm-update', '--quiet', '--dry-run',
               '--update-if-stale', str(update_if_stale)]

        to_update = self._get_stale_qubes(cmd)

        for row in self.list_store:
            if row.vm.name == 'dom0':
                continue
            row.updates_available = bool(row.vm.name in to_update)
            row.selected = bool(row.vm.name in to_update)

    def get_vms_to_update(self) -> ListWrapper:
        """Returns list of vms selected to be updated"""
        return self.list_store.get_selected()

    @property
    def is_populated(self) -> bool:
        """Returns True if updatable vms list is populated."""
        return self.list_store is not None

    @property
    def is_visible(self):
        """Returns True if page is shown by stack."""
        return self.stack.get_visible_child() == self.page

    @disable_checkboxes
    def on_checkbox_toggled(self, _emitter, path, *_args):
        """Handles (un)selection of single row."""
        if path is None:
            return

        self.list_store.invert_selection(path)
        selected_num = sum(row.selected for row in self.list_store)
        if selected_num == len(self.list_store):
            self.head_checkbox.state = HeaderCheckbox.ALL
        elif selected_num == 0:
            self.head_checkbox.state = HeaderCheckbox.NONE
        else:
            self.head_checkbox.state = HeaderCheckbox.SELECTED
        self.head_checkbox.set_buttons()

    @disable_checkboxes
    def on_header_toggled(self, _emitter):
        """Handles clicking on header checkbox.

        Cycle between selection of:
         <1> vms with `updates_available` (YES)
         <2> <1> + vms no checked for updates for a while (YES and MAYBE)
         <3> all vms (YES, MAYBE and NO)
         <4> no vm. (nothing)

        If the user has selected any vms that do not match the defined states,
        the cycle will start from (1).
        """
        on_head_checkbox_toggled(
            self.list_store, self.head_checkbox, self.select_rows)

    def select_rows(self):
        for row in self.list_store:
            row.selected = row.updates_available \
                           in self.head_checkbox.allowed

    def select_rows_ignoring_conditions(self, cliargs, dom0):
        cmd = ['qubes-vm-update', '--dry-run', '--quiet']

        args = [a for a in dir(cliargs) if not a.startswith("_")]
        for arg in args:
            if arg in ("non_interactive", "non_default_select",
                       "dom0",
                       "restart", "apply_to_sys", "apply_to_all", "no_apply",
                       "max_concurrency", "log"):
                continue
            value = getattr(cliargs, arg)
            if value:
                if arg in ("skip", "targets"):
                    vms = set(value.split(","))
                    vms_without_dom0 = vms.difference({"dom0"})
                    if not vms_without_dom0:
                        continue
                    value = ",".join(sorted(vms_without_dom0))
                cmd.append(f"--{arg.replace('_', '-')}")
                if not isinstance(value, bool):
                    cmd.append(str(value))

        to_update = set()
        non_default_select = [
            '--' + arg for arg in cliargs.non_default_select if arg != 'dom0']
        non_default = [a for a in cmd if a in non_default_select]
        if non_default or cliargs.non_interactive:
            to_update = self._get_stale_qubes(cmd)

        to_update = self._handle_cli_dom0(dom0, to_update, cliargs)

        for row in self.list_store:
            row.selected = row.name in to_update

    def _get_stale_qubes(self, cmd):
        try:
            self.log.debug("Run command %s", " ".join(cmd))
            output = subprocess.check_output(cmd)
            self.log.debug("Command returns: %s", output.decode())

            output_lines = output.decode().split("\n")
            if ":" not in output_lines[0]:
                return set()

            return {
                vm_name.strip() for vm_name
                in output_lines[0].split(":", maxsplit=1)[1].split(",")
            }
        except subprocess.CalledProcessError as err:
            if err.returncode != 100:
                raise err
            return set()

    @staticmethod
    def _handle_cli_dom0(dom0, to_update, cliargs):
        default_select = not any(
            (getattr(cliargs, arg)
             for arg in cliargs.non_default_select if arg != 'all'))
        if ((
            default_select and cliargs.non_interactive
            or cliargs.all
            or cliargs.dom0
        ) and (
            cliargs.force_update
            or bool(dom0.features.get('updates-available', False))
            or is_stale(dom0, cliargs.update_if_stale)
        )):
            to_update.add('dom0')

        if cliargs.targets and "dom0" in cliargs.targets.split(","):
            to_update.add("dom0")
        if cliargs.skip and "dom0" in cliargs.skip.split(","):
            to_update = to_update.difference({"dom0"})
        return to_update


def is_stale(vm, expiration_period):
    if expiration_period is None:
        return False
    today = datetime.today()
    last_update_str = vm.features.get(
        'last-updates-check',
        datetime.fromtimestamp(0).strftime('%Y-%m-%d %H:%M:%S')
    )
    last_update = datetime.fromisoformat(last_update_str)
    if (today - last_update).days > expiration_period:
        return True
    return False


class UpdateRowWrapper(RowWrapper):
    COLUMN_NUM = 9
    _SELECTION = 1
    _ICON = 2
    _NAME = 3
    _UPDATES_AVAILABLE = 4
    _LAST_UPDATES_CHECK = 5
    _LAST_UPDATE = 6
    _UPDATE_PROGRESS = 7
    _STATUS = 8

    def __init__(self, list_store, vm, to_update: bool):
        updates_available = bool(vm.features.get('updates-available', False))
        if to_update and not updates_available:
            updates_available = None
        selected = updates_available is True
        supported = check_support(vm)

        last_updates_check = vm.features.get('last-updates-check', None)
        last_update = vm.features.get('last-update', None)

        icon = load_icon(vm.icon)
        name = QubeName(vm.name, str(vm.label))

        raw_row = [
            selected,
            icon,
            name,
            UpdatesAvailable.from_features(updates_available, supported),
            Date(last_updates_check),
            Date(last_update),
            0,
            UpdateStatus.Undefined,
        ]

        super().__init__(list_store, vm, raw_row)

        self.buffer: str = ""

    def append_text_view(self, text):
        self.buffer += text

    @property
    def selected(self):
        return self.raw_row[self._SELECTION]

    @selected.setter
    def selected(self, value):
        self.raw_row[self._SELECTION] = value

    @property
    def icon(self):
        return self.raw_row[self._ICON]

    @property
    def name(self):
        return self.raw_row[self._NAME].name

    @property
    def color_name(self):
        return self.raw_row[self._NAME]

    @property
    def updates_available(self):
        return self.raw_row[self._UPDATES_AVAILABLE]

    @updates_available.setter
    def updates_available(self, value):
        updates_available = bool(
            self.vm.features.get('updates-available', False))
        supported = check_support(self.vm)

        if value and not updates_available:
            updates_available = None
        self.raw_row[self._UPDATES_AVAILABLE] = \
            UpdatesAvailable.from_features(updates_available, supported)

    @property
    def last_updates_check(self):
        return self.raw_row[self._LAST_UPDATES_CHECK]

    @property
    def last_update(self):
        return self.raw_row[self._LAST_UPDATE]

    def get_update_progress(self):
        return self.raw_row[self._UPDATE_PROGRESS]

    @property
    def status(self) -> UpdateStatus:
        return self.raw_row[self._STATUS]

    def set_status(self, status_code: UpdateStatus):
        self.raw_row[self._STATUS] = status_code

    def set_update_progress(self, progress):
        self.raw_row[self._UPDATE_PROGRESS] = progress


class UpdateHeaderCheckbox(HeaderCheckbox):
    def __init__(self, checkbox_column_button, next_button):
        super().__init__(checkbox_column_button,
                         [UpdatesAvailable.YES,
                          UpdatesAvailable.MAYBE,
                          UpdatesAvailable.NO])
        self.next_button = next_button

    def all_action(self, *args, **kwargs):
        self.next_button.set_sensitive(True)

    def inconsistent_action(self, *args, **kwargs):
        self.next_button.set_sensitive(True)

    def none_action(self, *args, **kwargs):
        self.next_button.set_sensitive(False)


class Date:
    """
    Prints Date in desired way: unknown, today, yesterday, normal date.

    Comparable.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.date_format_source = "%Y-%m-%d %H:%M:%S"
        if len(args) == 1 and args[0] is None:
            self.datetime = datetime.min
        elif len(args) == 1 and isinstance(args[0], str):
            self.datetime = datetime.strptime(args[0], self.date_format_source)
        else:
            self.datetime = datetime(*args, *kwargs)
        self.date_format = "%Y-%m-%d"

    @classmethod
    def from_datetime(cls, datetime_: datetime):
        self = cls(1, 1, 1)
        self.datetime = datetime_
        return self

    def __str__(self):
        date_str = self.datetime.strftime(self.date_format)
        today_str = datetime.today().strftime(self.date_format)
        yesterday = datetime.today() - timedelta(days=1)
        yesterday_str = yesterday.strftime(self.date_format)
        unknown_str = datetime.min.strftime(self.date_format)
        if date_str == today_str:
            return "today"
        if date_str == yesterday_str:
            return "yesterday"
        if date_str == unknown_str:
            return "unknown"
        return date_str

    def __eq__(self, other):
        return self.datetime == other.datetime

    def __lt__(self, other):
        return self.datetime < other.datetime


class UpdatesAvailable(Enum):
    """
    Formatted info about updates.

    Comparable.
    """

    YES = 0
    MAYBE = 1
    NO = 2
    EOL = 3

    @staticmethod
    def from_features(updates_available: Optional[bool],
                      supported: Optional[str]=None) -> "UpdatesAvailable":
        if not supported:
            return UpdatesAvailable.EOL
        if updates_available:
            return UpdatesAvailable.YES
        if updates_available is None:
            return UpdatesAvailable.MAYBE
        return UpdatesAvailable.NO

    @property
    def color(self):
        if self is UpdatesAvailable.YES:
            return label_color_theme("green")
        if self is UpdatesAvailable.MAYBE:
            return label_color_theme("orange")
        if self is UpdatesAvailable.NO:
            return label_color_theme("black")
        if self is UpdatesAvailable.EOL:
            return label_color_theme('red')

    def __str__(self):
        if self is UpdatesAvailable.YES:
            name = "YES"
        elif self is UpdatesAvailable.MAYBE:
            name = "MAYBE"
        elif self is UpdatesAvailable.NO:
            name = "NO"
        elif self is UpdatesAvailable.EOL:
            name = "OBSOLETE"
        else:
            name = "ERROR"
        return f'<span foreground="{self.color}"><b>' \
               + name + '</b></span>'

    def __eq__(self, other: "UpdatesAvailable"):
        return self.value == other.value

    def __lt__(self, other: "UpdatesAvailable"):
        return self.value < other.value
