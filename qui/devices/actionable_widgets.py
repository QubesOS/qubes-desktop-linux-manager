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
"""
Generic widgets handling devices. Made in a way that makes them easy to pack in
other widgets, e.g. MenuItems and ListRows.

Use generate_wrapper_widget to get a wrapped widget.
"""
import asyncio
import functools
import pathlib
from typing import Iterable, Callable, Optional, List

import qubesadmin
import qubesadmin.devices
import qubesadmin.vm

import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, GdkPixbuf, GLib  # isort:skip

from . import backend
import time


def load_icon(icon_name: str, backup_name: str, size: int = 24):
    """Load icon from provided name/path, if available. If not, load backup
    icon. If icon not found in any of the above ways, load a blank icon of
    specified size.
    Returns GdkPixbuf.Pixbuf.
    Size must be in pixels.

    To enable local testing, there is a fallback that tries to load icons from
    local directory.
    """
    try:
        image: GdkPixbuf.Pixbuf = Gtk.IconTheme.get_default().load_icon(
            icon_name, size, 0
        )
        return image
    except (TypeError, GLib.Error):
        try:
            image: GdkPixbuf.Pixbuf = Gtk.IconTheme.get_default().load_icon(
                backup_name, size, 0
            )
            return image
        except (TypeError, GLib.Error):
            try:
                # this is a workaround in case we are running this locally
                icon_path = (
                    str(pathlib.Path().resolve())
                    + "/icons/scalable/"
                    + icon_name
                    + ".svg"
                )
                return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, size, size)
            except (GLib.Error, TypeError):
                # we are giving up and just using a blank icon
                pixbuf: GdkPixbuf.Pixbuf = GdkPixbuf.Pixbuf.new(
                    GdkPixbuf.Colorspace.RGB, True, 8, size, size
                )
                pixbuf.fill(0x000)
                return pixbuf


class ActionableWidget:
    """abstract class to be used in various clickable items in menus and
    list items"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # should this widget be sensitive?
        self.actionable: bool = True

    async def widget_action(self, *_args):
        """What should happen when this widget is activated/clicked"""


### ICONS
class VariantIcon(Gtk.Image):
    def __init__(self, icon_name, initial_variant: str, size: int):
        """
        Initialize a new icon that has a light and dark variants.
        :param icon_name: base name of the icon, e.g. 'key'
        :param initial_variant: initial variant, one of 'light' and 'dark'
        :param size: icon size
        """
        super().__init__()

        self.light_icon = load_icon(icon_name + "-light", icon_name, size)
        self.dark_icon = load_icon(icon_name + "-dark", icon_name, size)

        if initial_variant == "light":
            self.set_from_pixbuf(self.light_icon)
            self.is_light = True
        else:
            self.set_from_pixbuf(self.dark_icon)
            self.is_light = False

    def toggle_icon(self):
        if self.is_light:
            self.set_from_pixbuf(self.dark_icon)
            self.is_light = False
        else:
            self.set_from_pixbuf(self.light_icon)
            self.is_light = True


class VMWithIcon(Gtk.Box):
    def __init__(
        self,
        vm: backend.VM,
        size: int = 18,
        variant: str = "dark",
        name: Optional[str] = None,
    ):
        """
        Icon with VM name or optional other text in parentheses.
        :param vm: VM object
        :param size: icon size
        :param variant: light / dark string
        :param name: optional text to put instead of vm name
        after colon
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.backend_icon = VariantIcon(vm.icon_name, variant, size)

        self.backend_label = Gtk.Label(xalign=0)
        backend_label: str = name or vm.name
        self.backend_label.set_markup(backend_label)

        self.pack_start(self.backend_icon, False, False, 4)
        self.pack_start(self.backend_label, False, False, 0)

        self.get_style_context().add_class("vm_item")


