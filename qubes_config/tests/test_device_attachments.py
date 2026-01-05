# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2025 Marta Marczykowska-Górecka
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
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=protected-access
from unittest.mock import patch

import pytest

from qubesadmin.tests.mock_app import MockDevice
from ..global_config.device_attachments import AutoDeviceDialog, DeviceManager
from ..global_config.device_attachments import (
    AttachmentHandler,
    RequiredDeviceDialog,
    DevAttachmentHandler,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

### AUTO ATTACH HANDLER TESTS

AUTO_CLASSES = ["block", "mic", "usb"]
PCI_CLASSES = ["block", "pci"]


# pylint fails to correctly react to fixtures
# pylint: disable=redefined-outer-name
@pytest.fixture
def auto_attach_handler(real_builder, test_qapp_devices):
    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = AttachmentHandler(
        qapp=test_qapp_devices,
        builder=real_builder,
        device_policy_manager=dev_policy_manager,
        classes=AUTO_CLASSES,
        assignment_filter=DevAttachmentHandler._filter_auto,
        edit_dialog_class=AutoDeviceDialog,
        prefix="devices_auto",
    )
    return handler


@pytest.fixture
def required_handler(real_builder, test_qapp_devices):
    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = AttachmentHandler(
        qapp=test_qapp_devices,
        builder=real_builder,
        device_policy_manager=dev_policy_manager,
        classes=PCI_CLASSES,
        assignment_filter=DevAttachmentHandler._filter_required,
        edit_dialog_class=RequiredDeviceDialog,
        prefix="devices_required",
    )
    return handler


def test_auto_attach_init(auto_attach_handler):
    assert len(auto_attach_handler.rule_list.get_children()) == 3


def test_auto_attach_edit_dialog(auto_attach_handler):
    # test if the edit dialog works
    qapp = auto_attach_handler.qapp

    existing_rows = auto_attach_handler.rule_list.get_children()
    assert len(existing_rows) == 3

    auto_attach_handler.add_button.clicked()

    assert auto_attach_handler.edit_dialog.dev_modeler.get_selected() is None
    assert (
        "Internal Mic" not in auto_attach_handler.edit_dialog.devident_label.get_text()
    )

    auto_attach_handler.edit_dialog.dev_combo.set_active_id("dom0:mic::m000000")
    assert auto_attach_handler.edit_dialog.dev_modeler.get_selected() is not None
    assert "Internal Mic" in auto_attach_handler.edit_dialog.devident_label.get_text()
    assert "dom0:mic" in auto_attach_handler.edit_dialog.port_check.get_label()
    assert auto_attach_handler.edit_dialog.port_check.get_active()

    auto_attach_handler.edit_dialog.dev_combo.set_active_id("1:2:u011010")
    assert auto_attach_handler.edit_dialog.dev_modeler.get_selected() is not None
    assert "Hammer" in auto_attach_handler.edit_dialog.devident_label.get_text()
    assert "sys-usb:2-23" in auto_attach_handler.edit_dialog.port_check.get_label()

    auto_attach_handler.edit_dialog.auto_radio.set_active(True)
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-vm"]
    )
    assert auto_attach_handler.edit_dialog.port_check.get_active()
    auto_attach_handler.edit_dialog.port_check.set_active(False)

    auto_attach_handler.edit_dialog.ok_button.clicked()

    new_rows = auto_attach_handler.rule_list.get_children()
    assert len(new_rows) == len(existing_rows) + 1

    diff_rows = set(new_rows) - set(existing_rows)
    assert len(diff_rows) == 1
    new_row = diff_rows.pop()
    assert "Hammer" in new_row.dev_label.get_text()
    assert "will attach automatically" in new_row.action_label.get_text()
    assert len(new_row.vm_box.get_children()) == 1

    expected_call = (
        "test-vm",
        "admin.vm.device.usb.Assign",
        "sys-usb+_+1+2+u011010",
        b"device_id='1:2:u011010' port_id='*' devclass='usb' "
        b"backend_domain='sys-usb' mode='auto-attach'"
        b" frontend_domain='test-vm'",
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    auto_attach_handler.save()

    assert expected_call in qapp.actual_calls


def test_auto_attach_dialog_port_two_vms(auto_attach_handler):
    qapp = auto_attach_handler.qapp
    auto_attach_handler.add_button.clicked()
    auto_attach_handler.edit_dialog.dev_combo.set_active_id("1:2:u011010")
    auto_attach_handler.edit_dialog.devident_check.set_active(False)
    auto_attach_handler.edit_dialog.ask_radio.set_active(True)
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-vm"]
    )
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-red"]
    )
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-blue"]
    )
    auto_attach_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+_",
            b"device_id='*' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-vm'",
        ),
        (
            "test-red",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+_",
            b"device_id='*' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-red'",
        ),
        (
            "test-blue",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+_",
            b"device_id='*' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-blue'",
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    auto_attach_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_edit_rule_ident(auto_attach_handler):
    qapp = auto_attach_handler.qapp
    # change device and port checking, leave the rest the same
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    auto_attach_handler.edit_button.clicked()
    assert "Hammer" in auto_attach_handler.edit_dialog.devident_label.get_text()
    assert auto_attach_handler.edit_dialog.devident_check.get_active()
    assert auto_attach_handler.edit_dialog.port_check.get_active()
    assert auto_attach_handler.edit_dialog.auto_radio.get_active()
    assert auto_attach_handler.edit_dialog.qube_handler.selected_vms == [
        qapp.domains["test-vm"]
    ]

    auto_attach_handler.edit_dialog.dev_combo.set_active_id("dom0:mic::m000000")
    auto_attach_handler.edit_dialog.devident_check.set_active(True)
    auto_attach_handler.edit_dialog.port_check.set_active(False)

    auto_attach_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.mic.Assign",
            "dom0+_+dom0+mic++m000000",
            b"device_id='dom0:mic::m000000' port_id='*' devclass='mic' "
            b"backend_domain='dom0' mode='auto-attach' "
            b"frontend_domain='test-vm'",
        ),
        (
            "test-vm",
            "admin.vm.device.usb.Unassign",
            "sys-usb+2-23+1+2+u011010",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    auto_attach_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_edit_rule_action(auto_attach_handler):
    qapp = auto_attach_handler.qapp
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    auto_attach_handler.edit_button.clicked()

    auto_attach_handler.edit_dialog.ask_radio.set_active(True)

    auto_attach_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+1+2+u011010",
            b"device_id='1:2:u011010' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-vm'",
        ),
        (
            "test-vm",
            "admin.vm.device.usb.Unassign",
            "sys-usb+2-23+1+2+u011010",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    auto_attach_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_edit_rule_vms(auto_attach_handler):
    qapp = auto_attach_handler.qapp

    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    auto_attach_handler.edit_button.clicked()

    auto_attach_handler.edit_dialog.qube_handler.clear()
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-red"]
    )
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-blue"]
    )
    auto_attach_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-red",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+1+2+u011010",
            b"device_id='1:2:u011010' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='auto-attach' "
            b"frontend_domain='test-red'",
        ),
        (
            "test-blue",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-23+1+2+u011010",
            b"device_id='1:2:u011010' port_id='2-23' devclass='usb' "
            b"backend_domain='sys-usb' mode='auto-attach' "
            b"frontend_domain='test-blue'",
        ),
        (
            "test-vm",
            "admin.vm.device.usb.Unassign",
            "sys-usb+2-23+1+2+u011010",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    auto_attach_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_edit_rule_unknown_opt(real_builder, test_qapp_devices):
    # attachment with both port and device as *
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="usb",
            product="Strange",
            vendor="ACME",
            backend_vm="sys-usb",
            assigned=[("test-vm", "auto-attach", ["misc_opt"])],
            device_id="1:3:u011010",
            port="2-24",
        )
    )
    test_qapp_devices.update_vm_calls()

    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = AttachmentHandler(
        qapp=test_qapp_devices,
        builder=real_builder,
        device_policy_manager=dev_policy_manager,
        classes=AUTO_CLASSES,
        assignment_filter=DevAttachmentHandler._filter_auto,
        edit_dialog_class=AutoDeviceDialog,
        prefix="devices_auto",
    )
    assert isinstance(handler.edit_dialog, AutoDeviceDialog)
    for row in handler.rule_list.get_children():
        if "Strange" in row.dev_label.get_text():
            handler.rule_list.select_row(row)
            break
    else:
        assert False

    handler.edit_button.clicked()

    handler.edit_dialog.qube_handler.clear()
    handler.edit_dialog.qube_handler.add_selected_vm(
        test_qapp_devices.domains["test-red"]
    )
    handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-red",
            "admin.vm.device.usb.Assign",
            "sys-usb+2-24+1+3+u011010",
            b"device_id='1:3:u011010' port_id='2-24' devclass='usb' "
            b"backend_domain='sys-usb' mode='auto-attach' "
            b"frontend_domain='test-red' _misc_opt='True'",
        ),
        (
            "test-vm",
            "admin.vm.device.usb.Unassign",
            "sys-usb+2-24+1+3+u011010",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in test_qapp_devices.actual_calls
        test_qapp_devices.expected_calls[call] = b"0\x00"

    handler.save()

    for call in expected_calls:
        assert call in test_qapp_devices.actual_calls


def test_auto_not_list_required(real_builder, test_qapp_devices):
    # do not show a rule for block devices that are Required in the auto-attach list
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="block",
            product="RequiredB",
            vendor="ACME",
            backend_vm="sys-usb",
            assigned=[("test-vm", "required", None)],
            device_id="1d6b:0104:DEADBEEF:b123456",
            port="sda",
        )
    )
    test_qapp_devices.update_vm_calls()

    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = AttachmentHandler(
        qapp=test_qapp_devices,
        builder=real_builder,
        device_policy_manager=dev_policy_manager,
        classes=AUTO_CLASSES,
        assignment_filter=DevAttachmentHandler._filter_auto,
        edit_dialog_class=AutoDeviceDialog,
        prefix="devices_auto",
    )
    assert isinstance(handler.edit_dialog, AutoDeviceDialog)
    for row in handler.rule_list.get_children():
        if "RequiredB" in row.dev_label.get_text():
            assert False, "Required incorrectly listed in AutoAttach"


