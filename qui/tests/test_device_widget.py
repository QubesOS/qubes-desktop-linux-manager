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