class VMInfoBox(Gtk.Box):
    """
    Information about device.
    For all devices, it has:
        Device attachment scheme, in the following form:
        backend_vm (device name) [-> frontend_vm[, other_frontend+]]
    If relevant, also:
        - information that the device attaches with microphone
        - information that the device is a child of another device
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        backend_vm = device.backend_domain
        frontend_vms = list(device.attachments)
        # backend is always there
        backend_vm_icon = VMWithIcon(backend_vm, name=device.port)
        backend_vm_icon.get_style_context().add_class("main_device_vm")
        self.pack_start(backend_vm_icon, False, False, 4)

        if frontend_vms:
            # arrow
            self.arrow = VariantIcon("arrow", variant, 15)
            self.pack_start(self.arrow, False, False, 4)

            for vm in frontend_vms:
                # vm
                # potential topic to explore: commas
                vm_name = VMWithIcon(vm)
                vm_name.get_style_context().add_class("main_device_vm")

                self.pack_start(vm_name, False, False, 4)


#### Non-interactive items


class InfoHeader(Gtk.Label, ActionableWidget):
    """
    Simple header with a bolded name, left-aligned.
    """

    def __init__(self, text):
        super().__init__()
        self.set_text(text)
        self.get_style_context().add_class("device_header")
        self.get_style_context().add_class("main_device_item")
        self.set_halign(Gtk.Align.START)
        self.actionable = False


class SeparatorItem(Gtk.Separator, ActionableWidget):
    """Separator item"""

    def __init__(self):
        super().__init__()
        self.actionable = False
        self.get_style_context().add_class("separator_item")


#### Attach/detach action items


class SimpleActionWidget(Gtk.Box):
    def __init__(self, icon_name, text, variant: str = "dark"):
        """Widget with an action and an icon."""
        super().__init__()
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.icon = VariantIcon(icon_name, variant, 24)
        self.text_label = Gtk.Label()
        self.text_label.set_line_wrap_mode(Gtk.WrapMode.WORD)
        self.text_label.set_markup(text)
        self.text_label.set_xalign(0)
        self.get_style_context().add_class("vm_item")

        self.pack_start(self.icon, False, False, 5)
        self.pack_start(self.text_label, True, True, 0)


class AttachWidget(ActionableWidget, VMWithIcon):
    """Attach device to qube action"""

    def __init__(self, vm: backend.VM, device: backend.Device):
        super().__init__(vm)
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        self.device.attach_to_vm(self.vm)


class DetachWidget(ActionableWidget, SimpleActionWidget):
    """Detach device from a VM"""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        super().__init__("detach", "<b>Detach from " + vm.name + "</b>", variant)
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        self.device.detach_from_vm(self.vm, False)


class DetachWithWidget(ActionableWidget, SimpleActionWidget):
    """Detach device from a VM with another device"""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        second_device_names = ", ".join(
            [dev.name for dev in device.devices_to_attach_with_me]
        )
        super().__init__(
            "detach",
            "<b>Detach from " + vm.name + " with " + second_device_names + "</b>",
            variant,
        )
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        self.device.detach_from_vm(self.vm, True)


class DetachAndShutdownWidget(ActionableWidget, SimpleActionWidget):
    """Detach device from a disposable VM and shut it down."""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        super().__init__(
            "detach", "<b>Detach and shut down " + vm.name + "</b>", variant
        )
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        self.device.detach_from_vm(self.vm, True)
        self.vm.vm_object.shutdown()


class DetachAndAttachWidget(ActionableWidget, VMWithIcon):
    """Detach device from current attachment(s) and attach to another"""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        super().__init__(vm, variant=variant)
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        for vm in self.device.attachments:
            self.device.detach_from_vm(vm, True)
        self.device.attach_to_vm(self.vm)


class AttachDisposableWidget(ActionableWidget, VMWithIcon):
    """Attach to a new disposable qube"""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        super().__init__(vm, variant=variant)
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        new_dispvm = qubesadmin.vm.DispVM.from_appvm(self.vm.vm_object.app, self.vm)
        new_dispvm.start()

        self.device.attach_to_vm(backend.VM(new_dispvm))


class DetachAndAttachDisposableWidget(ActionableWidget, VMWithIcon):
    """Detach from all current attachments and attach to new disposable"""

    def __init__(self, vm: backend.VM, device: backend.Device, variant: str = "dark"):
        super().__init__(vm, variant=variant)
        self.vm = vm
        self.device = device

    async def widget_action(self, *_args):
        self.device.detach_from_vm(self.vm)
        new_dispvm = qubesadmin.vm.DispVM.from_appvm(self.vm.vm_object.app, self.vm)
        new_dispvm.start()

        self.device.attach_to_vm(backend.VM(new_dispvm))


class ToggleFeatureItem(ActionableWidget, SimpleActionWidget):
    def __init__(
        self, icon_name, text, state, device, feature_name, variant: str = "dark"
    ):
        """
        Widget representing a toggleable feature.
        :param icon_name: name of the 'on' icon
        :param text: text on the widget
        :param state: whether the item is toggled or not toggled
        :param device: Device object
        :param feature_name: name of the feature
        :param variant: color variant
        """
        super().__init__(icon_name if state else "", text, variant)
        self.device = device
        self.feature_name = feature_name

    async def widget_action(self, *_args):
        """Toggle the state of the feature: either add the device ID to it or remove
        it."""
        self.device.backend_domain.toggle_feature_value(
            self.feature_name, str(self.device.id_string)
        )


#### Configuration-related actions


class DeviceSettingsWidget(ActionableWidget, SimpleActionWidget):
    """
    Not yet implemented.
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__("settings", "<b>Device settings</b>", variant)
        self.variant = variant
        self.device = device

    def get_child_widgets(self):
        if self.device.device_group == "Camera":
            yield ToggleFeatureItem(
                "check",
                "Attach with Microphone",
                bool(self.device.devices_to_attach_with_me),
                self.device,
                backend.FEATURE_ATTACH_WITH_MIC,
                self.variant,
            )

        if self.device.has_children:
            yield ToggleFeatureItem(
                "check",
                "Show child devices",
                self.device.show_children,
                self.device,
                backend.FEATURE_HIDE_CHILDREN,
                self.variant,
            )

        gaw_item = GlobalAttachmentWidget(self.device, self.variant)
        yield gaw_item

    def toggle_feature(self, feature_name, *_args):
        feature = self.device.backend_domain.features.get(feature_name, "")
        all_devs: List[str] = feature.split(" ")

        if self.device.id_string in all_devs:
            all_devs.remove(self.device.id_string)
        else:
            all_devs.append(self.device.id_string)

        new_feature = " ".join(all_devs)
        self.device.backend_domain.features[feature_name] = new_feature

    async def widget_action(self, *_args):
        """No-op, only shows child item."""


class GlobalAttachmentWidget(ActionableWidget, SimpleActionWidget):
    """
    Open Global Config at Device Attachments
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__("settings", "<b>Auto Attach Settings...</b>", variant)
        self.device = device

    async def widget_action(self, *_args):
        await asyncio.create_subprocess_exec("qubes-global-config", "-o", "attachments")


class GlobalSettingsWidget(ActionableWidget, SimpleActionWidget):
    """
    Not yet implemented.
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__("settings", "<b>Global device settings</b>", variant)
        self.device = device

    async def widget_action(self, *_args):
        await asyncio.create_subprocess_exec("qubes-global-config", "-o", "attachments")


class HelpWidget(ActionableWidget, SimpleActionWidget):
    """
    Not yet implemented.
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__("question-icon", "<b>Help</b>", variant)
        self.device = device

    async def widget_action(self, *_args):
        pass


#### Device info widget


class DeviceHeaderWidget(Gtk.Box, ActionableWidget):
    def __init__(self, device: backend.Device, variant: str = "dark"):
        """General information about the device - name, in the future also
        a button to rename the device."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.device_label = Gtk.Label()
        self.device_label.set_markup(device.name)
        self.device_label.get_style_context().add_class("device_name")
        self.device_label.set_xalign(Gtk.Align.CENTER)
        self.device_label.set_halign(Gtk.Align.CENTER)

        self.diagram = VMInfoBox(device, variant)
        self.diagram.set_halign(Gtk.Align.CENTER)

        self.add(self.device_label)
        self.add(self.diagram)

        if device.parent:
            parent_label = Gtk.Label()
            parent_label.set_halign(Gtk.Align.CENTER)
            parent_label.set_markup(
                "This device is a child of <b>" + str(device.parent) + "</b>"
            )
            self.add(parent_label)

        if device.devices_to_attach_with_me:
            mic_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            mic_label = Gtk.Label()
            mic_label.set_markup("This device will attach with microphone")
            mic_box.add(mic_label)
            mic_img = VariantIcon("mic", variant, 18)
            mic_box.add(mic_img)
            mic_box.set_halign(Gtk.Align.CENTER)
            self.add(mic_box)

        self.actionable = False


