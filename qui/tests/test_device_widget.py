"""Devices widget tests for the "microphone not attached" notification."""

# pylint: disable=redefined-outer-name

import asyncio
from unittest import mock

import pytest

from qui.devices.device_widget import DevicesTray, Gio, GLib, MIC_ID


@pytest.fixture
def tray():
    """Minimal stand-in for DevicesTray, enough for the mic handlers."""
    fake_tray = mock.Mock()
    fake_tray.devices = {MIC_ID: mock.Mock()}
    fake_tray.devices[MIC_ID].is_valid_for_vm.return_value = True
    fake_tray.devices[MIC_ID].devices_to_attach_with_me = []
    fake_tray.qapp.domains = {}
    return fake_tray


@pytest.fixture
def vm():
    fake_vm = mock.MagicMock()
    fake_vm.name = "work"
    fake_vm.__str__.return_value = "work"
    fake_vm.klass = "AppVM"
    fake_vm.devices_denied = ""
    return fake_vm


def test_audio_input_blocked(tray, vm):
    DevicesTray.audio_input_blocked(tray, vm, "audio-input-blocked")
    tray.send_notification.assert_called_once()
    notification_id, notification = tray.send_notification.call_args[0]
    assert notification_id == "mic-blocked-work"
    assert isinstance(notification, Gio.Notification)


def test_audio_input_blocked_mic_denied(tray, vm):
    tray.devices[MIC_ID].is_valid_for_vm.return_value = False
    DevicesTray.audio_input_blocked(tray, vm, "audio-input-blocked")
    tray.send_notification.assert_not_called()


def test_audio_input_blocked_no_mic(tray, vm):
    tray.devices = {}
    DevicesTray.audio_input_blocked(tray, vm, "audio-input-blocked")
    tray.send_notification.assert_not_called()


def test_attach_mic(tray, vm):
    tray.qapp.domains = {"work": vm}

    async def run():
        DevicesTray.do_attach_mic(tray, None, GLib.Variant.new_string("work"))
        await asyncio.sleep(0.1)

    asyncio.get_event_loop().run_until_complete(run())
    microphone = tray.devices[MIC_ID]
    microphone.attach_to_vm.assert_called_once()
    args, kwargs = microphone.attach_to_vm.call_args
    assert args[0].name == "work"
    assert kwargs == {"with_aux_devices": False}


def test_attach_mic_unknown_vm(tray):
    DevicesTray.do_attach_mic(tray, None, GLib.Variant.new_string("nonexistent"))
    tray.devices[MIC_ID].attach_to_vm.assert_not_called()


def _button_actions(tray, vm):
    with mock.patch.object(Gio.Notification, "add_button_with_target") as add:
        DevicesTray.audio_input_blocked(tray, vm, "audio-input-blocked")
    return [call.args[1] for call in add.call_args_list]


def test_audio_input_blocked_buttons_without_camera(tray, vm):
    """No linked camera: only the mic-only button is offered."""
    targets = _button_actions(tray, vm)
    assert targets == ["app.attach-mic"]


def test_audio_input_blocked_buttons_with_camera(tray, vm):
    """Linked camera: a second button attaches mic and camera."""
    tray.devices[MIC_ID].devices_to_attach_with_me = [mock.Mock()]
    targets = _button_actions(tray, vm)
    assert targets == ["app.attach-mic", "app.attach-mic-with-camera"]


def test_attach_mic_with_camera(tray, vm):
    """The mic-and-camera action attaches with aux devices."""
    tray.qapp.domains = {"work": vm}

    async def run():
        DevicesTray.do_attach_mic(
            tray, None, GLib.Variant.new_string("work"), with_camera=True
        )
        await asyncio.sleep(0.1)

    asyncio.get_event_loop().run_until_complete(run())
    _, kwargs = tray.devices[MIC_ID].attach_to_vm.call_args
    assert kwargs == {"with_aux_devices": True}


def test_attach_mic_no_mic(tray):
    """No microphone: the action does nothing."""
    tray.devices = {}
    tray.qapp.domains = mock.MagicMock()
    DevicesTray.do_attach_mic(tray, None, GLib.Variant.new_string("work"))
    tray.qapp.domains.__getitem__.assert_not_called()
