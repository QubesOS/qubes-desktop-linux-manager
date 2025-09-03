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

# Must be imported before creating threads
from ..tray.gtk3_xwayland_menu_dismisser import (
    get_fullscreen_window_hack,
)  # isort:skip

from typing import Set, List, Dict, Optional
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

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, Gdk, Gio  # isort:skip

try:
    from gi.events import GLibEventLoopPolicy

    asyncio.set_event_loop_policy(GLibEventLoopPolicy())
except ImportError:
    import gbulb

    gbulb.install()

from qui.devices import backend
from qui.devices import actionable_widgets

from qubes_config.widgets.gtk_utils import is_theme_light

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


# FUTURE: this should be moved to backend with new API changes
DEV_TYPES = ["block", "usb", "mic"]


class DeviceMenu(Gtk.Menu):
    """Menu for handling a single device"""

    def __init__(
        self,
        main_item: actionable_widgets.MainDeviceWidget,
        vms: List[backend.VM],
        dispvm_templates: List[backend.VM],
    ):
        super().__init__()

        for child_widget in main_item.get_child_widgets(vms, dispvm_templates):
            child_item = actionable_widgets.generate_wrapper_widget(
                Gtk.MenuItem, "activate", child_widget
            )
            if hasattr(child_widget, "get_child_widgets"):
                submenu = Gtk.Menu()
                submenu.set_reserve_toggle_size(False)

                for menu_item_widget in child_widget.get_child_widgets():
                    menu_item = actionable_widgets.generate_wrapper_widget(
                        Gtk.MenuItem, "activate", menu_item_widget
                    )
                    submenu.add(menu_item)
                submenu.show_all()
                child_item.set_submenu(submenu)
            self.add(child_item)

        self.show_all()


