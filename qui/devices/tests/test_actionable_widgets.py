# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2026 Sahil Kumar
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
# pylint: disable=redefined-outer-name
import asyncio
import pytest
from unittest.mock import patch, Mock
from qubesadmin import exc
from qubesadmin.tests.mock_app import MockQubesComplete
from qui.devices.actionable_widgets import (
    AttachDisposableWidget,
    DetachAndAttachDisposableWidget,
)


@pytest.fixture
def mock_qapp():
    app = MockQubesComplete()
    return app


def make_mock_device(device_class="block"):
    device = Mock()
    device.device_class = device_class
    device.interfaces = ""
    device.is_valid_for_vm = Mock(return_value=True)
    device.attach_to_vm = Mock()
    device.detach_from_vm = Mock()
    return device


def make_mock_vm(qubes_app):
    vm = Mock()
    vm.icon_name = "appvm-green"
    vm.name = "test-vm"
    vm.vm_object = qubes_app._qubes["test-vm"]  # pylint: disable=protected-access
    return vm


class TestAttachDisposableWidget:

    def test_block_device_opens_file_manager(self, mock_qapp):
        """run_service is called for block device attach to dispvm"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp123"
        mock_dispvm.log = Mock()
        mock_dispvm.devices_denied = ""

        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = AttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())

        mock_dispvm.run_service.assert_called_once_with(
            "qubes.StartApp+qubes-open-file-manager",
            wait=False,
        )

    def test_non_block_device_no_file_manager(self, mock_qapp):
        """run_service is NOT called for non-block device"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_device = make_mock_device("usb")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp123"
        mock_dispvm.devices_denied = ""

        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = AttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())

        mock_dispvm.run_service.assert_not_called()

    def test_file_manager_exception_logged(self, mock_qapp):
        """QubesException from run_service is logged via dispvm.log"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp123"
        mock_dispvm.log = Mock()
        mock_dispvm.devices_denied = ""
        mock_dispvm.run_service.side_effect = exc.QubesException("failed")

        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = AttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())

        mock_dispvm.log.exception.assert_called_once()

    def test_feature_flag_disables_file_manager(self, mock_qapp):
        """run_service is NOT called when feature flag is disabled"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_vm.vm_object.features["device-open-file-manager-on-attach"] = ""
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp123"
        mock_dispvm.devices_denied = ""
        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = AttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())
        mock_dispvm.run_service.assert_not_called()


class TestDetachAndAttachDisposableWidget:

    def test_block_device_opens_file_manager(self, mock_qapp):
        """run_service is called for block device on detach+attach"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp456"
        mock_dispvm.log = Mock()
        mock_dispvm.devices_denied = ""

        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = DetachAndAttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())

        mock_dispvm.run_service.assert_called_once_with(
            "qubes.StartApp+qubes-open-file-manager",
            wait=False,
        )

    def test_file_manager_exception_logged(self, mock_qapp):
        """QubesException from run_service is logged via dispvm.log"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp456"
        mock_dispvm.log = Mock()
        mock_dispvm.devices_denied = ""
        mock_dispvm.run_service.side_effect = exc.QubesException("failed")

        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = DetachAndAttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())

        mock_dispvm.log.exception.assert_called_once()

    def test_feature_flag_disables_file_manager(self, mock_qapp):
        """run_service is NOT called when feature flag is disabled"""
        mock_vm = make_mock_vm(mock_qapp)
        mock_vm.vm_object.features["device-open-file-manager-on-attach"] = ""
        mock_device = make_mock_device("block")
        mock_dispvm = Mock()
        mock_dispvm.name = "disp456"
        mock_dispvm.devices_denied = ""
        with patch("qubesadmin.vm.DispVM.from_appvm", return_value=mock_dispvm):
            widget = DetachAndAttachDisposableWidget(mock_vm, mock_device)
            asyncio.run(widget.widget_action())
        mock_dispvm.run_service.assert_not_called()
