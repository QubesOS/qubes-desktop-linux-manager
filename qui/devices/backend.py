# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023 Marta Marczykowska-Górecka
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
from typing import Set, Dict, Optional, List

import qubesadmin
import qubesadmin.exc
import qubesadmin.devices
import qubesadmin.vm
from qubesadmin.utils import size_to_human
from qubesadmin.device_protocol import DeviceAssignment, DeviceCategory

import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, Gio  # isort:skip

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

FEATURE_HIDE_CHILDREN = "device-hide-children"
FEATURE_ATTACH_WITH_MIC = "device-attach-with-mic"


class VM:
    """
    Wrapper for various VMs that can serve as backend/frontend
    """

    def __init__(self, vm: qubesadmin.vm.QubesVM):
        self.__hash = hash(vm)
        self._vm = vm
        self.name = vm.name
        self.vm_class = vm.klass

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return self.__hash

    @property
    def icon_name(self):
        """Name of the VM icon"""
        try:
            return getattr(self._vm, "icon", self._vm.label.icon)
        except qubesadmin.exc.QubesException:
            return "appvm-black"

    @property
    def is_dispvm_template(self) -> bool:
        """
        Is this VM a dispvm template?
        """
        return getattr(self._vm, "template_for_dispvms", False)

    @property
    def is_attachable(self) -> bool:
        """
        Should this VM be listed as possible attachment target in the GUI?
        """
        return self.vm_class != "AdminVM" and self._vm.is_running()

    @property
    def vm_object(self):
        """
        Get the qubesadmin.vm.QubesVM object.
        """
        return self._vm

    @property
    def should_be_cleaned_up(self):
        """
        VMs that should have the "shut me down when detaching device" option
        """
        return getattr(self._vm, "auto_cleanup", False)

    def toggle_feature_value(self, feature_name, value):
        """
        If provided value is part of a comma-separated list in feature_name, remove it.
        If it is not, add it.
        """
        feature = self._vm.features.get(feature_name, "")
        all_devs: List[str] = [f for f in feature.split(" ") if f]

        if value in all_devs:
            all_devs.remove(value)
        else:
            all_devs.append(value)

        new_feature = " ".join(all_devs)
        self._vm.features[feature_name] = new_feature


