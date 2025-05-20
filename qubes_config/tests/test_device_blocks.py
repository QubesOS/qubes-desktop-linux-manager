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

from ..global_config.device_attachments import DeviceManager
from ..global_config.device_blocks import DeviceBlockHandler, OtherCategoryRow

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


### DEVICE POLICY BLOCK HANDLER TESTS


# pylint fails to correctly react to fixtures
# pylint: disable=redefined-outer-name
@pytest.fixture
def block_handler(real_builder, test_qapp_devices):
    dev_policy_manager = DeviceManager(test_qapp_devices)
    dev_policy_manager.load_data()

    handler = DeviceBlockHandler(
        test_qapp_devices, real_builder, dev_policy_manager
    )
    return handler


def test_policy_block_init(block_handler):
    assert len(block_handler.rule_list.get_children()) == 2


def test_policy_block_remove(block_handler):
    qapp = block_handler.qapp
    assert not block_handler.remove_button.is_sensitive()

    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    assert block_handler.remove_button.is_sensitive()

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        block_handler.remove_button.clicked()

    expected_calls = [
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p02****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"u02****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p0703**"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"ue0****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p123***"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_policy_block_add(block_handler):
    qapp = block_handler.qapp
    assert block_handler.add_button.is_sensitive()

    block_handler.add_button.clicked()

    block_handler.edit_dialog.qube_model.select_value("test-blue")

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "Human interface devices":
            row.activate()
            break
    else:
        assert False, "Category not found"

    for row in block_handler.edit_dialog.listbox.get_children():
        assert row.check_box.get_active() == (
            row.category_wrapper.name
            in ("Human interface devices", "Mice", "Keyboards")
        )

    assert block_handler.edit_dialog.ok_button.get_sensitive()
    block_handler.edit_dialog.ok_button.clicked()
    assert len(block_handler.rule_list.get_children()) == 3

    # only top level categories should block
    expected_calls = [
        ("test-blue", "admin.vm.device.denied.Add", None, b"u03****"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"p09****"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_policy_block_all(block_handler):
    qapp = block_handler.qapp
    assert block_handler.add_button.is_sensitive()

    block_handler.add_button.clicked()

    block_handler.edit_dialog.qube_model.select_value("test-blue")

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "All devices":
            row.activate()
            break
    else:
        assert False, "Category not found"

    for row in block_handler.edit_dialog.listbox.get_children():
        assert row.check_box.get_active()

    assert block_handler.edit_dialog.ok_button.get_sensitive()
    block_handler.edit_dialog.ok_button.clicked()
    assert len(block_handler.rule_list.get_children()) == 3

    # only top level categories should block
    expected_calls = [
        ("test-blue", "admin.vm.device.denied.Add", None, b"*******"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_policy_block_edit_vm(block_handler):
    qapp = block_handler.qapp
    assert not block_handler.edit_button.is_sensitive()

    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    assert block_handler.edit_button.is_sensitive()

    block_handler.edit_button.clicked()

    assert (
        block_handler.edit_dialog.qube_model.get_selected().name == "test-dev2"
    )

    for row in block_handler.edit_dialog.listbox.get_children():
        if isinstance(row, OtherCategoryRow):
            assert row.text_box.get_text() == "p123***"
            break
    else:
        assert False, "Misc row not found"

    for row in block_handler.edit_dialog.listbox.get_children():
        assert isinstance(row, OtherCategoryRow) or (
            row.check_box.get_active()
            == (row.category_wrapper.name == "Network devices")
        )

    block_handler.edit_dialog.qube_model.select_value("test-blue")
    block_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p02****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"u02****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p0703**"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"ue0****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p123***"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"p02****"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"p0703**"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"ue0****"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"u02****"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"p123***"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_policy_block_edit_rules(block_handler):
    qapp = block_handler.qapp
    assert not block_handler.edit_button.is_sensitive()

    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    assert block_handler.edit_button.is_sensitive()

    block_handler.edit_button.clicked()

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "Human interface devices":
            row.activate()
            break
    else:
        assert False, "Category not found"

    block_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        ("test-dev2", "admin.vm.device.denied.Add", None, b"u03****"),
        ("test-dev2", "admin.vm.device.denied.Add", None, b"p09****"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls


def test_policy_block_add_cancel(block_handler):
    assert block_handler.add_button.is_sensitive()

    assert len(block_handler.rule_list.get_children()) == 2

    block_handler.add_button.clicked()
    block_handler.edit_dialog.cancel_button.clicked()

    assert len(block_handler.rule_list.get_children()) == 2


def test_policy_block_unsaved(block_handler):
    # add
    block_handler.add_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-red")

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "Printers":
            row.activate()
            break
    else:
        assert False, "Category not found"
    block_handler.edit_dialog.ok_button.clicked()

    # remove
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        block_handler.remove_button.clicked()

    # edit
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev row"
    block_handler.edit_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-blue")
    block_handler.edit_dialog.ok_button.clicked()

    unsaved = block_handler.get_unsaved().split("\n")
    assert len(unsaved) == 3
    assert len([l for l in unsaved if "Removed" in l and "test-dev2" in l]) == 1
    assert len([l for l in unsaved if "changed" in l and "test-blue" in l]) == 1
    assert (
        len(
            [
                l
                for l in unsaved
                if "changed" in l and "test-red" in l and "Printers" in l
            ]
        )
        == 1
    )


def test_policy_block_reset(block_handler):
    # add
    block_handler.add_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-red")

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "Printers":
            row.activate()
            break
    else:
        assert False, "Category not found"
    block_handler.edit_dialog.ok_button.clicked()

    # remove
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        block_handler.remove_button.clicked()

    # edit
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev row"
    block_handler.edit_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-blue")
    block_handler.edit_dialog.ok_button.clicked()

    block_handler.reset()
    assert block_handler.get_unsaved() == ""

    # nothing should be called
    block_handler.save()


def test_policy_block_add_after_edit(block_handler):
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    assert block_handler.edit_button.is_sensitive()
    block_handler.edit_button.clicked()
    block_handler.edit_dialog.cancel_button.clicked()

    block_handler.add_button.clicked()

    assert block_handler.edit_dialog.qube_model.get_selected() is None
    for row in block_handler.edit_dialog.listbox.get_children():
        assert not row.check_box.get_active()


def test_multiple_save(block_handler):
    qapp = block_handler.qapp

    # add
    block_handler.add_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-red")

    for row in block_handler.edit_dialog.listbox.get_children():
        if row.category_wrapper.name == "Printers":
            row.activate()
            break
    else:
        assert False, "Category not found"
    block_handler.edit_dialog.ok_button.clicked()
    # remove
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev2":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev2 row"

    with patch(
        "qubes_config.global_config.device_widgets.ask_question",
        return_value=Gtk.ResponseType.YES,
    ):
        block_handler.remove_button.clicked()

    # edit
    for row in block_handler.rule_list.get_children():
        if row.vm_wrapper.vm.name == "test-dev":
            block_handler.rule_list.select_row(row)
            break
    else:
        assert False, "Failed to find test-dev row"
    block_handler.edit_button.clicked()
    block_handler.edit_dialog.qube_model.select_value("test-blue")
    block_handler.edit_dialog.ok_button.clicked()

    expected_calls = [
        ("test-red", "admin.vm.device.denied.Add", None, b"u07****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p123***"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p02****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"p0703**"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"ue0****"),
        ("test-dev2", "admin.vm.device.denied.Remove", None, b"u02****"),
        ("test-blue", "admin.vm.device.denied.Add", None, b"m******"),
        ("test-dev", "admin.vm.device.denied.Remove", None, b"m******"),
    ]
    for call in expected_calls:
        assert call not in qapp.actual_calls
        qapp.expected_calls[call] = b"0\x00"

    block_handler.save()

    for call in expected_calls:
        assert call in qapp.actual_calls

    # save a couple more times
    for call in expected_calls:
        del qapp.expected_calls[call]
        assert qapp.actual_calls.count(call) == 1

    block_handler.save()
    block_handler.save()
    block_handler.save()

    for call in expected_calls:
        assert qapp.actual_calls.count(call) == 1