def test_remove_rule(auto_attach_handler):
    qapp = auto_attach_handler.qapp
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        auto_attach_handler.remove_button.clicked()

    expected_call = (
        "test-vm",
        "admin.vm.device.usb.Unassign",
        "sys-usb+2-23+1+2+u011010",
        None,
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    auto_attach_handler.save()

    assert expected_call in qapp.actual_calls


def test_auto_attach_buttons(auto_attach_handler):
    assert auto_attach_handler.add_button.get_sensitive()
    assert not auto_attach_handler.edit_button.get_sensitive()
    assert not auto_attach_handler.remove_button.get_sensitive()

    for row in auto_attach_handler.rule_list.get_children():
        auto_attach_handler.rule_list.select_row(row)
        break

    assert auto_attach_handler.add_button.get_sensitive()
    assert auto_attach_handler.edit_button.get_sensitive()
    assert auto_attach_handler.remove_button.get_sensitive()

    auto_attach_handler.rule_list.select_row(None)
    assert auto_attach_handler.add_button.get_sensitive()
    assert not auto_attach_handler.edit_button.get_sensitive()
    assert not auto_attach_handler.remove_button.get_sensitive()


def test_auto_attach_noop(auto_attach_handler):
    for row in auto_attach_handler.rule_list.get_children():
        auto_attach_handler.rule_list.select_row(row)
        break

    auto_attach_handler.edit_button.clicked()
    auto_attach_handler.edit_dialog.ok_button.clicked()

    auto_attach_handler.save()


def test_auto_attach_device_unavailable(auto_attach_handler):
    qapp = auto_attach_handler.qapp

    for row in auto_attach_handler.rule_list.get_children():
        # TODO: fix when prbartman fixes saving device identity
        if "?***" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    # this only tests removing the rule

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        auto_attach_handler.remove_button.clicked()

    expected_call = (
        "test-vm",
        "admin.vm.device.usb.Unassign",
        "sys-usb+2-30+0+0007+u01101",
        None,
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    auto_attach_handler.save()

    assert expected_call in qapp.actual_calls


def test_auto_attach_validity(auto_attach_handler):
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    auto_attach_handler.edit_button.clicked()

    assert auto_attach_handler.edit_dialog.ok_button.get_sensitive()

    auto_attach_handler.edit_dialog.port_check.set_active(False)
    auto_attach_handler.edit_dialog.devident_check.set_active(False)

    assert not auto_attach_handler.edit_dialog.ok_button.get_sensitive()

    auto_attach_handler.edit_dialog.port_check.set_active(True)

    assert auto_attach_handler.edit_dialog.ok_button.get_sensitive()

    auto_attach_handler.edit_dialog.qube_handler.clear()

    assert not auto_attach_handler.edit_dialog.ok_button.get_sensitive()


def test_auto_attach_get_unsaved(auto_attach_handler):
    assert auto_attach_handler.get_unsaved() == ""
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        auto_attach_handler.remove_button.clicked()

    for row in auto_attach_handler.rule_list.get_children():
        if "Anvil" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    assert auto_attach_handler.edit_button.get_sensitive()
    auto_attach_handler.edit_button.clicked()
    auto_attach_handler.edit_dialog.port_check.set_active(False)
    auto_attach_handler.edit_dialog.ok_button.clicked()

    assert "Hammer" in auto_attach_handler.get_unsaved()
    assert "Anvil" in auto_attach_handler.get_unsaved()


def test_auto_attach_reset(auto_attach_handler):
    qapp = auto_attach_handler.qapp

    assert auto_attach_handler.get_unsaved() == ""
    for row in auto_attach_handler.rule_list.get_children():
        if "Hammer" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        auto_attach_handler.remove_button.clicked()

    for row in auto_attach_handler.rule_list.get_children():
        if "Anvil" in row.dev_label.get_text():
            auto_attach_handler.rule_list.select_row(row)
            break
    else:
        assert False

    auto_attach_handler.edit_button.clicked()
    auto_attach_handler.edit_dialog.port_check.set_active(False)
    auto_attach_handler.edit_dialog.ok_button.clicked()

    auto_attach_handler.add_button.clicked()
    auto_attach_handler.edit_dialog.dev_combo.set_active_id("1:2:u011010")
    auto_attach_handler.edit_dialog.devident_check.set_active(False)
    auto_attach_handler.edit_dialog.port_check.set_active(True)
    auto_attach_handler.edit_dialog.ask_radio.set_active(True)
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-vm"]
    )
    auto_attach_handler.edit_dialog.ok_button.clicked()

    assert auto_attach_handler.get_unsaved() != ""

    auto_attach_handler.reset()
    assert auto_attach_handler.get_unsaved() == ""
    # nothing should be called here
    auto_attach_handler.save()


def test_auto_attach_add_cancel(auto_attach_handler):
    # no ghosts after cancelling adding a rule
    assert len(auto_attach_handler.rule_list.get_children()) == 3

    auto_attach_handler.add_button.clicked()
    auto_attach_handler.edit_dialog.cancel_button.clicked()

    assert len(auto_attach_handler.rule_list.get_children()) == 3


def test_auto_attach_block_read_only(auto_attach_handler):
    qapp = auto_attach_handler.qapp
    auto_attach_handler.add_button.clicked()
    auto_attach_handler.edit_dialog.dev_combo.set_active_id("444:888:b123422")
    auto_attach_handler.edit_dialog.devident_check.set_active(True)
    auto_attach_handler.edit_dialog.port_check.set_active(True)
    auto_attach_handler.edit_dialog.ask_radio.set_active(True)
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-vm"]
    )
    auto_attach_handler.edit_dialog.qube_handler.add_selected_vm(
        qapp.domains["test-red"]
    )
    auto_attach_handler.edit_dialog.read_only_check.set_active(True)
    auto_attach_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.block.Assign",
            "sys-usb+sda+444+888+b123422",
            b"device_id='444:888:b123422' port_id='sda' devclass='block' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-vm' _read-only='True'",
        ),
        (
            "test-red",
            "admin.vm.device.block.Assign",
            "sys-usb+sda+444+888+b123422",
            b"device_id='444:888:b123422' port_id='sda' devclass='block' "
            b"backend_domain='sys-usb' mode='ask-to-attach' "
            b"frontend_domain='test-red' _read-only='True'",
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    auto_attach_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_req_init(required_handler):
    assert len(required_handler.rule_list.get_children()) == 3


def test_req_edit_dialog(required_handler):
    # test if the edit dialog works
    qapp = required_handler.qapp

    existing_rows = required_handler.rule_list.get_children()
    required_handler.add_button.clicked()

    assert required_handler.edit_dialog.dev_modeler.get_selected() is None
    assert "Piano" not in required_handler.edit_dialog.devident_label.get_text()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p028000")
    assert required_handler.edit_dialog.dev_modeler.get_selected() is not None
    assert "Network" in required_handler.edit_dialog.devident_label.get_text()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p300000")
    assert required_handler.edit_dialog.dev_modeler.get_selected() is not None
    assert "Piano" in required_handler.edit_dialog.devident_label.get_text()

    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])

    required_handler.edit_dialog.ok_button.clicked()

    new_rows = required_handler.rule_list.get_children()
    assert len(new_rows) == len(existing_rows) + 1

    diff_rows = set(new_rows) - set(existing_rows)
    assert len(diff_rows) == 1
    new_row = diff_rows.pop()
    assert "Piano" in new_row.dev_label.get_text()
    assert "required" in new_row.action_label.get_text()
    assert len(new_row.vm_box.get_children()) == 1

    expected_call = (
        "test-vm",
        "admin.vm.device.pci.Assign",
        "dom0+0f.0+0x8086+0x51f0++p300000",
        b"device_id='0x8086:0x51f0::p300000' port_id='0f.0' "
        b"devclass='pci' backend_domain='dom0' mode='required'"
        b" frontend_domain='test-vm'",
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    required_handler.save()

    assert expected_call in qapp.actual_calls


def test_req_dialog_change_vm(required_handler):
    qapp = required_handler.qapp

    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()

    required_handler.edit_dialog.qube_handler.clear()
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-red"])
    required_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-red",
            "admin.vm.device.pci.Assign",
            "dom0+0c.0+0x8086+0x51f0++p028000",
            b"device_id='0x8086:0x51f0::p028000' port_id='0c.0' "
            b"devclass='pci' backend_domain='dom0' mode='required'"
            b" frontend_domain='test-red'",
        ),
        (
            "sys-net",
            "admin.vm.device.pci.Unassign",
            "dom0+0c.0+0x8086+0x51f0++p028000",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    required_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_req_add_no_strict(required_handler):
    # test if the edit dialog works
    qapp = required_handler.qapp

    required_handler.add_button.clicked()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p300000")

    assert not required_handler.edit_dialog.ok_button.get_sensitive()
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])

    assert not required_handler.edit_dialog.no_strict_check.get_active()
    required_handler.edit_dialog.no_strict_check.set_active(True)

    required_handler.edit_dialog.ok_button.clicked()

    expected_call = (
        "test-vm",
        "admin.vm.device.pci.Assign",
        "dom0+0f.0+0x8086+0x51f0++p300000",
        b"device_id='0x8086:0x51f0::p300000' port_id='0f.0' "
        b"devclass='pci' backend_domain='dom0' mode='required'"
        b" frontend_domain='test-vm' _no-strict-reset='True'",
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    required_handler.save()

    assert expected_call in qapp.actual_calls


def test_req_add_both_opts(required_handler):
    # test if the edit dialog works
    qapp = required_handler.qapp

    required_handler.add_button.clicked()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p300000")

    assert not required_handler.edit_dialog.ok_button.get_sensitive()
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])
    assert required_handler.edit_dialog.ok_button.get_sensitive()

    assert not required_handler.edit_dialog.permissive_check.get_active()
    assert not required_handler.edit_dialog.no_strict_check.get_active()
    required_handler.edit_dialog.permissive_check.set_active(True)
    required_handler.edit_dialog.no_strict_check.set_active(True)

    required_handler.edit_dialog.ok_button.clicked()

    expected_call = (
        "test-vm",
        "admin.vm.device.pci.Assign",
        "dom0+0f.0+0x8086+0x51f0++p300000",
        b"device_id='0x8086:0x51f0::p300000' port_id='0f.0' "
        b"devclass='pci' backend_domain='dom0' mode='required'"
        b" frontend_domain='test-vm' _no-strict-reset='True' "
        b"_permissive='True'",
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    required_handler.save()

    assert expected_call in qapp.actual_calls


def test_req_dialog_remove_opts(required_handler):
    # open a bunch of edit screens in order to make sure checkboxes get
    # correctly checked and unchecked
    qapp = required_handler.qapp

    for row in required_handler.rule_list.get_children():
        if "Orchestra" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()

    assert required_handler.edit_dialog.no_strict_check.get_active()
    assert not required_handler.edit_dialog.permissive_check.get_active()

    # close, select another
    required_handler.edit_dialog.cancel_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()

    assert not required_handler.edit_dialog.no_strict_check.get_active()
    assert not required_handler.edit_dialog.permissive_check.get_active()

    required_handler.edit_dialog.cancel_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Orchestra" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()

    assert required_handler.edit_dialog.no_strict_check.get_active()
    assert not required_handler.edit_dialog.permissive_check.get_active()
    required_handler.edit_dialog.no_strict_check.set_active(False)
    required_handler.edit_dialog.permissive_check.set_active(True)

    required_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-red",
            "admin.vm.device.pci.Assign",
            "dom0+0h.0+0x8086+0x51c8++p040300",
            b"device_id='0x8086:0x51c8::p040300' port_id='0h.0' "
            b"devclass='pci' backend_domain='dom0' mode='required'"
            b" frontend_domain='test-red' _permissive='True'",
        ),
        (
            "test-red",
            "admin.vm.device.pci.Unassign",
            "dom0+0h.0+0x8086+0x51c8++p040300",
            None,
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    required_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_req_buttons(required_handler):
    assert required_handler.add_button.get_sensitive()
    assert not required_handler.edit_button.get_sensitive()
    assert not required_handler.remove_button.get_sensitive()

    for row in required_handler.rule_list.get_children():
        required_handler.rule_list.select_row(row)
        break

    assert required_handler.add_button.get_sensitive()
    assert required_handler.edit_button.get_sensitive()
    assert required_handler.remove_button.get_sensitive()

    required_handler.rule_list.select_row(None)
    assert required_handler.add_button.get_sensitive()
    assert not required_handler.edit_button.get_sensitive()
    assert not required_handler.remove_button.get_sensitive()


def test_req_noop(required_handler):
    for row in required_handler.rule_list.get_children():
        required_handler.rule_list.select_row(row)
        break

    assert required_handler.edit_button.get_sensitive()
    required_handler.edit_button.clicked()
    required_handler.edit_dialog.ok_button.clicked()

    required_handler.save()


def test_req_validity(required_handler):
    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()

    assert required_handler.edit_dialog.ok_button.get_sensitive()

    required_handler.edit_dialog.qube_handler.clear()

    assert not required_handler.edit_dialog.ok_button.get_sensitive()

    required_handler.edit_dialog.qube_handler.add_selected_vm(
        required_handler.qapp.domains["test-red"]
    )

    assert required_handler.edit_dialog.ok_button.get_sensitive()


def test_req_get_unsaved(required_handler):
    assert required_handler.get_unsaved() == ""
    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        required_handler.remove_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Orchestra" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    assert required_handler.edit_button.get_sensitive()
    required_handler.edit_button.clicked()
    required_handler.edit_dialog.no_strict_check.set_active(False)
    required_handler.edit_dialog.ok_button.clicked()

    required_handler.add_button.clicked()
    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x461e::p0c0330")
    required_handler.edit_dialog.qube_handler.add_selected_vm(
        required_handler.qapp.domains["test-vm"]
    )
    required_handler.edit_dialog.ok_button.clicked()

    assert "Network Card" in required_handler.get_unsaved()
    assert "Orchestra" in required_handler.get_unsaved()
    assert "USB Controller" in required_handler.get_unsaved()


def test_req_reset(required_handler):
    qapp = required_handler.qapp

    assert required_handler.get_unsaved() == ""
    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        required_handler.remove_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Orchestra" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()
    required_handler.edit_dialog.no_strict_check.set_active(False)
    required_handler.edit_dialog.ok_button.clicked()

    required_handler.add_button.clicked()
    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x461e::p0c0330")
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])
    required_handler.edit_dialog.ok_button.clicked()

    assert required_handler.get_unsaved() != ""

    required_handler.reset()
    assert required_handler.get_unsaved() == ""
    # nothing should be called here
    required_handler.save()


