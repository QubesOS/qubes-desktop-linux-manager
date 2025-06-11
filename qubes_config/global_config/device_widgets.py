# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2025 Marta Marczykowska-Górecka
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
Widgets relevant to Device Attachments page.
"""
import abc
from typing import List, Any, Callable

import gi

from ..widgets.gtk_utils import ask_question, resize_window_to_reasonable

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class HeaderComboModeler:
    """A model handler for a ComboBox with a list with headers (insensitive
    and unselectable)"""

    def __init__(
        self,
        combobox: Gtk.ComboBox,
        values: dict[str, tuple[str, Any]],
    ):
        """
        A helper for modeling ComboBox contents that consist of a list with
        headers (headers are not sensitive).
        :param combobox: A Gtk.ComboBox or ComboBoxText to be filled
        :param values: a dictionary that maps value_id (str) to a tuple of
        nicely presented value (str) and the actual underlying value or None,
        if it's a header
        """
        self._combo: Gtk.ComboBox = combobox
        self._combo.clear()
        self._values: dict[str, tuple[str, Any]] = values

        self._model = Gtk.ListStore(str, str, bool)  # id, text and sensitivity
        self._fill_model()

        renderer = Gtk.CellRendererText()
        self._combo.set_model(self._model)
        self._combo.set_id_column(0)
        self._combo.pack_start(renderer, True)
        self._combo.add_attribute(renderer, "text", 1)
        self._combo.add_attribute(renderer, "sensitive", 2)

    def get_selected(self):
        """Get currently selected value."""
        active_id = self._combo.get_active_id()
        result_tuple = self._values.get(active_id, None)
        if result_tuple:
            return result_tuple[1]
        return None

    def _fill_model(self):
        self._model.clear()
        for device_id, value in self._values.items():
            description, device = value
            self._model.append([device_id, description, bool(device)])

    def select_value(self, selected_value: Any):
        """Select provided value, if available."""
        self._fill_model()

        for key, value in self._values.items():
            if value[1] == selected_value:
                self._combo.set_active_id(key)


class DevPolicyRow(Gtk.ListBoxRow):
    """Base class for ListBoxRows representing various policy rules on the
    Device Assignments page.
    This is not an abstract class because Gtk.ListBoxRow already inherits
    from an abstract class."""

    def __init__(self):
        super().__init__()
        self.changed = False
        self.valid = True

    @abc.abstractmethod
    def update(self):
        """Update displayed state"""

    @abc.abstractmethod
    def save(self):
        """Save changes to the system"""
        self.changed = False

    @abc.abstractmethod
    def remove_self(self):
        """
        This should remove the current assignment or policy from the system.
        """


class DevPolicyDialogHandler:
    """
    A generic class for various Edit Device Policy row dialogs.

    Every edit dialog needs:
    - {prefix}_dialog - a Gtk.Dialog
    - {prefix}_ok_button - a Gtk.Button
    - {prefix}_cancel_button - a Gtk.Button
    """

    def __init__(
        self, builder: Gtk.Builder, qapp, prefix: str, parent_window: Gtk.Window
    ):
        self.qapp = qapp

        self.dialog: Gtk.Dialog = builder.get_object(f"{prefix}_dialog")
        self.dialog.set_transient_for(parent_window)

        # ok and cancel buttons
        self.ok_button: Gtk.Button = builder.get_object(f"{prefix}_ok_button")
        self.cancel_button: Gtk.Button = builder.get_object(f"{prefix}_cancel_button")

        self.current_row: Gtk.ListBoxRow | None = None
        self.remove_on_cancel = False

        self.dialog.connect("delete-event", self._cancel)
        self.ok_button.connect("clicked", self._save_changes)
        self.cancel_button.connect("clicked", self._cancel)

        self.dialog.connect("size-allocate", self._resize_window)

    def _resize_window(self, *_args):
        resize_window_to_reasonable(self.dialog)

    def _cancel(self, *_args):
        if self.remove_on_cancel and self.current_row:
            self.current_row.get_parent().remove(self.current_row)
        self.current_row = None
        self.remove_on_cancel = False
        self.dialog.hide()
        # return True to stop other handlers from destroying the dialog
        return True

    def _save_changes(self, *_args):
        if not self.current_row:
            self._cancel()
            return
        self.current_row.update()
        self.current_row.changed = True
        parent = self.current_row.get_parent()

        self.current_row = None
        self.remove_on_cancel = False

        self.dialog.hide()
        parent.emit("rules-changed", None)

    def run_for_new(self, new_row_function: Callable) -> DevPolicyRow:
        """Run for a new row"""
        new_row = new_row_function()
        self.current_row = new_row
        self.remove_on_cancel = True

        self.dialog.show()
        self._resize_window()

        return new_row

    def run_for_existing(self, row: DevPolicyRow):
        """Run for an existing row"""
        self.current_row = row
        self.validate()
        self.remove_on_cancel = False
        self.dialog.show()
        self._resize_window()

    def validate(self, *_args):
        """Connect this function to any events that should trigger
        re-checking for dialog validity."""
        self.ok_button.set_sensitive(self.check_validity())

    def check_validity(self) -> bool:
        """Return True if the current dialog state should allow saving,
        False otherwise."""
        return True

    def fill_combo_with_devices(
        self, dev_classes: dict, combo: Gtk.ComboBox, device_manager, dev_row_class
    ) -> HeaderComboModeler:
        """Fill provided combobox with current devices"""
        dev_list = {}
        for class_id, class_name in dev_classes.items():
            devices = list(device_manager.get_available_devices([class_id]))
            if devices:
                dev_list[class_name] = (class_name, None)
                for dev in devices:
                    dw = dev_row_class.new_from_device_info(dev)
                    dev_list[dw.device_id] = (dw.long_name, dw)

        combo.connect("changed", self.validate)

        return HeaderComboModeler(combo, dev_list)


class DevicePolicyHandler:
    """Generic handler for DeviceAssignments"""

    def __init__(
        self,
        prefix: str,
        builder: Gtk.Builder,
        qapp,
        device_policy_manager,
        edit_dialog_class,
    ):
        self.qapp = qapp
        self.device_policy_manager = device_policy_manager
        self.edit_dialog_class = edit_dialog_class

        self.main_window: Gtk.Window = builder.get_object("main_window")

        self.rule_list: Gtk.ListBox = builder.get_object(f"{prefix}_list")

        self.add_button: Gtk.Button = builder.get_object(f"{prefix}_add_rule_button")
        self.edit_button: Gtk.Button = builder.get_object(f"{prefix}_edit_rule_button")
        self.remove_button: Gtk.Button = builder.get_object(f"{prefix}_del_rule_button")

        self.add_button.connect("clicked", self.add_new_rule)
        self.edit_button.connect("clicked", self.edit_rule)
        self.remove_button.connect("clicked", self.remove_rule)
        self.rule_list.connect("row-selected", self._row_selected)
        self.rule_list.connect("row-activated", self.edit_rule)

        self.edit_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)

        self.removed_rows: List[DevPolicyRow] = []

        self.edit_dialog = self.get_edit_dialog(builder)

        self.load_current_state()

    def _row_selected(self, *_args):
        row = self.rule_list.get_selected_row()
        if row:
            self.edit_button.set_sensitive(row.valid)
            self.remove_button.set_sensitive(True)
        else:
            self.edit_button.set_sensitive(False)
            self.remove_button.set_sensitive(False)

    def add_new_rule(self, *_args):
        """Add a new row to the list"""
        new_row = self.edit_dialog.run_for_new(self.create_new_row)
        self.rule_list.add(new_row)

    def edit_rule(self, *_args):
        """Edit currently selected rule"""
        current_row = self.rule_list.get_selected_row()
        self.edit_dialog.run_for_existing(current_row)

    def remove_rule(self, *_args):
        current_row = self.rule_list.get_selected_row()
        response = ask_question(
            self.main_window,
            "Delete rule",
            _("Are you sure you want to delete rule:\n") + str(current_row),
        )
        if response == Gtk.ResponseType.NO:
            return

        self.removed_rows.append(current_row)
        self.rule_list.remove(current_row)
        self.rule_list.emit("rules-changed", None)

    def save(self) -> None:
        """Save all changes"""
        # new and existing
        for row in self.rule_list.get_children():
            row.save()

        # removed
        for row in self.removed_rows:
            row.remove_self()

        self.removed_rows.clear()
        self.device_policy_manager.load_data()

    def reset(self) -> None:
        """Reset all changes."""
        for row in self.rule_list.get_children():
            self.rule_list.remove(row)
        self.removed_rows.clear()
        self.load_current_state()

    def get_unsaved(self) -> str:
        """
        Get all unsaved changes.
        """
        results = []
        for row in self.rule_list.get_children():
            if row.changed:
                results.append(_("Attachment changed: ") + str(row))

        for row in self.removed_rows:
            results.append(_("Removed assignment: ") + str(row))

        return "\n".join(results)

    @abc.abstractmethod
    def create_new_row(self) -> DevPolicyRow:
        """This function should return a blank DevPolicyRow."""

    def load_current_state(self):
        """This function should load current system state."""

    @abc.abstractmethod
    def get_edit_dialog(self, builder: Gtk.Builder) -> DevPolicyDialogHandler:
        """this function should get a DevPolicyDialogHandler for an
        appropriate edit dialog."""
