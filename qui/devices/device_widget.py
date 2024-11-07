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
from typing import Set, List, Dict
import asyncio
import sys
import time

import importlib.resources

import qubesadmin
import qubesadmin.exc
import qubesadmin.events
import qubesadmin.tests
import qubesadmin.tests.mock_app

import qui
import qui.utils

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Gdk, Gio  # isort:skip

from qui.devices import backend
from qui.devices import actionable_widgets

from qubes_config.widgets.gtk_utils import is_theme_light

import gbulb
gbulb.install()

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


# FUTURE: this should be moved to backend with new API changes
DEV_TYPES = ['block', 'usb', 'mic']


class DeviceMenu(Gtk.Menu):
    """Menu for handling a single device"""
    def __init__(self, main_item: actionable_widgets.MainDeviceWidget,
                 vms: List[backend.VM],
                 dispvm_templates: List[backend.VM]):
        super().__init__()

        for child_widget in main_item.get_child_widgets(vms, dispvm_templates):
            item = actionable_widgets.generate_wrapper_widget(
                Gtk.MenuItem, 'activate', child_widget)
            self.add(item)

        self.show_all()


class DevicesTray(Gtk.Application):
    """Tray application for handling devices."""
    def __init__(self, app_name, qapp, dispatcher):
        super().__init__()
        self.name: str = app_name

        # maps: port to connected device (e.g., sys-usb:sda -> block device)
        self.devices: Dict[str, backend.Device] = {}
        self.vms: Set[backend.VM] = set()
        self.dispvm_templates: Set[backend.VM] = set()

        self.dispatcher: qubesadmin.events.EventsDispatcher = dispatcher
        self.qapp: qubesadmin.Qubes = qapp

        self.set_application_id(self.name)
        self.register()  # register Gtk Application

        self.initialize_vm_data()
        self.initialize_dev_data()

        for devclass in DEV_TYPES:
            self.dispatcher.add_handler('device-attach:' + devclass,
                                        self.device_attached)
            self.dispatcher.add_handler('device-detach:' + devclass,
                                        self.device_detached)
            self.dispatcher.add_handler('device-list-change:' + devclass,
                                        self.device_list_update)

        self.dispatcher.add_handler('domain-shutdown',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start', self.vm_start)

        self.dispatcher.add_handler('property-set:template_for_dispvms',
                                    self.vm_dispvm_template_change)

        self.dispatcher.add_handler('property-reset:template_for_dispvms',
                                    self.vm_dispvm_template_change)
        self.dispatcher.add_handler('property-del:template_for_dispvms',
                                    self.vm_dispvm_template_change)

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name('qubes-devices')
        self.widget_icon.connect('button-press-event', self.show_menu)
        self.widget_icon.set_tooltip_markup(
            '<b>Qubes Devices</b>\nView and manage devices.')

    def device_list_update(self, vm, _event, **_kwargs):

        changed_devices: Dict[str, backend.Device] = {}

        # create list of all current devices from the changed VM
        try:
            for devclass in DEV_TYPES:
                for device in vm.devices[devclass]:
                    changed_devices[str(device.port)] = backend.Device(
                        device, self)

        except qubesadmin.exc.QubesException:
            changed_devices = {}  # VM was removed

        for dev_port, dev in changed_devices.items():
            if dev_port not in self.devices:
                dev.connection_timestamp = time.monotonic()
                self.devices[dev_port] = dev
                self.emit_notification(
                    _("Device available"),
                    _("Device {} is available.").format(dev.description),
                    Gio.NotificationPriority.NORMAL,
                    notification_id=dev.notification_id)

        dev_to_remove = []
        for dev_port, dev in self.devices.items():
            if dev.backend_domain != vm:
                continue
            if dev_port not in changed_devices:
                dev_to_remove.append((dev_port, dev))

        for dev_port, dev in dev_to_remove:
            self.emit_notification(
                _("Device removed"),
                _("Device {} has been removed.").format(dev.description),
                Gio.NotificationPriority.NORMAL,
                notification_id=dev.notification_id)
            del self.devices[dev_port]

    def initialize_vm_data(self):
        for vm in self.qapp.domains:
            wrapped_vm = backend.VM(vm)
            try:
                if wrapped_vm.is_attachable:
                    self.vms.add(wrapped_vm)
                if wrapped_vm.is_dispvm_template:
                    self.dispvm_templates.add(wrapped_vm)
            except qubesadmin.exc.QubesException:
                # we don't have access to VM state
                pass

    def initialize_dev_data(self):
        # list all devices
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                try:
                    for device in domain.devices[devclass]:
                        self.devices[str(device.port)] = backend.Device(
                            device, self)
                except qubesadmin.exc.QubesException:
                    # we have no permission to access VM's devices
                    continue

        # list existing device attachments
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                try:
                    for device in domain.devices[devclass
                            ].get_attached_devices():
                        dev = str(device.port)
                        if dev in self.devices:
                            # occassionally ghost UnknownDevices appear when a
                            # device was removed but not detached from a VM
                            # FUTURE: is this still true after api changes?
                            self.devices[dev].attachments.add(
                                backend.VM(domain))
                except qubesadmin.exc.QubesException:
                    # we have no permission to access VM's devices
                    continue

    def device_attached(self, vm, _event, device, **_kwargs):
        try:
            if not vm.is_running() or device.devclass not in DEV_TYPES:
                return
        except qubesadmin.exc.QubesPropertyAccessError:
            # we don't have access to VM state
            return

        if str(device.port) not in self.devices:
            self.devices[str(device.port)] = backend.Device(device, self)

        vm_wrapped = backend.VM(vm)

        self.devices[str(device.port)].attachments.add(vm_wrapped)

    def device_detached(self, vm, _event, port, **_kwargs):
        try:
            if not vm.is_running():
                return
        except qubesadmin.exc.QubesPropertyAccessError:
            # we don't have access to VM state
            return

        port = str(port)
        vm_wrapped = backend.VM(vm)

        if port in self.devices:
            self.devices[port].attachments.discard(vm_wrapped)

    def vm_start(self, vm, _event, **_kwargs):
        wrapped_vm = backend.VM(vm)
        if wrapped_vm.is_attachable:
            self.vms.add(wrapped_vm)

        for devclass in DEV_TYPES:
            try:
                for device in vm.devices[devclass].get_attached_devices():
                    dev = str(device.port)
                    if dev in self.devices:
                        self.devices[dev].attachments.add(wrapped_vm)
            except qubesadmin.exc.QubesDaemonAccessError:
                # we don't have access to devices
                return

    def vm_shutdown(self, vm, _event, **_kwargs):
        wrapped_vm = backend.VM(vm)
        self.vms.discard(wrapped_vm)
        self.dispvm_templates.discard(wrapped_vm)

        for dev in self.devices.values():
            dev.attachments.discard(wrapped_vm)

    def vm_dispvm_template_change(self, vm, _event, **_kwargs):
        """Is template for dispvms property changed"""
        wrapped_vm = backend.VM(vm)
        if wrapped_vm.is_dispvm_template:
            self.dispvm_templates.add(wrapped_vm)
        else:
            self.dispvm_templates.discard(wrapped_vm)
    #
    # def on_label_changed(self, vm, _event, **_kwargs):
    #     if not vm:  # global properties changed
    #         return
    #     try:
    #         name = vm.name
    #     except qubesadmin.exc.QubesPropertyAccessError:
    #         return  # the VM was deleted before its status could be updated
    #     for domain in self.vms:
    #         if str(domain) == name:
    #             try:
    #                 domain.icon = vm.label.icon
    #             except qubesadmin.exc.QubesPropertyAccessError:
    #                 domain.icon = 'appvm-block'
    #
    #     for device in self.devices.values():
    #         if device.backend_domain == name:
    #             try:
    #                 device.vm_icon = vm.label.icon
    #             except qubesadmin.exc.QubesPropertyAccessError:
    #                 device.vm_icon = 'appvm-black'

    @staticmethod
    def load_css(widget) -> str:
        """Load appropriate css. This should be called whenever menu is shown,
        because it needs a realized widget.
        Returns light/dark variant used currently as 'light' or 'dark' string.
        """
        theme = 'light' if is_theme_light(widget) else 'dark'
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        css_file_ref = (importlib.resources.files('qui') /
                        f'qubes-devices-{theme}.css')
        with importlib.resources.as_file(css_file_ref) as css_file:
            provider.load_from_path(str(css_file))

        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        return theme

    def show_menu(self, _unused, _event):
        """Show menu at mouse pointer."""
        tray_menu = Gtk.Menu()
        theme = self.load_css(tray_menu)
        tray_menu.set_reserve_toggle_size(False)

        # create menu items
        menu_items = []
        sorted_vms = sorted(self.vms)
        sorted_dispvms = sorted(self.dispvm_templates)
        sorted_devices = sorted(self.devices.values(),
                                key=lambda x: x.sorting_key)

        for i, dev in enumerate(sorted_devices):
            if i == 0 or dev.device_group != sorted_devices[i - 1].device_group:
                # add a header
                menu_item = \
                    actionable_widgets.generate_wrapper_widget(
                        Gtk.MenuItem,
                        'activate',
                        actionable_widgets.InfoHeader(dev.device_group))
                menu_items.append(menu_item)

            device_widget = actionable_widgets.MainDeviceWidget(dev, theme)
            device_item = \
                actionable_widgets.generate_wrapper_widget(
                    Gtk.MenuItem, 'activate', device_widget)
            device_item.set_reserve_indicator(False)

            device_menu = DeviceMenu(device_widget, sorted_vms, sorted_dispvms)
            device_menu.set_reserve_toggle_size(False)
            device_item.set_submenu(device_menu)

            menu_items.append(device_item)

        for item in menu_items:
            tray_menu.add(item)

        tray_menu.show_all()
        tray_menu.popup_at_pointer(None)  # use current event

    def emit_notification(self, title, message, priority, error=False,
                          notification_id=None):
        notification = Gio.Notification.new(title)
        notification.set_body(message)
        notification.set_priority(priority)
        if error:
            notification.set_icon(Gio.ThemedIcon.new('dialog-error'))
            if notification_id:
                notification_id += 'ERROR'
        self.send_notification(notification_id, notification)


def main():
    qapp = qubesadmin.Qubes()
    # qapp = qubesadmin.tests.mock_app.MockQubesComplete()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    # dispatcher = qubesadmin.tests.mock_app.MockDispatcher(qapp)
    app = DevicesTray(
        'org.qubes.qui.tray.Devices', qapp, dispatcher)

    loop = asyncio.get_event_loop()
    return_code = qui.utils.run_asyncio_and_show_errors(
        loop, [asyncio.ensure_future(dispatcher.listen_for_events())],
    "Qubes Devices Widget")
    del app
    return return_code


if __name__ == '__main__':
    sys.exit(main())
