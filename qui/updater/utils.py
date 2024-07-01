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
import ast
import functools
import gi

from enum import Enum
from typing import List

gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk


def disable_checkboxes(func):
    """
    Workaround for avoiding circular recursion.

    Clicking on the header checkbox sets the value of the rows checkboxes, so it
    calls the connected method which sets the header checkbox, and so on...
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, "disable_checkboxes"):
            raise TypeError("To use this decorator inside the class yu need to"
                            " add attribute `disable_checkboxes`.")
        if self.disable_checkboxes:
            return
        self.disable_checkboxes = True
        func(self, *args, **kwargs)
        self.disable_checkboxes = False

    return wrapper


def pass_through_event_window(button):
    """
    Clicking on header button should activate the button not the header itself.
    """
    if not isinstance(button, Gtk.Button):
        raise TypeError("%r is not a gtk.Button" % button)
    event_window = button.get_event_window()
    event_window.set_pass_through(True)


class HeaderCheckbox:
    NONE = 0
    SAFE = 1
    EXTENDED = 2
    ALL = 3
    SELECTED = 4

    def __init__(self, header_button, allowed):
        self.header_button = header_button
        self.state = HeaderCheckbox.SAFE
        self._allowed: List = allowed

    @property
    def allowed(self):
        if self.state == HeaderCheckbox.ALL:
            return self._allowed[:]
        if self.state == HeaderCheckbox.SAFE:
            return self._allowed[:1]
        if self.state == HeaderCheckbox.EXTENDED:
            return self._allowed[:2]
        if self.state == HeaderCheckbox.NONE:
            return ()

    def set_buttons(self, *args, **kwargs):
        if self.state == HeaderCheckbox.ALL:
            self.header_button.set_inconsistent(False)
            self.header_button.set_active(True)
            self.all_action(*args, **kwargs)
        elif self.state == HeaderCheckbox.NONE:
            self.header_button.set_inconsistent(False)
            self.header_button.set_active(False)
            self.none_action(*args, **kwargs)
        else:
            self.header_button.set_inconsistent(True)
            self.inconsistent_action(*args, **kwargs)

    def next_state(self):
        self.state = (self.state + 1) % 4  # SELECTED is skipped

    def all_action(self, *args, **kwargs):
        raise NotImplementedError()

    def inconsistent_action(self, *args, **kwargs):
        raise NotImplementedError()

    def none_action(self, *args, **kwargs):
        raise NotImplementedError()


def on_head_checkbox_toggled(list_store, head_checkbox, select_rows):
    if len(list_store) == 0:  # to avoid infinite loop
        head_checkbox.state = HeaderCheckbox.NONE
        selected_num = 0
    else:
        selected_num = selected_num_old = sum(
            row.selected for row in list_store)
        while selected_num == selected_num_old:
            head_checkbox.next_state()
            select_rows()
            selected_num = sum(
                row.selected for row in list_store)
    head_checkbox.set_buttons(selected_num)


class QubeClass(Enum):
    """
    Sorting order by vm type.
    """
    AdminVM = 0
    TemplateVM = 1
    StandaloneVM = 2
    AppVM = 3
    DispVM = 4

__effective_css_provider__: Gtk.CssProvider = None

def SetEffectiveCssProvider(CssProvider: Gtk.CssProvider) -> None:
    global __effective_css_provider__
    __effective_css_provider__ = CssProvider

def label_color_theme(color: str) -> str:
    global __effective_css_provider__
    widget = Gtk.Label()
    if __effective_css_provider__ == None:
        # Replicating the old behaviour. Both forward and backward compatible
        widget.get_style_context().add_class(f'qube-box-{color}')
    elif f'.qube-box-{color}' in __effective_css_provider__.to_string():
        widget.get_style_context().add_class(f'qube-box-{color}')
    else:
        widget.get_style_context().add_class('qube-box-custom-label')
    gtk_color = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
    color_rgb = ast.literal_eval(gtk_color.to_string()[3:])
    color_hex = '#{:02x}{:02x}{:02x}'.format(*color_rgb)
    return color_hex


class QubeName:
    def __init__(self, name, color):
        self.name = name
        self.color = color

    def __str__(self):
        return f'<span foreground="{label_color_theme(self.color)}' \
               '"><b>' + self.name + '</b></span>'

    def __eq__(self, other):
        return self.name == other.name

    def __lt__(self, other):
        return self.name < other.name


class UpdateStatus(Enum):
    Success = 0
    NoUpdatesFound = 1
    Cancelled = 2
    Error = 3
    InProgress = 4
    ProgressUnknown = 5
    Undefined = 6

    def __str__(self):
        text = "Error"
        color = "red"
        if self == UpdateStatus.Success:
            text = "Updated successfully"
            color = "green"
        elif self == UpdateStatus.NoUpdatesFound:
            text = "No updates found"
            color = "green"
        elif self == UpdateStatus.Cancelled:
            text = "Cancelled"
        elif self in (UpdateStatus.InProgress, UpdateStatus.ProgressUnknown):
            text = "In progress"

        return f'<span foreground="{color}">' + text + '</span>'

    def __eq__(self, other):
        return self.value == other.value

    def __lt__(self, other):
        return self.value < other.value

    def __bool__(self):
        return self == UpdateStatus.Success

    @staticmethod
    def from_name(name):
        names = {"success": UpdateStatus.Success,
                 "error": UpdateStatus.Error,
                 "no_updates": UpdateStatus.NoUpdatesFound,
                 "cancelled": UpdateStatus.Cancelled}
        return names[name]


class RowWrapper:
    def __init__(self, list_store, vm, raw_row: list):
        super().__init__()
        self.list_store = list_store
        self.vm = vm

        self.list_store.append([self, *raw_row])
        self.raw_row = self.list_store[-1]

    def __eq__(self, other):
        if self.vm.klass == other.vm.klass:
            return self.vm.label.index == other.vm.label.index
        return False

    def __lt__(self, other):
        self_class = QubeClass[self.vm.klass]
        other_class = QubeClass[other.vm.klass]
        if self_class == other_class:
            return self.vm.label.index == other.vm.label.index
        return self_class.value < other_class.value

    @property
    def selected(self):
        raise NotImplementedError()

    @selected.setter
    def selected(self, value):
        raise NotImplementedError()

    @property
    def icon(self):
        raise NotImplementedError()

    @property
    def name(self):
        raise NotImplementedError()

    @property
    def color_name(self):
        raise NotImplementedError()


class UpdateListIter:
    def __init__(self, list_store_wrapped):
        self.list_store_wrapped = list_store_wrapped
        self._id = -1

    def __next__(self) -> RowWrapper:
        self._id += 1
        if 0 <= self._id < len(self.list_store_wrapped):
            return self.list_store_wrapped[self._id]
        raise StopIteration


class ListWrapper:
    def __init__(self, row_type, list_store_raw):
        self.list_store_raw = list_store_raw
        self.list_store_wrapped: list = []
        self.row_type = row_type
        for idx in range(self.row_type.COLUMN_NUM):
            self.list_store_raw.set_sort_func(idx, self.sort_func, idx)

    def __iter__(self) -> UpdateListIter:
        return UpdateListIter(self.list_store_wrapped)

    def __getitem__(self, item):
        return self.list_store_wrapped[item]

    def __len__(self) -> int:
        return len(self.list_store_wrapped)

    def append_vm(self, vm, state: bool = False):
        qube_row = self.row_type(self.list_store_raw, vm, state)
        self.list_store_wrapped.append(qube_row)

    def invert_selection(self, path):
        it = self.list_store_raw.get_iter(path)
        self.list_store_raw[it][0].selected = \
            not self.list_store_raw[it][0].selected

    def get_selected(self) -> "ListWrapper":
        empty_copy = Gtk.ListStore(*(
            self.list_store_raw.get_column_type(i)
            for i in range(self.list_store_raw.get_n_columns())
        ))
        result = ListWrapper(self.row_type, empty_copy)
        selected_rows = [row for row in self if row.selected]
        for row in selected_rows:
            result.append_vm(row.vm)
        return result

    def sort_func(self, model, iter1, iter2, data):
        # Get the values at the two iter indices
        value1 = model[iter1][data]
        value2 = model[iter2][data]

        # Compare the values and return -1, 0, or 1
        if value1 < value2:
            return -1
        if value1 == value2:
            return 0
        return 1
