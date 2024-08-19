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
from typing import Set, Dict, Optional

import qubesadmin
import qubesadmin.exc
import qubesadmin.devices
import qubesadmin.vm
from qubesadmin.utils import size_to_human
from qubesadmin.device_protocol import (Port, VirtualDevice, DeviceInfo,
                                        DeviceAssignment)

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Gio  # isort:skip

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


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
            return getattr(self._vm, 'icon', self._vm.label.icon)
        except qubesadmin.exc.QubesException:
            return 'appvm-black'

    @property
    def is_dispvm_template(self) -> bool:
        """
        Is this VM a dispvm template?
        """
        return getattr(self._vm, 'template_for_dispvms', False)

    @property
    def is_attachable(self) -> bool:
        """
        Should this VM be listed as possible attachment target in the GUI?
        """
        return self.vm_class != 'AdminVM' and self._vm.is_running()

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


class Device:
    def __init__(self, dev: qubesadmin.devices.DeviceInfo,
                 gtk_app: Gtk.Application):
        self.gtk_app: Gtk.Application = gtk_app
        self._dev: qubesadmin.devices.DeviceInfo = dev
        self.__hash = hash(dev)
        self._port: str = ''
        # Monotonic connection timestamp only for new devices
        self.connection_timestamp: float = None

        self._dev_name: str = getattr(dev, 'description', 'unknown')
        if dev.devclass == 'block' and 'size' in dev.data:
            self._dev_name += " (" + size_to_human(int(dev.data['size'])) + ")"

        self._ident: str = getattr(dev, 'port_id', 'unknown')
        self._description: str = getattr(dev, 'description', 'unknown')
        self._devclass: str = getattr(dev, 'devclass', 'unknown')
        self._data: Dict = getattr(dev, 'data', {})
        self._device_id = getattr(dev, 'device_id', '*')
        self.attachments: Set[VM] = set()
        backend_domain = getattr(dev, 'backend_domain', None)
        if backend_domain:
            self._backend_domain: Optional[VM] = VM(backend_domain)
        else:
            self._backend_domain: Optional[VM] = None

        try:
            self.vm_icon: str = getattr(dev.backend_domain, 'icon',
                                   dev.backend_domain.label.icon)
        except qubesadmin.exc.QubesException:
            self.vm_icon: str = 'appvm-black'

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
        return self._ident

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
        if self.device_class == 'block':
            return 'harddrive'
        if self.device_class == 'mic':
            return 'mic'
        return ''

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
        if self._devclass == 'block':
            return 'Data (Block) Devices'
        if self._devclass == 'usb':
            return 'USB Devices'
        if self._devclass == 'mic':
            return 'Microphones'
        # TODO: those below come from new API, may need an update
        if self._devclass == 'Other':
            return 'Other Devices'
        if self._devclass == 'Communication':
            return 'Other Devices'  # eg. modems
        if self._devclass in ('Input', 'Keyboard', 'Mouse'):
            return 'Input Devices'
        if self._devclass in ('Printer', 'Scanner'):
            return "Printers and Scanners"
        if self._devclass == 'Multimedia':
            return 'Other Devices'
            # Multimedia = Audio, Video, Displays etc.
        if self._devclass == 'Wireless':
            return 'Other Devices'
        if self._devclass == 'Bluetooth':
            return 'Bluetooth Devices'
        if self._devclass == 'Mass_Data':
            return 'Other Devices'
        if self._devclass == 'Network':
            return 'Other Devices'
        if self._devclass == 'Memory':
            return 'Other Devices'
        if self._devclass.startswith('PCI'):
            return 'PCI Devices'
        if self._devclass == 'Docking Station':
            return 'Docking Station'
        if self._devclass == 'Processor':
            return 'Other Devices'
        return 'Other Devices'

    @property
    def sorting_key(self) -> str:
        """Key used for sorting devices in menus"""
        return self.device_group + self._devclass + self.name

    def attach_to_vm(self, vm: VM):
        """
        Perform attachment to provided VM.
        """
        try:
            assignment = DeviceAssignment(VirtualDevice(Port(
                self.backend_domain, self.id_string, self.device_class),
                device_id=self._device_id))

            vm.vm_object.devices[self.device_class].attach(assignment)
            self.gtk_app.emit_notification(
                _("Attaching device"),
                _("Attaching {} to {}").format(self.description, vm),
                Gio.NotificationPriority.NORMAL,
                notification_id=self.notification_id)

        except Exception as ex: # pylint: disable=broad-except
            self.gtk_app.emit_notification(
                _("Error"),
                _("Attaching device {0} to {1} failed. "
                  "Error: {2} - {3}").format(
                    self.description, vm, type(ex).__name__,
                    ex),
                Gio.NotificationPriority.HIGH,
                error=True,
                notification_id=self.notification_id)

    def detach_from_vm(self, vm: VM):
        """
        Detach device from listed VM.
        """
        self.gtk_app.emit_notification(
            _("Detaching device"),
            _("Detaching {} from {}").format(self.description, vm),
            Gio.NotificationPriority.NORMAL,
            notification_id=self.notification_id)
        try:
            assignment = DeviceAssignment(VirtualDevice(Port(
                self.backend_domain, self._ident, self.device_class)))
            vm.vm_object.devices[self.device_class].detach(assignment)
        except qubesadmin.exc.QubesException as ex:
            self.gtk_app.emit_notification(
                _("Error"),
                _("Detaching device {0} from {1} failed. "
                  "Error: {2}").format(self.description, vm, ex),
                Gio.NotificationPriority.HIGH,
                error=True,
                notification_id=self.notification_id)

    def detach_from_all(self):
        """
        Detach from all VMs
        """
        for vm in self.attachments:
            self.detach_from_vm(vm)
