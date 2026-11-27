"""Devices widget tests using mock Qubes objects."""

# pylint: disable=protected-access

from qui.devices import device_widget
from qubesadmin.tests.mock_app import MockDispatcher, MockQube, MockQubes


def test_vm_started_before_events_connection(monkeypatch):
    """A qube started between startup and the events connection gets listed."""
    monkeypatch.setattr(device_widget.DevicesTray, "register", lambda self: True)
    qapp = MockQubes()
    qapp._qubes["work"] = MockQube(name="work", qapp=qapp)
    for mock_vm in qapp._qubes.values():
        for feature in (
            device_widget.backend.FEATURE_HIDE_CHILDREN,
            device_widget.backend.FEATURE_ATTACH_WITH_MIC,
        ):
            mock_vm.features.setdefault(feature, None)
    qapp.update_vm_calls()
    qapp.expected_calls[("dom0", "admin.deviceclass.List", None, None)] = (
        b"0\x00block\nmic\nusb\n"
    )
    dispatcher = MockDispatcher(qapp)

    widget = device_widget.DevicesTray(
        "org.qubes.qui.tray.Devices.test", qapp, dispatcher
    )
    widget.widget_icon.set_visible(False)
    assert "work" not in {vm.name for vm in widget.vms}

    qapp._qubes["work"].running = True
    qapp._qubes["work"].update_calls()
    dispatcher.handle("", "connection-established")

    assert "work" in {vm.name for vm in widget.vms}