class Device:
    @classmethod
    def id_from_device(cls, dev: qubesadmin.devices.DeviceInfo) -> str:
        return str(dev.port) + ":" + str(dev.device_id)

    def __init__(self, dev: qubesadmin.devices.DeviceInfo, gtk_app: Gtk.Application):
        self.gtk_app: Gtk.Application = gtk_app
        self._dev: qubesadmin.devices.DeviceInfo = dev
        self.__hash = hash(dev)
        self._port: str = str(dev.port)
        # Monotonic connection timestamp only for new devices
        self.connection_timestamp: float = None

        self._dev_name: str = getattr(dev, "description", "unknown")
        if dev.devclass == "block" and "size" in dev.data:
            self._dev_name += " (" + size_to_human(int(dev.data["size"])) + ")"

        self._ident: str = getattr(dev, "port_id", "unknown")
        self._description: str = getattr(dev, "description", "unknown")
        self._devclass: str = getattr(dev, "devclass", "unknown")

        main_category = None
        for interface in dev.interfaces:
            if interface.category.name != "Other":
                main_category = interface.category
                break
        else:
            main_category = DeviceCategory.Other

        self._category: DeviceCategory = main_category

        self._data: Dict = getattr(dev, "data", {})
        self._device_id = getattr(dev, "device_id", "*")
        self.parent = str(getattr(dev, "parent_device", None) or "")
        self.attachments: Set[VM] = set()
        self.assignments: Set[VM] = set()
        backend_domain = getattr(dev, "backend_domain", None)
        if backend_domain:
            self._backend_domain: Optional[VM] = VM(backend_domain)
        else:
            self._backend_domain: Optional[VM] = None

        try:
            self.vm_icon: str = getattr(
                dev.backend_domain, "icon", dev.backend_domain.label.icon
            )
        except qubesadmin.exc.QubesException:
            self.vm_icon: str = "appvm-black"
        self._full_id = self.id_from_device(dev)

        self.devices_to_attach_with_me: List[Device] = []
        self.has_children: bool = False
        self.show_children: bool = True
        self.hide_this_device: bool = False

    def __str__(self):
        return self._dev_name

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return self.__hash

    @property
    def name(self) -> str:
        """VM name"""
        return self._dev_name

    @property
    def id_string(self) -> str:
        """Unique id string"""
        return self._full_id

    @property
    def description(self) -> str:
        """Device description."""
        return self._description

    @property
    def port(self) -> str:
        """Port to which the device is connected"""
        return self._port

    @property
    def device_class(self) -> str:
        """Device class"""
        return self._devclass

    @property
    def device_icon(self) -> str:
        """Device icon"""
        match self._category:
            case DeviceCategory.Network:
                return "network"
            case DeviceCategory.Keyboard:
                return "keyboard"
            case DeviceCategory.Mouse:
                return "mouse"
            case DeviceCategory.Input:
                return "keyboard"
            case DeviceCategory.Printer:
                return "printer"
            case DeviceCategory.Camera:
                return "camera"
            case DeviceCategory.Audio:
                return "audio"
            case DeviceCategory.Microphone:
                return "mic"
            case DeviceCategory.USB_Storage:
                return "harddrive"
            case DeviceCategory.Block_Storage:
                return "harddrive"
            case DeviceCategory.Storage:
                return "harddrive"
            case DeviceCategory.Bluetooth:
                return "bluetooth"
        return ""

    @property
    def backend_domain(self) -> Optional[VM]:
        """VM that exposes this device"""
        return self._backend_domain

    @property
    def frontend_domain(self) -> Set[VM]:
        """All vms the device is attached to"""
        return self.attachments

    @property
    def notification_id(self) -> str:
        """Notification id for notifications related to this device."""
        return str(self.backend_domain) + self._ident

    @property
    def device_group(self) -> str:
        """Device group for purposes of menus."""
        return str(self._category.name).replace("_", " ")

    @property
    def sorting_key(self) -> str:
        """Key used for sorting devices in menus"""
        return self.device_group + self._devclass + self.name

    def attach_to_vm(self, vm: VM, with_aux_devices: bool = True):
        """
        Perform attachment to provided VM. If with_aux_devices is False,
        ignore devices_to_attach_with_me
        """
        try:
            assignment = DeviceAssignment.new(
                self.backend_domain,
                port_id=self._ident,
                devclass=self.device_class,
                device_id=self._device_id,
            )
            vm.vm_object.devices[self.device_class].attach(assignment)
            self.gtk_app.emit_notification(
                _("Attaching device"),
                _("Attaching {} to {}").format(self.description, vm),
                Gio.NotificationPriority.NORMAL,
                notification_id=self.notification_id,
            )
            if self.devices_to_attach_with_me and with_aux_devices:
                for device in self.devices_to_attach_with_me:
                    if device is self:
                        # this should never happen, but....
                        continue
                    device.detach_from_all()
                    device.attach_to_vm(vm, with_aux_devices=False)

        except Exception as ex:  # pylint: disable=broad-except
            self.gtk_app.emit_notification(
                _("Error"),
                _("Attaching device {0} to {1} failed. Error: {2} - {3}").format(
                    self.description, vm, type(ex).__name__, ex
                ),
                Gio.NotificationPriority.HIGH,
                error=True,
                notification_id=self.notification_id,
            )

    def detach_from_vm(self, vm: VM, with_aux_devices: bool = True):
        """
        Detach device from listed VM. If with_aux_devices is False,
        ignore devices_to_attach_with_me.
        """
        self.gtk_app.emit_notification(
            _("Detaching device"),
            _("Detaching {} from {}").format(self.description, vm),
            Gio.NotificationPriority.NORMAL,
            notification_id=self.notification_id,
        )
        try:
            assignment = DeviceAssignment.new(
                self.backend_domain, self._ident, self.device_class
            )
            vm.vm_object.devices[self.device_class].detach(assignment)
            if self.devices_to_attach_with_me and with_aux_devices:
                for device in self.devices_to_attach_with_me:
                    if device is self:
                        # this should never happen, but....
                        continue
                    device.detach_from_all(with_aux_devices=False)
        except qubesadmin.exc.QubesException as ex:
            self.gtk_app.emit_notification(
                _("Error"),
                _("Detaching device {0} from {1} failed. Error: {2}").format(
                    self.description, vm, ex
                ),
                Gio.NotificationPriority.HIGH,
                error=True,
                notification_id=self.notification_id,
            )

    def detach_from_all(self, with_aux_devices: bool = True):
        """
        Detach from all VMs. If with_aux_devices is False,
        ignore devices_to_attach_with_me.
        """
        for vm in self.attachments:
            self.detach_from_vm(vm, with_aux_devices)
