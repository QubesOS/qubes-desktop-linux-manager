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
Device attachment functionality.
"""
from typing import List, Optional, Tuple, Iterator, Callable

from qubesadmin.device_protocol import (
    DeviceAssignment,
    AssignmentMode,
    DeviceInfo,
    Port,
    DeviceInterface,
)

from ..widgets.gtk_widgets import TokenName
from ..widgets.gtk_utils import show_error
from .device_widgets import (
    DevPolicyRow,
    DevPolicyDialogHandler,
    HeaderComboModeler,
    DevicePolicyHandler,
)
from .page_handler import PageHandler
from .vm_flowbox import VMFlowboxHandler
from .device_blocks import DeviceBlockHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

DEVICE_CLASSES = {
    "block": _("Block device"),
    "mic": _("Microphone"),
    "pci": _("PCI device"),
    "usb": _("USB device"),
}


class AutoDeviceDialog(DevPolicyDialogHandler):
    """
    The handler for an Edit Device Rule dialog window.
    """

    DEV_CLASSES = {
        "mic": _("Microphone"),
        "usb": _("USB Devices"),
        "block": _("Block Devices"),
    }

    def __init__(
        self,
        builder: Gtk.Builder,
        qapp,
        parent_window: Gtk.Window,
        device_manager: "DeviceManager",
    ):
        """
        Dialog for editing AutoAttachment options.
        """
        super().__init__(builder, qapp, "edit_device", parent_window)
        self.device_manager = device_manager

        self.dev_combo: Gtk.ComboBox = builder.get_object("edit_device_device_combo")

        self.backend_check: Gtk.CheckButton = builder.get_object(
            "edit_device_backend_check"
        )
        self.devclass_check: Gtk.CheckButton = builder.get_object(
            "edit_device_devclass_check"
        )
        self.devident_check: Gtk.CheckButton = builder.get_object(
            "edit_device_devident_check"
        )
        self.port_check: Gtk.CheckButton = builder.get_object("edit_device_port_check")

        self.devident_label: Gtk.Label = builder.get_object(
            "edit_device_devident_label"
        )

        self.backend_box: Gtk.Box = builder.get_object("edit_device_backend_box")
        self.backend_child: Optional[Gtk.Widget] = None  # formatted qube name

        self.auto_radio: Gtk.RadioButton = builder.get_object("edit_device_auto_radio")
        self.ask_radio: Gtk.RadioButton = builder.get_object("edit_device_ask_radio")

        self.unknown_box: Gtk.Box = builder.get_object("edit_device_unknown_box")
        self.err_label: Gtk.Label = builder.get_object("edit_device_err_label")
        self.read_only_check: Gtk.CheckButton = builder.get_object(
            "edit_device_read_only"
        )

        self.qube_handler = VMFlowboxHandler(
            builder,
            self.qapp,
            "edit_device",
            [],
            filter_function=lambda vm: vm.klass != "AdminVM",
        )

        self.backend_vm: Optional[qubesadmin.vm.QubesVM] = None
        self.dev_modeler = self.fill_combo_with_devices(
            self.DEV_CLASSES, self.dev_combo, self.device_manager, DeviceWrapper
        )

        self.devident_check.connect("toggled", self.validate)
        self.port_check.connect("toggled", self.validate)
        self.qube_handler.connect_change_callback(self.validate)
        self.dev_combo.connect("changed", self._combo_changed)

    def fill_checkboxes(
        self,
        backend_domain: Optional[qubesadmin.vm.QubesVM],
        devclass: str,
        dev_identity: str,
        port: str,
        ident_checked: bool,
        port_checked: bool,
        read_only: Optional[bool] = False,
    ):
        """Fill all checkboxes with appropriate values"""
        if self.backend_child:
            self.backend_box.remove(self.backend_child)
            self.backend_child = None
        if backend_domain:
            self.backend_child = TokenName(str(backend_domain), self.qapp)
            self.backend_box.pack_start(self.backend_child, False, False, 5)
            self.backend_box.show_all()
        self.backend_vm = backend_domain

        self.devclass_check.set_label(_("Device class: ") + devclass)

        # dev identity
        self.devident_label.set_text(dev_identity)
        self.devident_check.set_sensitive(True)
        self.devident_check.set_active(ident_checked)

        # port
        self.port_check.set_label("Port: " + port)
        self.port_check.set_sensitive(True)
        self.port_check.set_active(port_checked)

        if devclass == "block":
            self.read_only_check.set_sensitive(True)
            self.read_only_check.set_active(read_only)
        else:
            self.read_only_check.set_sensitive(False)
            self.read_only_check.set_active(False)

    def fill_checkboxes_from_device(self, device: "DeviceWrapper"):
        """Fill checkboxes based on a DeviceInfo"""
        self.fill_checkboxes(
            backend_domain=device.backend_domain,
            devclass=device.devclass,
            dev_identity=device.identity_description,
            port=str(device.port),
            ident_checked=True,
            port_checked=True,
        )

    def fill_checkboxes_from_assignment_wrapper(
        self, assignment_wrapper: "AssignmentWrapper"
    ):
        """Fill checkboxes based on a set of assignments"""
        if not assignment_wrapper.device.device:
            self.fill_checkboxes_from_none()
            return
        self.fill_checkboxes(
            backend_domain=assignment_wrapper.device.backend_domain,
            devclass=assignment_wrapper.device.devclass,
            dev_identity=assignment_wrapper.device_identity_description(),
            port=str(assignment_wrapper.device.device.port),
            ident_checked=assignment_wrapper.device_identity_required,
            port_checked=assignment_wrapper.port_required,
            read_only=assignment_wrapper.read_only,
        )

    def fill_checkboxes_from_none(self):
        """Fill checkboxes for an empty device"""
        if self.backend_child:
            self.backend_box.remove(self.backend_child)
            self.backend_child = None
            self.backend_vm = None

        self.devclass_check.set_label(_("Device class:"))

        # dev identity
        self.devident_label.set_text("")
        self.devident_check.set_active(False)
        self.devident_check.set_sensitive(False)

        # port
        self.port_check.set_label("Port: ")
        self.port_check.set_active(True)
        self.port_check.set_sensitive(False)

        self.read_only_check.set_sensitive(False)
        self.read_only_check.set_active(False)

    def check_validity(self):
        """Check if dialog can be saved/ok-ed"""
        self.err_label.set_visible(False)
        if not self.qube_handler.selected_vms:
            return False
        if not self.port_check.get_active() and not self.devident_check.get_active():
            return False
        for vm in self.qube_handler.selected_vms:
            if vm == self.backend_vm:
                self.err_label.set_visible(True)
                return False
        return True

    def _combo_changed(self, *_args):
        device = self.dev_modeler.get_selected()
        if device:
            self.fill_checkboxes_from_device(device)
        else:
            self.fill_checkboxes_from_none()

    def _save_changes(self, *_args):
        if not self.current_row:
            self._cancel()
            return
        assignment_wrapper = self.current_row.assignment_wrapper

        # we need to always save currently selected device, to avoid the hell of
        # finding it again
        if self.dev_modeler.get_selected():
            if assignment_wrapper.device != self.dev_modeler.get_selected():
                assignment_wrapper.changed = True
                assignment_wrapper.device = self.dev_modeler.get_selected()

        if (
            assignment_wrapper.device_identity_required
            != self.devident_check.get_active()
        ):
            assignment_wrapper.changed = True
            assignment_wrapper.device_identity_required = (
                self.devident_check.get_active()
            )

        if assignment_wrapper.port_required != self.port_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.port_required = self.port_check.get_active()

        if self.port_check.get_active():
            if assignment_wrapper.port != self.dev_modeler.get_selected().port:
                assignment_wrapper.changed = True
                assignment_wrapper.port = self.dev_modeler.get_selected().port
        if (
            self.auto_radio.get_active()
            and assignment_wrapper.mode != AssignmentMode.AUTO
        ):
            assignment_wrapper.changed = True
            assignment_wrapper.mode = AssignmentMode.AUTO
        elif (
            self.ask_radio.get_active()
            and assignment_wrapper.mode != AssignmentMode.ASK
        ):
            assignment_wrapper.changed = True
            assignment_wrapper.mode = AssignmentMode.ASK

        if assignment_wrapper.read_only != self.read_only_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.read_only = self.read_only_check.get_active()

        if sorted(assignment_wrapper.frontends) != sorted(
            self.qube_handler.selected_vms
        ):
            assignment_wrapper.changed = True
            assignment_wrapper.frontends = self.qube_handler.selected_vms.copy()

        super()._save_changes()

    def run_for_new(self, new_row_function: Callable) -> DevPolicyRow:
        """Open dialog for a new assignment"""
        self.dialog.set_title(_("Create New Device Assignment"))
        self.fill_checkboxes_from_none()
        self.dev_combo.set_active_id(None)
        self.qube_handler.reset()
        self.unknown_box.set_visible(False)

        self.auto_radio.set_active(True)
        self.validate()

        new_row = super().run_for_new(new_row_function)
        return new_row

    def run_for_existing(self, row: DevPolicyRow):
        """Open dialog for an existing assignment"""
        self.dialog.set_title(_("Edit Device Assignment"))

        # load data
        self.dev_modeler.select_value(row.assignment_wrapper.device)
        self.fill_checkboxes_from_assignment_wrapper(row.assignment_wrapper)

        if row.assignment_wrapper.mode == AssignmentMode.AUTO:
            self.auto_radio.set_active(True)
        else:
            self.ask_radio.set_active(True)

        # fill qubes
        self.qube_handler.reset()
        for qube in row.assignment_wrapper.frontends:
            self.qube_handler.add_selected_vm(qube)

        if not row.assignment_wrapper.device.device.is_device_id_set:
            if row.assignment_wrapper.device_identity_required:
                self.unknown_box.set_visible(True)
            else:
                # it looks weird to show "device unavailable" box for unknown
                # device when device is not shown
                self.unknown_box.set_visible(False)
            self.dev_combo.set_sensitive(False)
            self.port_check.set_sensitive(False)
            self.devident_check.set_sensitive(False)
            self.auto_radio.set_sensitive(False)
            self.ask_radio.set_sensitive(False)
            self.qube_handler.set_sensitive(False)
        else:
            self.unknown_box.set_visible(False)
            self.dev_combo.set_sensitive(True)
            self.port_check.set_sensitive(True)
            self.devident_check.set_sensitive(True)
            self.auto_radio.set_sensitive(True)
            self.ask_radio.set_sensitive(True)
            self.qube_handler.set_sensitive(True)

        super().run_for_existing(row)


class RequiredDeviceDialog(DevPolicyDialogHandler):
    DEV_CLASSES = {"pci": _("PCI Devices"), "block": _("Block Devices")}

    def __init__(
        self,
        builder: Gtk.Builder,
        qapp,
        parent_window: Gtk.Window,
        device_manager: "DeviceManager",
    ):
        """
        The handler for a Required Device Rule dialog window.
        """
        super().__init__(builder, qapp, "required_device", parent_window)
        self.device_manager = device_manager

        self.dev_combo: Gtk.ComboBox = builder.get_object(
            "required_device_device_combo"
        )
        self.devident_label: Gtk.Label = builder.get_object("required_device_devident")

        self.no_strict_check: Gtk.CheckButton = builder.get_object(
            "required_device_nostrict_check"
        )
        self.permissive_check: Gtk.CheckButton = builder.get_object(
            "required_device_permissive_check"
        )
        self.readonly_check: Gtk.CheckButton = builder.get_object(
            "required_device_readonly_check"
        )
        self.port_check: Gtk.CheckButton = builder.get_object(
            "required_device_port_check"
        )

        self.unknown_box: Gtk.Box = builder.get_object("required_device_unknown_box")
        self.err_label: Gtk.Label = builder.get_object("required_device_err_label")

        self.qube_handler = VMFlowboxHandler(
            builder,
            self.qapp,
            "required_device",
            [],
            filter_function=lambda vm: vm.klass != "AdminVM",
        )

        self.dev_modeler = self.fill_combo_with_devices(
            self.DEV_CLASSES, self.dev_combo, self.device_manager, DeviceWrapper
        )

        self.qube_handler.connect_change_callback(self.validate)

        self.dev_combo.connect("changed", self._combo_changed)

    def check_validity(self):
        """Check if dialog can be saved/ok-ed"""
        self.err_label.set_visible(False)
        if not self.qube_handler.selected_vms:
            return False
        if not self.dev_modeler.get_selected():
            return False
        backend_vm = self.dev_modeler.get_selected().backend_domain
        for vm in self.qube_handler.selected_vms:
            if vm == backend_vm:
                self.err_label.set_visible(True)
                return False
        return True

    @staticmethod
    def _init_check(
        check_button: Gtk.CheckButton,
        sensitive: bool,
        selected: bool,
        devclass_name: str,
    ):
        """Helper function to set state of checkbuttons"""
        check_button.set_sensitive(sensitive)
        check_button.set_active(selected)
        if sensitive:
            check_button.set_tooltip_text("")
        else:
            if not selected:
                check_button.set_tooltip_text(
                    _("Not available for {0} devices").format(devclass_name)
                )
            else:
                check_button.set_tooltip_text(
                    _("Always enabled for {0} devices").format(devclass_name)
                )

    def _combo_changed(self, *_args):
        device = self.dev_modeler.get_selected()
        if device:
            self.devident_label.set_text(
                device.identity_description + "\nPort: " + device.port_id
            )
            if device.devclass == "pci":
                self._init_check(self.readonly_check, False, False, "PCI")
                self._init_check(self.permissive_check, True, False, "PCI")
                self._init_check(self.no_strict_check, True, False, "PCI")
                self._init_check(self.port_check, False, True, "PCI")
            elif device.devclass == "block":
                self._init_check(self.readonly_check, True, False, "block")
                self._init_check(self.permissive_check, False, False, "block")
                self._init_check(self.no_strict_check, False, False, "block")
                self._init_check(self.port_check, True, True, "block")
        else:
            self.devident_label.set_text("No device selected.")
            self._init_check(self.readonly_check, False, False, "not selected")
            self._init_check(self.permissive_check, False, False, "not selected")
            self._init_check(self.no_strict_check, False, False, "not selected")
            self._init_check(self.port_check, False, False, "not selected")

    def _save_changes(self, *_args):
        if not self.current_row:
            self._cancel()
            return
        assignment_wrapper = self.current_row.assignment_wrapper

        if assignment_wrapper.no_strict_reset != self.no_strict_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.no_strict_reset = self.no_strict_check.get_active()

        if assignment_wrapper.permissive != self.permissive_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.permissive = self.permissive_check.get_active()

        if assignment_wrapper.read_only != self.readonly_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.read_only = self.readonly_check.get_active()

        if assignment_wrapper.device != self.dev_modeler.get_selected():
            assignment_wrapper.changed = True
            assignment_wrapper.device = self.dev_modeler.get_selected()

        if assignment_wrapper.port_required != self.port_check.get_active():
            assignment_wrapper.changed = True
            assignment_wrapper.port_required = self.port_check.get_active()

        if sorted(assignment_wrapper.frontends) != sorted(
            self.qube_handler.selected_vms
        ):
            assignment_wrapper.changed = True
            assignment_wrapper.frontends = self.qube_handler.selected_vms.copy()

        super()._save_changes()

    def run_for_new(self, new_row_function: Callable) -> DevPolicyRow:
        self.dialog.set_title(_("Create New Device Assignment"))
        self.devident_label.set_text("No device selected.")
        self._init_check(self.readonly_check, False, False, "not selected")
        self._init_check(self.permissive_check, False, False, "not selected")
        self._init_check(self.no_strict_check, False, False, "not selected")
        self._init_check(self.port_check, False, False, "not selected")

        self.unknown_box.set_visible(False)
        self.qube_handler.reset()
        self.validate()

        new_row = super().run_for_new(new_row_function)
        return new_row

    def run_for_existing(self, row: DevPolicyRow):
        self.dialog.set_title(_("Edit Device Assignment"))
        # load data
        self.dev_modeler.select_value(row.assignment_wrapper.device)

        self.no_strict_check.set_active(row.assignment_wrapper.no_strict_reset)
        self.permissive_check.set_active(row.assignment_wrapper.permissive)
        self.readonly_check.set_active(row.assignment_wrapper.read_only)
        self.port_check.set_active(row.assignment_wrapper.port_required)
        # fill qubes
        self.qube_handler.reset()
        for qube in row.assignment_wrapper.frontends:
            self.qube_handler.add_selected_vm(qube)

        if row.assignment_wrapper.device.device.is_device_id_set:
            self.unknown_box.set_visible(False)
        else:
            self.unknown_box.set_visible(True)

        super().run_for_existing(row)


class DeviceManager:
    """A helper class to keep the system state in, to avoid re-querying
    qubesd regularly"""

    def __init__(self, qapp: qubesadmin.Qubes):
        self.qapp = qapp

        self.all_devices: List[DeviceInfo] = []
        self.assignments: List[Tuple[DeviceAssignment, qubesadmin.vm.QubesVM]] = []

    def load_data(self):
        """Load system state"""
        self.all_devices.clear()
        self.assignments.clear()

        for vm in self.qapp.domains:
            for devclass in DEVICE_CLASSES:
                for dev in vm.devices[devclass].get_exposed_devices():
                    self.all_devices.append(dev)
                for ass in vm.devices[devclass].get_assigned_devices():
                    self.assignments.append((ass, vm))

    def get_available_devices(self, dev_classes: List[str]) -> Iterator[DeviceInfo]:
        """Get all available devices of listed classes"""
        for dev in self.all_devices:
            if dev.devclass in dev_classes:
                yield dev

    def get_assignments(
        self, dev_classes: List[str]
    ) -> Iterator[Tuple[DeviceAssignment, qubesadmin.vm.QubesVM]]:
        """Get all available assignments of listed classes"""
        for assignment, vm in self.assignments:
            if assignment.devclass in dev_classes:
                yield assignment, vm

    def get_denied(
        self,
    ) -> Iterator[tuple[qubesadmin.vm.QubesVM, list[DeviceInterface]]]:
        """Get all device interface blocks"""
        for vm in self.qapp.domains:
            if getattr(vm, "devices_denied", None):
                yield vm, DeviceInterface.from_str_bulk(vm.devices_denied)


class DeviceWrapper:
    """A convenience wrapper for any object that might represent what is
    being connected to VMs. Can be an existing device, a virtual device or a
    port."""

    def __init__(self, devclass: str, backend_domain: Optional[qubesadmin.vm.QubesVM]):
        # a bare-bones device object, ready to be filled with data
        self.device: Optional[DeviceInfo] = None
        self.devclass: str = devclass
        self.device_id: str = ""

        # shortest possible identifier
        self.port_id: str = ""
        # identifier to be used in dropdowns etc.
        self.long_name: str = ""

        # domain
        self.backend_domain = backend_domain

        # Description of the port
        self.port: Optional[Port] = None

    @property
    def identity_description(self) -> str:
        if not self.device:
            return _("Unknown device")
        result = _("Device name: ") + self.device.description + "\n"
        result += (
            _("Type: ")
            + ", ".join(interface.category.name for interface in self.device.interfaces)
            + "\n"
        )
        result += _("Vendor: ") + self.device.vendor + "\n"
        result += _("Serial number: ") + self.device.serial
        return result

    @classmethod
    def new_from_device_info(cls, device_info: DeviceInfo):
        dw = cls(device_info.devclass, device_info.backend_domain)
        dw.device = device_info
        dw.device_id = device_info.device_id

        dw.port_id = str(device_info.port)
        dw.long_name = device_info.description

        dw.port = device_info.port
        return dw

    def __eq__(self, other):
        return self.device == getattr(other, "device", None)


class AssignmentWrapper:
    """
    A set of assignments with the same device, port_id, assignment mode and
    options.
    """

    def __init__(self, device: DeviceWrapper):
        self.changed = False
        self.assignments: List[DeviceAssignment] = []

        # the variables below represent the state as displayed to a user;
        # it might be different than current system state if the user made
        # some changes and did not yet apply them
        self.device: DeviceWrapper = device

        self.frontends: List[qubesadmin.vm.QubesVM] = []
        self.mode: AssignmentMode = AssignmentMode.REQUIRED

        self.port_required: bool = True
        self.device_identity_required: bool = True
        self.no_strict_reset = False
        self.permissive = False
        self.read_only = False
        self.valid = True  # does this set of assignments have any weirdness
        # we can't handle?

        self.port: Optional[Port] = None

    @classmethod
    def new_from_existing(cls, assignments: List[DeviceAssignment]):
        """Create new AssignmentWrapper from a list of DeviceAssignments;
        this assumes the DeviceAssignments are appropriately grouped"""
        device = assignments[0].device
        wrapped_device = DeviceWrapper.new_from_device_info(device_info=device)

        aw = cls(wrapped_device)
        aw.assignments = assignments

        for ass in aw.assignments:
            aw.frontends.append(ass.frontend_domain)

        aw.mode = aw.assignments[0].mode
        aw.device_identity_required = aw.assignments[0].device_id != "*"
        aw.port_required = aw.assignments[0].port_id != "*"
        aw.port = aw.assignments[0].port
        if not aw.device_identity_required and not aw.port_required:
            aw.valid = False

        # make absolutely sure there is no tomfoolery in options (should be handled by
        # load_current_state, this is a just-in-case
        for assignment in aw.assignments:
            assert assignment.options == aw.assignments[0].options

        aw.no_strict_reset = (
            aw.assignments[0].options.get("no-strict-reset", "") == "True"
        )
        aw.permissive = aw.assignments[0].options.get("permissive", "") == "True"
        aw.read_only = aw.assignments[0].options.get("read-only", "") == "True"

        for opt in aw.assignments[0].options:
            if opt not in ("permissive", "no-strict-reset", "read-only"):
                aw.valid = False
        return aw

    def device_identity_description(self):
        """Nicely readable device identity description"""
        if self.device_identity_required:
            return self.device.identity_description
        return ""

    def __str__(self):
        return (
            self.device_description()
            + " "
            + self.action_description()
            + " "
            + ", ".join([vm.name for vm in self.frontends])
        )

    def action_description(self) -> str:
        """Description of associated action"""
        if self.mode == AssignmentMode.AUTO:
            return _("will attach automatically to")
        if self.mode == AssignmentMode.REQUIRED:
            return _("is required by ")
        return _("will ask to be attached to")

    def device_description(self):
        """
        Description of the assignment row, for use in the List of rows
        """
        if not self.device_identity_required:
            # we are at port
            return _("Any {} device attached to <b>{}</b> ").format(
                self.device.devclass, str(self.port)
            )
        # device ID required
        if self.port_required:
            return "<b>({}) {}</b> ".format(
                str(self.device.port_id), self.device.long_name
            )

        return "<b>({}) {}</b> ".format(
            self.device.backend_domain, self.device.long_name
        )

    def remove(self):
        """
        Remove the current assignment from the system.
        ."""
        for assignment in self.assignments:
            assignment.frontend_domain.devices[assignment.devclass].unassign(assignment)

    def save(self):
        """
        Save all assignment changes via removing old assignments and
        creating them again.
        """
        if not self.changed:
            return
        if self.assignments:
            options = self.assignments[0].options.copy()
            # options we handle
            if "no-strict-reset" in options:
                del options["no-strict-reset"]
            if "permissive" in options:
                del options["permissive"]
        else:
            options = {}

        self.remove()
        self.assignments.clear()

        device = self.device.device

        if not device:
            raise ValueError("Device not found")

        if not self.device_identity_required:
            device = device.clone(device_id="*")
        if not self.port_required:
            device = device.clone(
                port=Port(device.backend_domain, "*", device.devclass)
            )
        if self.mode == AssignmentMode.AUTO:
            mode = "auto-attach"
        elif self.mode == AssignmentMode.ASK:
            mode = "ask-to-attach"
        elif self.mode == AssignmentMode.REQUIRED:
            mode = "required"
        else:
            raise ValueError("Assignment mode unknown")

        if self.no_strict_reset:
            options["no-strict-reset"] = "True"
        if self.permissive:
            options["permissive"] = "True"
        if self.read_only:
            options["read-only"] = "True"

        for vm in self.frontends:
            new_assignment = DeviceAssignment(device=device, mode=mode, options=options)
            vm.devices[device.devclass].assign(new_assignment)
            self.assignments.append(new_assignment)

        self.changed = False


class AttachmentDescriptionRow(DevPolicyRow):
    """A ListBoxRow describing an existing assignment rule"""

    def __init__(self, assignment_wrapper: AssignmentWrapper, qapp: qubesadmin.Qubes):
        super().__init__()
        self.assignment_wrapper = assignment_wrapper
        self.valid = assignment_wrapper.valid
        self.qapp = qapp

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_box.set_homogeneous(True)
        self.main_box.set_spacing(5)

        self.add(self.main_box)

        self.dev_box = Gtk.Box()
        self.dev_label = Gtk.Label()
        self.dev_label.set_max_width_chars(100)
        self.dev_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.dev_box.add(self.dev_label)

        self.dev_label.set_halign(Gtk.Align.START)
        self.dev_label.set_valign(Gtk.Align.START)

        self.action_label = Gtk.Label()
        self.action_label.set_halign(Gtk.Align.CENTER)
        self.action_label.set_valign(Gtk.Align.START)

        self.main_box.pack_start(self.dev_box, True, True, 0)
        self.main_box.pack_start(self.action_label, True, True, 0)

        self.vm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.vm_box.set_halign(Gtk.Align.START)
        self.main_box.pack_start(self.vm_box, True, True, 0)

        self.update()

    def validate(self, row_collection) -> bool:
        for row in row_collection:
            if row == self:
                continue
            if (
                row.assignment_wrapper.device_description()
                == self.assignment_wrapper.device_description()
            ):
                for vm in self.assignment_wrapper.frontends:
                    if vm in row.assignment_wrapper.frontends:
                        return False
        return True

    def update(self):
        """Update row display."""
        self.dev_label.set_markup(self.assignment_wrapper.device_description())
        self.action_label.set_markup(self.assignment_wrapper.action_description())

        for child in self.vm_box.get_children():
            self.vm_box.remove(child)

        self.valid = True
        self.set_tooltip_text("")
        for vm in self.assignment_wrapper.frontends:
            self.vm_box.add(TokenName(vm.name, self.qapp))
            if vm.klass == "AdminVM":
                self.valid = False
                self.set_tooltip_text(_("This rule cannot be edited with GUI tools."))

        self.show_all()

    def save(self):
        """
        Save row changes, if any.
        """
        if not self.changed:
            return
        self.assignment_wrapper.save()
        super().save()

    def remove_self(self):
        """
        Remove all assignments associated with this row.
        """
        self.assignment_wrapper.remove()

    def __str__(self):
        """
        Used in descriptions of unsaved changes.
        """
        return str(self.assignment_wrapper)


class AttachmentHandler(DevicePolicyHandler):
    def __init__(
        self,
        builder: Gtk.Builder,
        qapp: qubesadmin.Qubes,
        prefix: str,
        device_policy_manager: DeviceManager,
        classes: list[str],
        assignment_filter: Callable,
        edit_dialog_class,
    ):
        """
        Handler for device attachments
        :param builder: Gtk.Builder
        :param qapp: Qubes object
        :param prefix: prefix for objects from builder
        :param device_policy_manager: DeviceManager
        :param classes: list of device classes to be included
        :param assignment_filter: function to filter assignments that make sense for
        this handler; should take an Assignment and return True/False
        :param edit_dialog_class: class of the editing dialog
        """
        self.classes = classes
        self.assignment_filter = assignment_filter
        super().__init__(
            prefix=prefix,
            builder=builder,
            qapp=qapp,
            device_policy_manager=device_policy_manager,
            edit_dialog_class=edit_dialog_class,
        )

    def get_edit_dialog(self, builder) -> DevPolicyDialogHandler:
        return self.edit_dialog_class(
            builder=builder,
            qapp=self.qapp,
            parent_window=self.main_window,
            device_manager=self.device_policy_manager,
        )

    def create_new_row(self) -> AttachmentDescriptionRow:
        blank_device = DeviceWrapper("new", None)
        assignment_wrapper = AssignmentWrapper(blank_device)
        new_row = AttachmentDescriptionRow(assignment_wrapper, self.qapp)
        return new_row

    @staticmethod
    def assignment_id(device_assignment: DeviceAssignment):
        """Unique identifier of a device_assignment, consists of a device id,
        port id and options."""
        return (
            device_assignment.device_id,
            device_assignment.port_id,
            str(device_assignment.options),
        )

    def load_current_state(self):
        """Load system state"""
        assignments: dict[tuple[str, str, str], list[DeviceAssignment]] = {}
        for assignment, _ in self.device_policy_manager.get_assignments(self.classes):
            if not self.assignment_filter(assignment):
                continue
            assignment_id = self.assignment_id(assignment)
            assignments.setdefault(assignment_id, []).append(assignment)

        for assignment_id, assignment_list in assignments.items():
            aw = AssignmentWrapper.new_from_existing(assignment_list)
            row = AttachmentDescriptionRow(aw, self.qapp)
            self.rule_list.add(row)

        self.rule_list.show_all()


class DevAttachmentHandler(PageHandler):
    """Handler for all the disparate Dev attachment functions."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
    ):
        self.qapp = qapp
        self.device_manager = DeviceManager(self.qapp)
        self.device_manager.load_data()

        self.main_window = gtk_builder.get_object("main_window")

        self.dev_block_handler = DeviceBlockHandler(
            qapp, gtk_builder, self.device_manager
        )
        self.auto_attach_handler = AttachmentHandler(
            builder=gtk_builder,
            qapp=qapp,
            prefix="devices_auto",
            device_policy_manager=self.device_manager,
            classes=["block", "mic", "usb"],
            assignment_filter=self._filter_required,
            edit_dialog_class=AutoDeviceDialog,
        )
        self.required_devices_handler = AttachmentHandler(
            builder=gtk_builder,
            qapp=qapp,
            prefix="devices_required",
            device_policy_manager=self.device_manager,
            classes=["block", "pci"],
            assignment_filter=self._filter_auto,
            edit_dialog_class=RequiredDeviceDialog,
        )

        self.lists = [
            self.dev_block_handler.rule_list,
            self.auto_attach_handler.rule_list,
            self.required_devices_handler.rule_list,
        ]

        for widget in self.lists:
            widget.connect("row-selected", self._select_one)
            widget.connect("rules-changed", self.validate_all_rows)

    @staticmethod
    def _filter_required(assignment: DeviceAssignment) -> bool:
        return assignment.mode == AssignmentMode.REQUIRED

    @staticmethod
    def _filter_auto(assignment: DeviceAssignment) -> bool:
        return assignment.mode in [AssignmentMode.AUTO, AssignmentMode.ASK]

    def _select_one(self, selected_widget: Gtk.ListBox, selected_row, *_args):
        if not selected_row:
            return
        for widget in self.lists:
            if widget != selected_widget:
                widget.select_row(None)

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = [
            self.dev_block_handler.get_unsaved(),
            self.auto_attach_handler.get_unsaved(),
            self.required_devices_handler.get_unsaved(),
        ]
        return "\n".join([x for x in unsaved if x])

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        self.dev_block_handler.reset()
        self.auto_attach_handler.reset()
        self.required_devices_handler.reset()

    def validate_all_rows(self, *_args):
        errors = []
        all_rows = (
            self.auto_attach_handler.rule_list.get_children()
            + self.required_devices_handler.rule_list.get_children()
        )
        for row in all_rows:
            if not row.validate(all_rows):
                errors.append(row)
                row.get_style_context().add_class("error_row")
            else:
                row.get_style_context().remove_class("error_row")

        if errors:
            show_error(
                self.main_window,
                _("Duplicate rules"),
                _(
                    "Duplicate device rules were found. Those rules cannot be "
                    "all present in a system; only the last one will be saved. "
                ),
            )

    def save(self):
        """Save current rules, whatever they are - custom or default."""
        # pretty ugly solution to duplicate rule, but eh...
        self.dev_block_handler.save()
        self.auto_attach_handler.save()
        self.required_devices_handler.save()
        self.device_manager.load_data()