def test_req_add_cancel(required_handler):
    # no ghosts after cancelling adding a rule
    assert len(required_handler.rule_list.get_children()) == 3

    required_handler.add_button.clicked()
    required_handler.edit_dialog.cancel_button.clicked()

    assert len(required_handler.rule_list.get_children()) == 3


def test_req_multiple_save(required_handler):
    """Check if we do not do superfluous saves when saving multiple times."""
    qapp = required_handler.qapp
    required_handler.add_button.clicked()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p300000")
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])
    required_handler.edit_dialog.ok_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Network Card" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        required_handler.remove_button.clicked()

    for row in required_handler.rule_list.get_children():
        if "Orchestra" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    assert required_handler.edit_button.get_sensitive()
    required_handler.edit_button.clicked()
    required_handler.edit_dialog.no_strict_check.set_active(False)
    required_handler.edit_dialog.permissive_check.set_active(True)
    required_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.pci.Assign",
            "dom0+0f.0+0x8086+0x51f0++p300000",
            b"device_id='0x8086:0x51f0::p300000' port_id='0f.0' "
            b"devclass='pci' backend_domain='dom0' mode='required'"
            b" frontend_domain='test-vm'",
        ),  # new assignment
        (
            "test-red",
            "admin.vm.device.pci.Unassign",
            "dom0+0h.0+0x8086+0x51c8++p040300",
            None,
        ),  # remove edited assignment
        (
            "test-red",
            "admin.vm.device.pci.Assign",
            "dom0+0h.0+0x8086+0x51c8++p040300",
            b"device_id='0x8086:0x51c8::p040300' port_id='0h.0' "
            b"devclass='pci' backend_domain='dom0' mode='required'"
            b" frontend_domain='test-red' _permissive='True'",
        ),  # add edited
        (
            "sys-net",
            "admin.vm.device.pci.Unassign",
            "dom0+0c.0+0x8086+0x51f0++p028000",
            None,
        ),  # removed assignment
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    required_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls

    # see if next saves do not do any superfluous calls
    for call in expected_calls:
        del qapp.expected_calls[call]

    required_handler.save()
    required_handler.save()

    for call in expected_calls:
        assert qapp.actual_calls.count(call) == 1


