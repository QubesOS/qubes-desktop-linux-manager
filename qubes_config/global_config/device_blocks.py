# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022 Marta Marczykowska-Górecka
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

from typing import List, Optional, Iterator, Callable

from qubesadmin.device_protocol import DeviceCategory, DeviceInterface

from ..widgets.gtk_widgets import TokenName, VMListModeler
from .device_widgets import (
    DevPolicyDialogHandler,
    DevPolicyRow,
    DevicePolicyHandler,
)
import gi

import qubesadmin.exc

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class DevicePolicyDialog(DevPolicyDialogHandler):
    """Handler for the Edit Blocks window."""

    def __init__(self, builder: Gtk.Builder, qapp, parent_window: Gtk.Window):
        super().__init__(builder, qapp, "device_policy", parent_window)

        self.new_label: Gtk.Label = builder.get_object(
            "device_policy_new_label"
        )

        self.block_box: Gtk.Box = builder.get_object("device_policy_block_box")
        self.qube_combo: Gtk.ComboBox = builder.get_object(
            "device_policy_vm_combo"
        )
        self.listbox: Gtk.ListBox = builder.get_object("device_policy_listbox")

        # setup qube modeler
        self.qube_model = VMListModeler(
            combobox=self.qube_combo,
            qapp=self.qapp,
            filter_function=lambda vm: vm.klass != "AdminVM",
            current_value=None,
        )
        self.qube_model.connect_change_callback(self._qube_selected)

        # setup treeview
        self.device_category_model = DeviceCategoryModeler()
        for row in self.device_category_model.get_rows():
            self.listbox.add(row)
            row.check_box.connect("toggled", self.validate)

        self.other_row: Optional["DeviceCategoryRow"] = None

        self.listbox.connect("row-activated", self._row_activated)

    def _save_changes(self, *_args):
        if not self.current_row:
            self._cancel()
            return
        # save changed VM
        self.current_row.vm_wrapper.vm = self.qube_model.get_selected()

        # save changed categories
        new_categories = []
        for row in self.listbox.get_children():
            if isinstance(row, OtherCategoryRow):
                continue
            if row.check_box.get_active():
                if not row.parent or not row.parent.check_box.get_active():
                    new_categories.append(row.category_wrapper)

        self.current_row.vm_wrapper.categories = new_categories

        super()._save_changes()

    def run_for_new(self, new_row_function: Callable) -> DevPolicyRow:
        """Run for a new rule"""
        self.dialog.set_title(_("New Device Attachment Block"))
        self.clear()
        return super().run_for_new(new_row_function)

    def run_for_existing(self, row: "DevPolicyRow"):
        """Run for an existing rule"""
        self.dialog.set_title("Edit Device Attachment Block")
        super().run_for_existing(row)
        self.clear()
        self.qube_model.select_value(row.vm_wrapper.vm)
        self.select_rows(row.vm_wrapper.categories)

        if row.vm_wrapper.other_interfaces:
            self.other_row = OtherCategoryRow(row.vm_wrapper.other_interfaces)
            self.listbox.add(self.other_row)

    def clear(self):
        """Clear all selections and dropdowns"""
        self.qube_model.clear_selection()

        if self.other_row:
            self.listbox.remove(self.other_row)
            self.other_row = None

        for row in self.listbox.get_children():
            row.check_box.set_active(False)

    def select_rows(self, categories: list["DeviceCategoryWrapper"]):
        """Select rows matching provided categories"""
        last_parent = None
        for row in self.listbox.get_children():
            if last_parent == row.parent:
                continue
            if row.category_wrapper in categories:
                row.check_box.set_active(True)
                last_parent = row

    def _row_activated(self, _box, row, *_args):
        row.row_activated()

    def check_validity(self) -> bool:
        """Check if current state is save-able (in this case, a VM is
        selected and at least one rule is selected)."""
        if self.qube_model.get_selected():
            for row in self.listbox.get_children():
                if row.check_box.get_active():
                    return True
        return False

    def _qube_selected(self, *_args):
        if self.qube_model.get_selected():
            self.new_label.set_visible(False)
            self.block_box.set_sensitive(True)
        else:
            self.new_label.set_visible(True)
            self.block_box.set_sensitive(False)

        self.validate()