class DevicesTray(Gtk.Application):
    """Tray application for handling devices."""

    def __init__(self, app_name, qapp, dispatcher):
        super().__init__()
        self.fullscreen_window_hack = get_fullscreen_window_hack()
        self.name: str = app_name

        # maps: port to connected device (e.g., sys-usb:sda -> block device)
        self.devices: Dict[str, backend.Device] = {}
        self.vms: Set[backend.VM] = set()
        self.dispvm_templates: Set[backend.VM] = set()
        self.parent_ports_to_hide = []
        self.active_usbvms: Set[backend.VM] = set()
        self.dormant_usbvms: Set[backend.VM] = set()
        self.dev_update_queue: Set = set()
        self.vm_update_queue: Set = set()

        self.dispatcher: qubesadmin.events.EventsDispatcher = dispatcher
        self.qapp: qubesadmin.Qubes = qapp

        self.set_application_id(self.name)
        self.register()  # register Gtk Application

        self.initialize_vm_data()
        self.initialize_dev_data()
        self.initialize_features()

        for devclass in DEV_TYPES:
            self.dispatcher.add_handler(
                "device-attach:" + devclass, self.device_attached
            )
            self.dispatcher.add_handler(
                "device-detach:" + devclass, self.device_detached
            )
            self.dispatcher.add_handler("device-added:" + devclass, self.device_added)
            self.dispatcher.add_handler(
                "device-removed:" + devclass, self.device_removed
            )
            self.dispatcher.add_handler(
                "device-assign:" + devclass, self.device_assigned
            )
            self.dispatcher.add_handler(
                "device-unassign:" + devclass, self.device_unassigned
            )

        self.dispatcher.add_handler("device-assign:pci", self.pci_action)
        self.dispatcher.add_handler("device-unassign:pci", self.pci_action)
        self.dispatcher.add_handler("domain-pre-delete", self.remove_domain_item)

        self.dispatcher.add_handler("domain-shutdown", self.vm_shutdown)
        self.dispatcher.add_handler("domain-start-failed", self.vm_shutdown)
        self.dispatcher.add_handler("domain-start", self.vm_start)
        self.dispatcher.add_handler("domain-unpaused", self.vm_unpaused)

        self.dispatcher.add_handler(
            "property-set:template_for_dispvms", self.vm_dispvm_template_change
        )

        self.dispatcher.add_handler(
            "property-reset:template_for_dispvms",
            self.vm_dispvm_template_change,
        )
        self.dispatcher.add_handler(
            "property-del:template_for_dispvms", self.vm_dispvm_template_change
        )

        self.dispatcher.add_handler(
            "domain-feature-set:internal", self.update_internal_feature
        )
        self.dispatcher.add_handler(
            "domain-feature-delete:internal", self.update_internal_feature
        )

        for feature in [backend.FEATURE_HIDE_CHILDREN, backend.FEATURE_ATTACH_WITH_MIC]:

            self.dispatcher.add_handler(
                f"domain-feature-set:{feature}", self.update_single_feature
            )
            self.dispatcher.add_handler(
                f"domain-feature-delete:{feature}", self.update_single_feature
            )

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name("qubes-devices")
        self.widget_icon.connect("button-press-event", self.show_menu)
        self.widget_icon.set_tooltip_markup(
            "<b>Qubes Devices</b>\nView and manage devices."
        )

    def _update_queue(self, vm, device, device_class):
        """Handle certain operations that should not be done too often."""
        # update children
        if vm not in self.vm_update_queue:
            self.vm_update_queue.add(vm)
            asyncio.create_task(self.update_parents(vm))
        if device not in self.dev_update_queue:
            self.dev_update_queue.add(device)
            asyncio.create_task(self.update_assignments(device_class))

    async def update_assignments(self, dev_class):
        """Scan vm list for new assignments"""
        await asyncio.sleep(0.3)

        if not self.dev_update_queue:
            return
        devs = self.dev_update_queue.copy()
        self.dev_update_queue.clear()

        for domain in self.qapp.domains:
            try:
                for device in domain.devices[dev_class].get_attached_devices():
                    dev = backend.Device.id_from_device(device)
                    if dev in devs and dev in self.devices:
                        self.devices[dev].attachments.add(backend.VM(domain))

                for device in domain.devices[dev_class].get_assigned_devices():
                    dev = backend.Device.id_from_device(device)
                    if dev in devs and dev in self.devices:
                        self.devices[dev].assignments.add(backend.VM(domain))
            except qubesadmin.exc.QubesException:
                # we have no permission to access VM's devices
                continue

    async def update_parents(self, vm):
        await asyncio.sleep(0.3)

        if vm not in self.vm_update_queue:
            return
        self.vm_update_queue.remove(vm)

        self.update_single_feature(
            None,
            None,
            backend.FEATURE_HIDE_CHILDREN,
            value=vm.features.get(backend.FEATURE_HIDE_CHILDREN, ""),
            oldvalue="",
        )

    def initialize_vm_data(self):
        for vm in self.qapp.domains:
            wrapped_vm = backend.VM(vm)
            try:
                if not vm.features.get("internal"):
                    if wrapped_vm.is_attachable:
                        self.vms.add(wrapped_vm)
                    if wrapped_vm.is_dispvm_template:
                        self.dispvm_templates.add(wrapped_vm)
                # Keep track of USBVMs
                if wrapped_vm.is_usbvm:
                    if vm.is_running():
                        self.active_usbvms.add(wrapped_vm)
                    else:
                        self.dormant_usbvms.add(wrapped_vm)
            except qubesadmin.exc.QubesException:
                # we don't have access to VM state
                pass

    def device_added(self, vm, _event, device):
        dev_id = backend.Device.id_from_device(device)
        dev = backend.Device(device, self)
        dev.connection_timestamp = time.monotonic()
        self.devices[dev_id] = dev

        if dev.parent:
            for potential_parent in self.devices.values():
                if potential_parent.port == dev.parent:
                    potential_parent.has_children = True
                    break

        # connect with mic
        mic_feature = vm.features.get(backend.FEATURE_ATTACH_WITH_MIC, "").split(" ")
        if dev_id in mic_feature:
            microphone = self.devices.get("dom0:mic:dom0:mic::m000000", None)
            microphone.devices_to_attach_with_me.append(dev)
            dev.devices_to_attach_with_me = [microphone]

        self.emit_notification(
            _("Device available"),
            _("Device {} is available.").format(dev.description),
            Gio.NotificationPriority.NORMAL,
            notification_id=dev.notification_id,
        )

        self._update_queue(vm, dev_id, dev.device_class)

    def device_removed(self, vm, _event, port):
        for potential_dev_id, potential_dev in self.devices.items():
            if (
                potential_dev.backend_domain.name != vm.name
                or potential_dev.port != str(port)
            ):
                continue
            dev, dev_id = potential_dev, potential_dev_id
            break
        else:
            # we never knew the device anyway
            return

        microphone = self.devices.get("dom0:mic:dom0:mic::m000000", None)

        self.emit_notification(
            _("Device removed"),
            _("Device {} has been removed.").format(dev.description),
            Gio.NotificationPriority.NORMAL,
            notification_id=dev.notification_id,
        )
        if dev in microphone.devices_to_attach_with_me:
            microphone.devices_to_attach_with_me.remove(dev)
        if dev.port in self.parent_ports_to_hide:
            self.parent_ports_to_hide.remove(dev.port)
        del self.devices[dev_id]

    def initialize_dev_data(self):
        # list all devices
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                try:
                    for device in domain.devices[devclass]:
                        dev_id = backend.Device.id_from_device(device)
                        self.devices[dev_id] = backend.Device(device, self)
                except qubesadmin.exc.QubesException:
                    # we have no permission to access VM's devices
                    continue

        # list children devices
        for device in self.devices.values():
            if device.parent:
                for potential_parent in self.devices.values():
                    if potential_parent.port == device.parent:
                        potential_parent.has_children = True

        # list existing device attachments and assignments
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                try:
                    for device in domain.devices[devclass].get_attached_devices():
                        dev = backend.Device.id_from_device(device)
                        if dev in self.devices:
                            # occassionally ghost UnknownDevices appear when a
                            # device was removed but not detached from a VM
                            # FUTURE: is this still true after api changes?
                            self.devices[dev].attachments.add(backend.VM(domain))

                    for device in domain.devices[devclass].get_assigned_devices():
                        dev = backend.Device.id_from_device(device)
                        if dev in self.devices:
                            self.devices[dev].assignments.add(backend.VM(domain))
                except qubesadmin.exc.QubesException:
                    # we have no permission to access VM's devices
                    continue

    def device_assigned(self, vm, _event, device, **_kwargs):
        dev_id = backend.Device.id_from_device(device)
        if dev_id not in self.devices:
            return
        self.devices[dev_id].assignments.add(backend.VM(vm))

    def device_unassigned(self, vm, _event, device, **_kwargs):
        dev_id = backend.Device.id_from_device(device)
        if dev_id not in self.devices:
            return
        try:
            self.devices[dev_id].assignments.remove(backend.VM(vm))
        except KeyError:
            # it's ok, somehow we got an unassign for a device we didn't store as
            # assigned. Cheers!
            return

    def pci_action(self, vm, _event, **_kwargs):
        # We assume PCI controllers could be assigned only when qube is shutdown
        wrapped_vm = backend.VM(vm)
        if wrapped_vm.is_usbvm:
            if wrapped_vm not in self.dormant_usbvms:
                self.dormant_usbvms.add(wrapped_vm)
        elif wrapped_vm in self.dormant_usbvms:
            self.dormant_usbvms.discard(wrapped_vm)

    def remove_domain_item(self, _submitter, _event, vm, **_kwargs):
        # In a perfect world, core should trigger `device-unassign:pci` event
        # for PCI devices attached to an HVM before actually removing it and
        # this method should not be necessary. But we are not certain :/
        for wrapped_vm in self.dormant_usbvms:
            if wrapped_vm.name == vm:
                self.dormant_usbvms.discard(wrapped_vm)
                break

    def update_single_feature(self, _vm, _event, feature, value=None, oldvalue=None):
        if not value:
            new = set()
        else:
            new = set(value.split(" "))
        if not oldvalue:
            old = set()
        else:
            old = set(oldvalue.split(" "))

        add = new - old
        remove = old - new

        microphone = self.devices.get("dom0:mic:dom0:mic::m000000", None)

        for dev_name in remove:
            if feature == backend.FEATURE_ATTACH_WITH_MIC:
                dev = self.devices.get(dev_name, None)
                if dev:
                    dev.devices_to_attach_with_me = []
                    if dev in microphone.devices_to_attach_with_me:
                        microphone.devices_to_attach_with_me.remove(dev)
            if feature == backend.FEATURE_HIDE_CHILDREN:
                dev = self.devices.get(dev_name, None)
                if dev and dev.port in self.parent_ports_to_hide:
                    dev.show_children = True
                    self.parent_ports_to_hide.remove(dev.port)
                    self.hide_child_devices(dev.port, True)

        for dev_name in add:
            if feature == backend.FEATURE_ATTACH_WITH_MIC and microphone:
                dev = self.devices.get(dev_name, None)
                if dev:
                    dev.devices_to_attach_with_me = [microphone]
                    microphone.devices_to_attach_with_me.append(dev)
            if feature == backend.FEATURE_HIDE_CHILDREN:
                dev = self.devices.get(dev_name, None)
                if dev:
                    dev.show_children = False
                    self.parent_ports_to_hide.append(dev.port)
                    self.hide_child_devices(dev.port, False)

    def vm_unpaused(self, vm, _event, **_kwargs):
        wrapped_vm = backend.VM(vm)
        try:
            attachable = wrapped_vm.is_attachable
            internal = vm.features.get("internal")
        except qubesadmin.exc.QubesException:
            attachable, internal = False, False
        if attachable and not internal:
            self.vms.add(wrapped_vm)

    def update_internal_feature(
        self, vm, _event, feature, value=None, oldvalue=None
    ):  # pylint: disable=unused-argument
        if bool(value) == bool(oldvalue):
            return
        wrapped_vm = backend.VM(vm)
        if not value:
            self.vms.discard(wrapped_vm)
            self.dispvm_templates.discard(wrapped_vm)
            return
        try:
            attachable = wrapped_vm.is_attachable
            dispvm_template = wrapped_vm.is_dispvm_template
        except qubesadmin.exc.QubesException:
            attachable, dispvm_template = False, False
        if attachable:
            self.vms.add(wrapped_vm)
        if dispvm_template:
            self.dispvm_templates.add(wrapped_vm)

    def initialize_features(self, *_args, **_kwargs):
        """
        Initialize all feature-related states
        :return:
        """
        domains = self.qapp.domains

        microphone = self.devices.get("dom0:mic:dom0:mic::m000000", None)
        # clear existing feature mappings
        for dev in self.devices.values():
            dev.devices_to_attach_with_me = []
            dev.hide_this_device = False
            dev.show_children = True

        mic_dev_strings = []
        if microphone:
            for domain in domains:
                mic_feature = domain.features.get(
                    backend.FEATURE_ATTACH_WITH_MIC, False
                )
                if isinstance(mic_feature, str):
                    mic_dev_strings.extend(
                        [dev for dev in mic_feature.split(" ") if dev]
                    )

            microphone.devices_to_attach_with_me = []

            for dev in mic_dev_strings:
                if dev in self.devices:
                    self.devices[dev].devices_to_attach_with_me = [microphone]
                    microphone.devices_to_attach_with_me.append(self.devices[dev])

        self.parent_ports_to_hide = []
        parent_ids_to_hide = []
        for domain in domains:
            children_feature = domain.features.get(backend.FEATURE_HIDE_CHILDREN, False)
            if isinstance(children_feature, str):
                parent_ids_to_hide.extend([s for s in children_feature.split(" ") if s])

        for dev in self.devices.values():
            if dev.id_string in parent_ids_to_hide:
                self.parent_ports_to_hide.append(dev.port)
                dev.show_children = False

        self.hide_child_devices()

    def hide_child_devices(
        self, parent_port: Optional[str] = None, state: bool = False
    ):
        """Hide (if state=False) or show (if state=True) all children of the device
        with provided parent_port, or all devices
        whose parents are in self.parent_ports_to_hide"""
        if not parent_port:
            for port in self.parent_ports_to_hide:
                self.hide_child_devices(port, state)

        for device in self.devices.values():
            if str(device.parent) == parent_port:
                device.hide_this_device = not state
                self.hide_child_devices(str(device.port), state)

    def device_attached(self, vm, _event, device, **_kwargs):
        try:
            if not vm.is_running() or device.devclass not in DEV_TYPES:
                return
        except qubesadmin.exc.QubesPropertyAccessError:
            # we don't have access to VM state
            return

        dev_id = backend.Device.id_from_device(device)
        if dev_id not in self.devices:
            self.devices[dev_id] = backend.Device(device, self)

        vm_wrapped = backend.VM(vm)

        self.devices[dev_id].attachments.add(vm_wrapped)

    def device_detached(self, vm, _event, port, **_kwargs):
        try:
            if not vm.is_running():
                return
        except qubesadmin.exc.QubesPropertyAccessError:
            # we don't have access to VM state
            return

        port = str(port)
        vm_wrapped = backend.VM(vm)

        for device in self.devices.values():
            if device.port == port:
                device.attachments.discard(vm_wrapped)

    def vm_start(self, vm, _event, **_kwargs):
        wrapped_vm = backend.VM(vm)
        try:
            internal = vm.features.get("internal")
            attachable = wrapped_vm.is_attachable
        except qubesadmin.exc.QubesException:
            internal, attachable = False, False
        if attachable and not internal:
            self.vms.add(wrapped_vm)
        if wrapped_vm in self.dormant_usbvms:
            self.dormant_usbvms.discard(wrapped_vm)
            self.active_usbvms.add(wrapped_vm)

        for devclass in DEV_TYPES:
            try:
                for device in vm.devices[devclass].get_attached_devices():
                    dev_id = backend.Device.id_from_device(device)
                    if dev_id in self.devices:
                        self.devices[dev_id].attachments.add(wrapped_vm)
            except qubesadmin.exc.QubesDaemonAccessError:
                # we don't have access to devices
                return

    def vm_shutdown(self, vm, _event, **_kwargs):
        wrapped_vm = backend.VM(vm)
        if wrapped_vm in self.active_usbvms:
            self.active_usbvms.discard(wrapped_vm)
            self.dormant_usbvms.add(wrapped_vm)

        self.vms.discard(wrapped_vm)
        self.dispvm_templates.discard(wrapped_vm)

        devs_to_remove = []
        for dev in self.devices.values():
            if dev.backend_domain == wrapped_vm:
                devs_to_remove.append(dev.port)
                continue
            dev.attachments.discard(wrapped_vm)
        for dev_port in devs_to_remove:
            self.device_removed(vm, None, port=dev_port)

    def vm_dispvm_template_change(self, vm, _event, **_kwargs):
        """Is template for dispvms property changed"""
        wrapped_vm = backend.VM(vm)
        try:
            internal = vm.features.get("internal")
            dispvm_template = wrapped_vm.is_dispvm_template
        except qubesadmin.exc.QubesException:
            internal, dispvm_template = False, False
        if dispvm_template and not internal:
            self.dispvm_templates.add(wrapped_vm)
        else:
            self.dispvm_templates.discard(wrapped_vm)

    @staticmethod
    def load_css(widget) -> str:
        """Load appropriate css. This should be called whenever menu is shown,
        because it needs a realized widget.
        Returns light/dark variant used currently as 'light' or 'dark' string.
        """
        theme = "light" if is_theme_light(widget) else "dark"
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        css_file_ref = importlib.resources.files("qui") / f"qubes-devices-{theme}.css"
        with importlib.resources.as_file(css_file_ref) as css_file:
            provider.load_from_path(str(css_file))

        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        return theme

    def show_menu(self, _unused, _event):
        """Show menu at mouse pointer."""
        tray_menu = Gtk.Menu()
        self.fullscreen_window_hack.show_for_widget(tray_menu)
        theme = self.load_css(tray_menu)
        tray_menu.set_reserve_toggle_size(False)

        # create menu items
        menu_items = []
        sorted_vms = sorted(self.vms)
        sorted_dispvms = sorted(self.dispvm_templates)
        sorted_devices = sorted(
            [dev for dev in self.devices.values() if not dev.hide_this_device],
            key=lambda x: x.sorting_key,
        )

        for i, dev in enumerate(sorted_devices):
            if i == 0 or dev.device_group != sorted_devices[i - 1].device_group:
                # add a header
                menu_item = actionable_widgets.generate_wrapper_widget(
                    Gtk.MenuItem,
                    "activate",
                    actionable_widgets.InfoHeader(dev.device_group),
                )
                menu_items.append(menu_item)

            device_widget = actionable_widgets.MainDeviceWidget(dev, theme)
            device_item = actionable_widgets.generate_wrapper_widget(
                Gtk.MenuItem, "activate", device_widget
            )
            device_item.set_reserve_indicator(False)

            device_menu = DeviceMenu(device_widget, sorted_vms, sorted_dispvms)
            device_menu.set_reserve_toggle_size(False)
            device_item.set_submenu(device_menu)

            menu_items.append(device_item)

        for wrapped_vm in self.dormant_usbvms:
            usbvm_item = actionable_widgets.generate_wrapper_widget(
                Gtk.MenuItem,
                "activate",
                actionable_widgets.StartUSBVM(wrapped_vm, theme),
            )
            menu_items.append(usbvm_item)

        for item in menu_items:
            tray_menu.add(item)

        tray_menu.show_all()
        tray_menu.popup_at_pointer(None)  # use current event

    def emit_notification(
        self, title, message, priority, error=False, notification_id=None
    ):
        notification = Gio.Notification.new(title)
        notification.set_body(message)
        notification.set_priority(priority)
        if error:
            notification.set_icon(Gio.ThemedIcon.new("dialog-error"))
            if notification_id:
                notification_id += "ERROR"
        self.send_notification(notification_id, notification)


def main():
    qapp = qubesadmin.Qubes()
    # qapp = qubesadmin.tests.mock_app.MockQubesComplete()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    # dispatcher = qubesadmin.tests.mock_app.MockDispatcher(qapp)
    app = DevicesTray("org.qubes.qui.tray.Devices", qapp, dispatcher)

    loop = asyncio.get_event_loop()
    return_code = qui.utils.run_asyncio_and_show_errors(
        loop,
        [asyncio.ensure_future(dispatcher.listen_for_events())],
        "Qubes Devices Widget",
    )
    del app
    return return_code


if __name__ == "__main__":
    sys.exit(main())