def test_req_options_after_save(required_handler):
    qapp = required_handler.qapp
    # test for a bug where applying options leads to incorrect options being
    # shown in edit dialog
    for row in required_handler.rule_list.get_children():
        if "USB Controller" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()
    assert not required_handler.edit_dialog.permissive_check.get_active()

    required_handler.edit_dialog.permissive_check.set_active(True)
    required_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "sys-net",
            "admin.vm.device.pci.Assign",
            "dom0+0d.0+0x8086+0x461e++p0c0330",
            b"device_id='0x8086:0x461e::p0c0330' port_id='0d.0' "
            b"devclass='pci' backend_domain='dom0' mode='required'"
            b" frontend_domain='sys-net' _permissive='True'",
        ),  # new assignment
        (
            "sys-net",
            "admin.vm.device.pci.Unassign",
            "dom0+0d.0+0x8086+0x461e++p0c0330",
            None,
        ),  # remove edited assignment
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    # because the main program does a reset after save to ensure correctness,
    # we need to check that the data loads correctly
    qapp.expected_calls[("sys-net", "admin.vm.device.pci.Assigned", None, None)] = (
        "0\x00dom0+0d.0+0x8086+0x461e++p0c0330 "
        "device_id='0x8086:0x461e::p0c0330' port_id='0d.0' devclass='pci' "
        "backend_domain='dom0' mode='required' frontend_domain='sys-net' "
        "_permissive='True'\n".encode()
    )

    required_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls

    required_handler.reset()
    for row in required_handler.rule_list.get_children():
        if "USB Controller" in row.dev_label.get_text():
            required_handler.rule_list.select_row(row)
            break
    else:
        assert False

    required_handler.edit_button.clicked()
    assert required_handler.edit_dialog.permissive_check.get_active()