class DeviceCategoryWrapper:
    """This class represents a DeviceCategory with a nice description
    wrapped around it."""

    def __init__(
        self, name: str, device_category: DeviceCategory, description: str = ""
    ):
        """
        :param name: readable name of the category
        :param device_category: relevant DeviceCategory
        :param description: optional description (will be shown in smaller font
        beneath the main description)
        """
        self.name = name
        self.children: List[DeviceCategoryWrapper] = []
        self.device_category = device_category
        self.description = description
        self.interfaces = [
            DeviceInterface(s) for s in self.device_category.value
        ]

    def readable_description(self):
        """Nicely formatted category description, perfect to be placed in a
        Gtk.Label's markup."""
        if self.description:
            return self.name + "\n<small>{}</small>".format(self.description)
        return self.name

    def matches(
        self, interfaces: list[DeviceInterface]
    ) -> (Optional)[list[DeviceInterface]]:
        """
        If in the given list of string representations of interfaces there is a
        complete match with my own category, return the matching list of
        interfaces.
        """
        if set(interfaces).issuperset(set(self.interfaces)):
            return self.interfaces
        return None

    def __eq__(self, other):
        return self.device_category == getattr(other, "device_category", None)


class DeviceCategoryRow(Gtk.ListBoxRow):
    """Gtk.ListBoxRow representing a block category"""

    def __init__(
        self,
        category_wrapper: DeviceCategoryWrapper,
        parent: Optional["DeviceCategoryRow"],
    ):
        """
        :param category_wrapper: relevant DeviceCategoryWrapper
        :param parent: parent row; if present, this row will be indented
        relative to the parent and will 1. be selected when the parent is
        selected 2. will deselect the parent if deselected
        """
        super().__init__()
        self.category_wrapper = category_wrapper
        self.depth: int = parent.depth + 1 if parent else 0
        self.parent = parent

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_box.set_spacing(0)
        self.main_box.set_margin_start(30 * self.depth)

        self.add(self.main_box)

        self.check_box: Gtk.CheckButton = Gtk.CheckButton()
        self.main_box.add(self.check_box)
        self.description_label = Gtk.Label()
        self.description_label.set_markup(
            self.category_wrapper.readable_description()
        )
        self.main_box.add(self.description_label)
        self.show_all()

        self.children: List[DeviceCategoryRow] = []
        self.check_box.connect("toggled", self._row_checked)

    def row_activated(self):
        self.check_box.set_active(not self.check_box.get_active())

    def _row_checked(self, *_args):
        if not self.check_box.get_active() and self.parent:
            self.parent.check_box.set_active(False)
        for child in self.children:
            child.check_box.set_active(self.check_box.get_active())


class OtherCategoryRow(Gtk.ListBoxRow):
    """Special row for the Other interfaces (listed as text and unclickable"""

    def __init__(self, interfaces: list[DeviceInterface]):
        super().__init__()
        self.other_interfaces: list[DeviceInterface] = interfaces

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_box.set_spacing(10)

        self.add(self.main_box)

        self.check_box = Gtk.CheckButton()
        self.check_box.set_active(True)
        self.main_box.add(self.check_box)
        self.description_label = Gtk.Label()
        self.description_label.set_markup(_("Other: "))
        self.main_box.add(self.description_label)

        self.text_box = Gtk.Entry()
        self.main_box.add(self.text_box)
        self.text_box.set_text(
            ", ".join([repr(i) for i in self.other_interfaces])
        )
        self.set_tooltip_text(_("Block set in command line."))
        self.set_sensitive(False)
        self.show_all()


class DeviceCategoryModeler:
    """Helper class to manage our DeviceCategoryWrapper model"""

    def __init__(self):
        self.root_device = DeviceCategoryWrapper(
            "All devices", DeviceCategory.Other
        )
        self.root_device.children.append(
            DeviceCategoryWrapper(
                _("Network devices"),
                DeviceCategory.Network,
                _("modems, WiFi and Ethernet adapters"),
            )
        )

        hid_devices = DeviceCategoryWrapper(
            _("Human interface devices"),
            DeviceCategory.Input,
            _("all input devices, such as mice, keyboards, tablets etc."),
        )
        self.root_device.children.append(hid_devices)
        hid_devices.children.append(
            DeviceCategoryWrapper(_("Keyboards"), DeviceCategory.Keyboard)
        )
        hid_devices.children.append(
            DeviceCategoryWrapper(_("Mice"), DeviceCategory.Mouse)
        )

        self.root_device.children.append(
            DeviceCategoryWrapper(_("Printers"), DeviceCategory.Printer)
        )

        self.root_device.children.append(
            DeviceCategoryWrapper(
                _("Image input devices"),
                DeviceCategory.Image_Input,
                _("Scanners and cameras"),
            )
        )

        self.root_device.children.append(
            DeviceCategoryWrapper(
                _("Multimedia output devices"),
                DeviceCategory.Multimedia_Output,
                _("Displays and audio output devices"),
            )
        )

        audio_devices = DeviceCategoryWrapper(
            _("Audio devices"), DeviceCategory.Audio
        )
        self.root_device.children.append(audio_devices)
        audio_devices.children.append(
            DeviceCategoryWrapper(("Microphones"), DeviceCategory.Microphone)
        )
        audio_devices.children.append(
            DeviceCategoryWrapper(
                _("Audio output devices"), DeviceCategory.Audio_Output
            )
        )

        storage_devices = DeviceCategoryWrapper(
            _("Storage devices"), DeviceCategory.Storage
        )
        self.root_device.children.append(storage_devices)
        storage_devices.children.append(
            DeviceCategoryWrapper(
                _("Block devices"), DeviceCategory.Block_Storage
            )
        )
        storage_devices.children.append(
            DeviceCategoryWrapper(
                _("USB storage devices"),
                DeviceCategory.USB_Storage,
                _(
                    "USB storage devices may offer more capabilities "
                    "than block storage devices.\nMost storage devices "
                    "can be attached as either block device or USB "
                    "device"
                ),
            )
        )

        self.root_device.children.append(
            DeviceCategoryWrapper(_("Bluetooth"), DeviceCategory.Bluetooth)
        )

        self.root_device.children.append(
            DeviceCategoryWrapper(
                _("Smart card readers"), DeviceCategory.Smart_Card_Readers
            )
        )

    def get_rows(
        self, parent_row: DeviceCategoryRow | None = None
    ) -> Iterator[DeviceCategoryRow]:
        """Get relevant ListBoxRows"""
        if not parent_row:
            parent_row = DeviceCategoryRow(self.root_device, None)
            yield parent_row

        for child in parent_row.category_wrapper.children:
            row = DeviceCategoryRow(child, parent_row)
            parent_row.children.append(row)
            yield row
            yield from self.get_rows(row)

    def parse_interfaces(
        self,
        interfaces: list[DeviceInterface],
        categories: list[DeviceCategoryWrapper] | None = None,
        node: DeviceCategoryWrapper | None = None,
    ) -> tuple[list[DeviceCategoryWrapper], list[DeviceInterface]]:
        """Turn a list of DeviceInterfaces into matching DeviceCategories and
        a list of remaining interfaces"""
        if categories is None:
            categories = []
        if node is None:
            node = self.root_device

        matched_interfaces = node.matches(interfaces)

        if matched_interfaces:
            for m in matched_interfaces:
                interfaces.remove(m)
            categories.append(node)
            return categories, interfaces
        for child in node.children:
            categories, interfaces = self.parse_interfaces(
                interfaces, categories, child
            )
        return categories, interfaces


class BlockPolicyWrapper:
    """This class is a wrapper for a VM with its associated denied device
    interfaces."""

    def __init__(
        self,
        vm,
        interfaces: List[DeviceInterface],
        dev_cat_modeler: DeviceCategoryModeler,
    ):
        self.original_vm = vm
        self.vm = vm
        self.interfaces = interfaces
        self.dev_cat_modeler = dev_cat_modeler
        self.categories: list[DeviceCategoryWrapper] = []
        self.other_interfaces: list[DeviceInterface] = []
        self.update()

    def get_description(self) -> str:
        """Get a nicely formatted (markup) description"""
        int_descr = ""
        if self.categories:
            int_descr += ", ".join([cat.name for cat in self.categories])
        if self.other_interfaces:
            if int_descr:
                int_descr += ", "
            int_descr += ", ".join([repr(i) for i in self.other_interfaces])
        return _("<b>{}</b> cannot be attached to ").format(int_descr)

    def update(self):
        """Update matching categories."""
        self.categories.clear()
        self.other_interfaces.clear()
        self.categories, self.other_interfaces = (
            self.dev_cat_modeler.parse_interfaces(self.interfaces.copy())
        )

    def save(self):
        """Save changes"""
        new_interfaces = []
        for c in self.categories:
            new_interfaces.extend(c.interfaces)
        new_interfaces.extend(self.other_interfaces)

        # remove old, make new
        if self.original_vm:
            # removing old only makes sense if they existed in the first place
            if self.original_vm != self.vm:
                self.remove()
            else:
                # remove only the missing ones
                for interface in self.interfaces:
                    if interface not in new_interfaces:
                        self.original_vm.devices.allow(interface)

        # make new blocks
        if self.original_vm != self.vm:
            # all of them
            for interface in new_interfaces:
                self.vm.devices.deny(interface)
        else:
            for interface in new_interfaces:
                if (
                    interface not in self.interfaces
                    and interface not in self.other_interfaces
                ):
                    self.vm.devices.deny(interface)

        self.interfaces = new_interfaces

    def remove(self):
        """Remove all existing blocks"""
        for interface in self.interfaces:
            self.original_vm.devices.allow(interface)


class BlockPolicyRow(DevPolicyRow):
    """ListBoxRow representing a vm with its associated blocks"""

    def __init__(self, vm_wrapper: BlockPolicyWrapper, qapp: qubesadmin.Qubes):
        super().__init__()
        self.vm_wrapper = vm_wrapper
        self.qapp = qapp

        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)

        self.label = Gtk.Label()
        self.box.add(self.label)
        self.vm_token: TokenName | None = None

        self.update()

    def description(self):
        """Nicely readable description, for use in unsaved changes (for
        example)"""
        return self.vm_wrapper.get_description() + self.vm_wrapper.vm.name

    def update(self):
        """Update displayed state."""
        if self.vm_token:
            self.box.remove(self.vm_token)
            self.vm_token = None

        if self.vm_wrapper.vm:
            self.vm_token = TokenName(self.vm_wrapper.vm, self.qapp)
            self.box.add(self.vm_token)
            self.box.show_all()
        else:
            self.vm_token = None

        self.label.set_markup(self.vm_wrapper.get_description())

        if self.vm_wrapper.vm:
            # only show all if it's in any way a sensible row
            self.show_all()

    def save(self):
        """Save changes in this row."""
        if not self.changed:
            return
        self.vm_wrapper.save()

        super().save()

    def remove_self(self):
        """Remove all blocks from the system"""
        self.vm_wrapper.remove()

    def __str__(self):
        return self.vm_wrapper.get_description() + self.vm_wrapper.vm.name


class DeviceBlockHandler(DevicePolicyHandler):
    """Handler class for all interface blocks"""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        builder: Gtk.Builder,
        device_policy_manager,
    ):
        self.device_category_modeler = DeviceCategoryModeler()
        super().__init__(
            prefix="devices_policy",
            builder=builder,
            qapp=qapp,
            device_policy_manager=device_policy_manager,
            edit_dialog_class=DevPolicyDialogHandler,
        )

    def load_current_state(self):
        """Load state from system"""
        rules = []
        for vm, interfaces in self.device_policy_manager.get_blocks():
            rules.append(
                BlockPolicyWrapper(vm, interfaces, self.device_category_modeler)
            )

        for rule in rules:
            self.rule_list.add(BlockPolicyRow(rule, self.qapp))

    def create_new_row(self) -> BlockPolicyRow:
        blank_rule = BlockPolicyWrapper(None, [], self.device_category_modeler)
        new_row = BlockPolicyRow(blank_rule, self.qapp)
        return new_row

    def get_edit_dialog(self, builder) -> DevPolicyDialogHandler:
        return DevicePolicyDialog(
            builder=builder, qapp=self.qapp, parent_window=self.main_window
        )