class MainDeviceWidget(ActionableWidget, Gtk.Grid):
    """
    This is the widget that should live in the complete devices list and points
    to other widgets.
    Widget is a grid, filled in the following way:
    | dev_icon |                device_name            |
    |          | backend_vm | (arrow) | frontend_vm[s] |
    """

    def __init__(self, device: backend.Device, variant: str = "dark"):
        super().__init__()
        self.device = device
        self.variant = variant

        # add NEW! label for new devices for 10 minutes on 1st view
        self._new_device_label_timout = 10 * 60
        # reduce NEW! label timeout to 2 minutes after 1st view
        self._new_device_label_afterview = 2 * 60

        self.get_style_context().add_class("main_device_item")

        # the part that is common to all devices

        self.device_icon = VariantIcon(device.device_icon, variant, 20)
        self.device_icon.set_valign(Gtk.Align.CENTER)

        self.device_label = Gtk.Label(xalign=0)

        label_markup = device.name
        if (
            device.connection_timestamp
            and int(time.monotonic() - device.connection_timestamp) < 120
        ):
            label_markup += ' <span foreground="#63a0ff"><b>NEW</b></span>'
        self.device_label.set_markup(label_markup)

        if self.device.attachments:
            self.device_label.get_style_context().add_class("dev_attached")

        self.device_label.get_style_context().add_class("main_device_label")

        self.attach(self.device_icon, 0, 0, 1, 1)
        self.attach(self.device_label, 1, 0, 3, 1)

        self.vm_diagram = VMInfoBox(device, self.variant)
        self.attach(self.vm_diagram, 1, 1, 3, 1)

    def get_child_widgets(self, vms, disp_vm_templates) -> Iterable[ActionableWidget]:
        """
        Get type-appropriate list of child widgets.
        :return: iterable of ActionableWidgets, ready to be packed in somewhere
        """

        attached_vms = [vm for vm in vms if vm in self.device.attachments]
        assigned_vms = [
            vm
            for vm in vms
            if vm in self.device.assignments and vm not in self.device.attachments
        ]
        other_vms = [
            vm
            for vm in vms
            if vm not in self.device.attachments and vm not in self.device.assignments
        ]

        # all devices have a header
        yield DeviceHeaderWidget(self.device, self.variant)
        yield SeparatorItem()

        # if attached
        if attached_vms:
            for vm in attached_vms:
                yield DetachWidget(vm, self.device, self.variant)
                if vm.should_be_cleaned_up:
                    yield DetachAndShutdownWidget(vm, self.device, self.variant)
                if self.device.devices_to_attach_with_me:
                    yield DetachWithWidget(vm, self.device, self.variant)
            yield SeparatorItem()

            if assigned_vms:
                yield InfoHeader("Detach and attach to preferred qube:")
                for vm in assigned_vms:
                    yield DetachAndAttachWidget(vm, self.device, self.variant)

            yield InfoHeader("Detach and attach to other qube:")

            for vm in other_vms:
                yield DetachAndAttachWidget(vm, self.device, self.variant)

            yield SeparatorItem()

            yield InfoHeader("Detach and attach to new disposable qube:")

            for vm in disp_vm_templates:
                yield DetachAndAttachDisposableWidget(vm, self.device, self.variant)

        else:
            if assigned_vms:
                yield InfoHeader("Attach to preferred qube:")
                for vm in assigned_vms:
                    yield AttachWidget(vm, self.device)

            yield InfoHeader("Attach to qube:")
            for vm in other_vms:
                yield AttachWidget(vm, self.device)

            yield SeparatorItem()

            yield InfoHeader("Attach to new disposable qube:")

            for vm in disp_vm_templates:
                yield AttachDisposableWidget(vm, self.device, self.variant)

        yield DeviceSettingsWidget(self.device, self.variant)


def generate_wrapper_widget(
    widget_class: Callable, signal: str, inside_widget: ActionableWidget
):
    """
    Wraps a provided
    :param widget_class: "outside" widget class, e.g. Gtk.MenuItem
    :param signal: name of the signal to which we should connect widget actions
    :param inside_widget: inner widget
    :return: a new widget_class instance with inside_widget in it
    """
    widget = widget_class()
    widget.add(inside_widget)

    def run_async(func, *_args):
        asyncio.create_task(func())

    widget.connect(signal, functools.partial(run_async, inside_widget.widget_action))
    widget.set_sensitive(inside_widget.actionable)
    return widget