def test_req_readonly(required_handler):
    # test if the edit dialog works
    qapp = required_handler.qapp

    required_handler.add_button.clicked()

    required_handler.edit_dialog.dev_combo.set_active_id("0x8086:0x51f0::p300000")

    assert not required_handler.edit_dialog.ok_button.get_sensitive()
    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])

    assert not required_handler.edit_dialog.no_strict_check.get_active()
    required_handler.edit_dialog.no_strict_check.set_active(True)

    required_handler.edit_dialog.ok_button.clicked()

    expected_call = (
        "test-vm",
        "admin.vm.device.pci.Assign",
        "dom0+0f.0+0x8086+0x51f0++p300000",
        b"device_id='0x8086:0x51f0::p300000' port_id='0f.0' "
        b"devclass='pci' backend_domain='dom0' mode='required'"
        b" frontend_domain='test-vm' _no-strict-reset='True'",
    )
    qapp.expected_calls[expected_call] = b"0\x00"
    assert expected_call not in qapp.actual_calls

    required_handler.save()

    assert expected_call in qapp.actual_calls


def test_req_grouping(real_builder, test_qapp_devices):
    # a device that has three assignments with different opts should appear
    # thrice
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="pci",
            product="OptionsDevice",
            backend_vm="dom0",
            assigned=[
                ("sys-net", "required", ["permissive"]),
                ("sys-usb", "required", ["no-strict-reset"]),
                ("test-vm", "required", None),
            ],
            device_id="0x8086:0x8857::p0c0330",
            port="0d.0",
            vendor="ACME",
        )
    )

    test_qapp_devices.update_vm_calls()

    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = AttachmentHandler(
        qapp=test_qapp_devices,
        builder=real_builder,
        device_policy_manager=dev_policy_manager,
        classes=PCI_CLASSES,
        assignment_filter=DevAttachmentHandler._filter_required,
        edit_dialog_class=RequiredDeviceDialog,
        prefix="devices_required",
    )

    rows = []
    for row in handler.rule_list.get_children():
        if "OptionsDevice" in row.dev_label.get_text():
            rows.append(row)

    assert len(rows) == 3


def test_req_port_not_required(required_handler):
    qapp = required_handler.qapp

    required_handler.add_button.clicked()

    assert required_handler.edit_dialog.dev_modeler.get_selected() is None
    assert "Ouroboros" not in required_handler.edit_dialog.devident_label.get_text()

    required_handler.edit_dialog.dev_combo.set_active_id("444:888:b123422")

    required_handler.edit_dialog.qube_handler.add_selected_vm(qapp.domains["test-vm"])

    assert required_handler.edit_dialog.port_check.get_active()
    required_handler.edit_dialog.port_check.set_active(False)
    required_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        (
            "test-vm",
            "admin.vm.device.block.Assign",
            "sys-usb+_+444+888+b123422",
            b"device_id='444:888:b123422' port_id='*' "
            b"devclass='block' backend_domain='sys-usb' mode='required'"
            b" frontend_domain='test-vm'",
        ),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    required_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls
