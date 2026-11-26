"""Devices widget tests for the warning shown on input-only devices."""

from unittest import mock

import pytest
from qubesadmin.device_protocol import DeviceInterface

from qui.devices import actionable_widgets, backend
from qui.devices.device_widget import DeviceMenu

KEYBOARD = "u030101"
MOUSE = "u030102"
HID = "u030000"
SMART_CARD = "u0b0000"
AUDIO = "u010100"


def make_qube(name):
    fake_vm = mock.MagicMock()
    fake_vm.name = name
    fake_vm.__str__.return_value = name
    fake_vm.klass = "AppVM"
    fake_vm.devices_denied = ""
    fake_vm.icon = "appvm-red"
    return fake_vm


def make_vm(name):
    return backend.VM(make_qube(name))


def make_device(interfaces):
    dev = mock.MagicMock()
    dev.interfaces = [DeviceInterface(i) for i in interfaces]
    dev.devclass = "usb"
    dev.description = "Test device"
    dev.port = "sys-usb:2-1"
    dev.port_id = "2-1"
    dev.device_id = "0000:0000::" + "".join(interfaces)
    dev.parent_device = None
    dev.backend_domain = make_qube("sys-usb")
    return backend.Device(dev, mock.Mock())


def menu_widgets(menu):
    return [item.get_child() for item in menu.get_children()]


def find(menu, widget_class):
    return [w for w in menu_widgets(menu) if isinstance(w, widget_class)]


def submenu_of(menu, widget_class):
    for item in menu.get_children():
        if isinstance(item.get_child(), widget_class):
            return item.get_submenu()
    raise AssertionError(f"no {widget_class.__name__} in menu")


@pytest.mark.parametrize(
    "interfaces, expected",
    [
        ([KEYBOARD], True),
        ([KEYBOARD, MOUSE, HID], True),
        ([KEYBOARD, HID, SMART_CARD], False),
        ([AUDIO, HID], False),
        ([], False),
    ],
)
def test_is_input_only(interfaces, expected):
    """A device is input-only when all its interfaces are input interfaces."""
    assert make_device(interfaces).is_input_only is expected


def test_input_only_menu_shows_warning():
    """Input-only device: warning, attach options only under Attach anyway."""
    device = make_device([KEYBOARD, MOUSE])
    menu = DeviceMenu(
        actionable_widgets.MainDeviceWidget(device), [make_vm("work")], []
    )

    assert find(menu, actionable_widgets.InputDeviceWarning)
    assert not find(menu, actionable_widgets.AttachWidget)
    assert find(menu, actionable_widgets.DeviceSettingsWidget)
    anyway = submenu_of(menu, actionable_widgets.AttachAnywayWidget)
    assert find(anyway, actionable_widgets.AttachWidget)


def test_mixed_device_menu_has_no_warning():
    """Device with a non-input interface shows attach options, no warning."""
    device = make_device([KEYBOARD, HID, SMART_CARD])
    menu = DeviceMenu(
        actionable_widgets.MainDeviceWidget(device), [make_vm("work")], []
    )

    assert not find(menu, actionable_widgets.InputDeviceWarning)
    assert not find(menu, actionable_widgets.AttachAnywayWidget)
    assert find(menu, actionable_widgets.AttachWidget)


def test_attached_input_only_menu_keeps_detach():
    """Attached input-only device keeps Detach in the main menu."""
    device = make_device([MOUSE])
    work = make_vm("work")
    device.attachments.add(work)
    menu = DeviceMenu(
        actionable_widgets.MainDeviceWidget(device), [work, make_vm("other")], []
    )

    assert find(menu, actionable_widgets.DetachWidget)
    assert not find(menu, actionable_widgets.DetachAndAttachWidget)
    anyway = submenu_of(menu, actionable_widgets.AttachAnywayWidget)
    assert find(anyway, actionable_widgets.DetachAndAttachWidget)
