# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022 Marta Marczykowska-Górecka
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

from qubesadmin.tests.mock_app import MockQube
from unittest.mock import patch, call as mock_call
from ..global_config.disposables import DisposablesHandler

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


# when dealing with features, we need to be always using helper methods
@patch("qubes_config.global_config.disposables.get_feature")
@patch("qubes_config.global_config.disposables.apply_feature_change")
def test_preload_handler(
    mock_apply, mock_get, real_builder, test_qapp, test_policy_manager
):  # pylint: disable=unused-argument
    default_threshold = 0

    mock_get.return_value = None
    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    # Actual calls includes extraneous calls for this test, focus on the
    # calls made to each save.
    test_qapp.actual_calls = []
    assert disposables_handler.get_unsaved() == ""

    defdispvm_combo: Gtk.ComboBox = disposables_handler.defdispvm_combo
    preload_dispvm_spin: Gtk.SpinButton = (
        disposables_handler.preload_handler.preload_dispvm_spin
    )
    preload_dispvm_threshold_spin: Gtk.SpinButton = (
        disposables_handler.preload_handler.preload_dispvm_threshold_spin
    )
    preload_dispvm_spin_check: Gtk.CheckButton = (
        disposables_handler.preload_handler.preload_dispvm_check
    )

    initial_default_dispvm = defdispvm_combo.get_active_id()
    initial_preload_dispvm = preload_dispvm_spin.get_value_as_int()

    # Start available but unchecked.
    assert preload_dispvm_spin_check.is_sensitive()
    assert preload_dispvm_spin.get_value_as_int() == 0
    assert not preload_dispvm_spin.is_sensitive()
    assert preload_dispvm_threshold_spin.is_sensitive()
    assert preload_dispvm_threshold_spin.get_value_as_int() == default_threshold

    # Check to allow spin.
    preload_dispvm_spin_check.set_active(True)
    assert preload_dispvm_spin.is_sensitive()
    assert (
        preload_dispvm_spin.get_value_as_int()
        == disposables_handler.preload_handler.DEFAULT_MAX
    )

    # check that reset works
    preload_dispvm_spin.set_value(9)
    preload_dispvm_spin_check.set_active(False)
    disposables_handler.defdispvm_handler.model.select_value("None")
    disposables_handler.reset()
    assert preload_dispvm_spin_check.is_sensitive()
    assert preload_dispvm_spin.get_value_as_int() == 0
    assert not preload_dispvm_spin.is_sensitive()
    assert preload_dispvm_threshold_spin.is_sensitive()
    assert preload_dispvm_threshold_spin.get_value_as_int() == default_threshold

    # Assert when changing from no default_dispvm, requires checking the box.
    disposables_handler.defdispvm_handler.model.select_value("None")
    disposables_handler.defdispvm_handler.model.select_value(initial_default_dispvm)
    assert not preload_dispvm_spin.is_sensitive()

    # Check if saving works
    disposables_handler.reset()

    disposables_handler.defdispvm_handler.model.select_value("test-alt-dvm")
    preload_dispvm_spin_check.set_active(True)
    new_preload_value = initial_preload_dispvm + 2
    preload_dispvm_spin.set_value(new_preload_value)

    call = (
        "dom0",
        "admin.property.Set",
        "default_dispvm",
        b"test-alt-dvm",
    )
    test_qapp.expected_calls[call] = b"0\x00"
    assert call not in test_qapp.actual_calls

    disposables_handler.save()

    mock_apply.assert_called_once_with(
        test_qapp.domains["dom0"],
        "preload-dispvm-max",
        str(new_preload_value),
    )
    assert call in test_qapp.actual_calls

    test_qapp.actual_calls = []

    # Assert that saving '0' sets the value '0' instead of feature deletion.
    mock_get.return_value = new_preload_value
    preload_dispvm_spin.set_value(0)
    disposables_handler.save()

    assert mock_apply.call_args == mock_call(
        test_qapp.domains["dom0"],
        "preload-dispvm-max",
        "0",
    )
    test_qapp.actual_calls = []

    # Assert that deselecting the check box deletes the feature.
    mock_get.return_value = 0
    threshold_value = preload_dispvm_threshold_spin.get_value_as_int()
    preload_dispvm_spin.set_value(1)
    preload_dispvm_spin_check.set_active(False)
    assert not preload_dispvm_spin.is_sensitive()
    # Assert that threshold is not impacted.
    assert preload_dispvm_threshold_spin.is_sensitive()
    assert preload_dispvm_threshold_spin.get_value_as_int() == threshold_value
    mock_apply_count = mock_apply.call_count
    disposables_handler.save()
    assert mock_apply.call_count == mock_apply_count + 1
    assert mock_apply.call_args == mock_call(
        test_qapp.domains["dom0"],
        "preload-dispvm-max",
        None,
    )
    assert not preload_dispvm_spin.is_sensitive()

    # Assert that reset sets the current value of 'max' and 'threshold'
    preload_dispvm_spin_check.set_active(True)
    assert preload_dispvm_spin.is_sensitive()

    disposables_handler.reset()
    assert (
        preload_dispvm_spin.get_value_as_int()
        == disposables_handler.preload_handler.DEFAULT_MAX
    )
    assert preload_dispvm_threshold_spin.get_value_as_int() == default_threshold


def test_dvm_list(real_builder, test_qapp, test_policy_manager):
    test_qapp._qubes["default-dvm"].features["preload-dispvm-max"] = 9
    test_qapp._qubes["test-alt-dvm"].features["preload-dispvm-max"] = 42
    test_qapp.update_vm_calls()

    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    defdispvm_name = disposables_handler.defdispvm_combo.get_active_id()

    expected_dvms = [
        vm.name
        for vm in test_qapp.domains
        if getattr(vm, "template_for_dispvms", False)
    ]
    actual_dvms = []
    # verify if all disp templates are present
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        actual_dvms.append(row.dispvm.name)

    assert sorted(actual_dvms) == sorted(expected_dvms)
    found_default = False

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if defdispvm_name == row.dispvm.name:
            assert not row.preload_spin.get_sensitive()
            found_default = True
        else:
            assert row.preload_spin.get_sensitive()
        assert row.preload_spin.get_value_as_int() == int(
            test_qapp.domains[row.dispvm.name].features.get("preload-dispvm-max", 0)
        )

    assert found_default


def test_dispvm_change(real_builder, test_qapp, test_policy_manager):
    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    defdispvm_combo: Gtk.ComboBox = disposables_handler.defdispvm_combo
    initial_defdispvm = defdispvm_combo.get_active()

    assert disposables_handler.get_unsaved() == ""
    defdispvm_combo.set_active(initial_defdispvm + 1)
    assert disposables_handler.get_unsaved() != ""

    disposables_handler.reset()

    initial_defdispvm_name = defdispvm_combo.get_active_id()
    assert defdispvm_combo.get_active() == initial_defdispvm
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if defdispvm_combo.get_active_id() == row.dispvm.name:
            assert not row.preload_spin.get_sensitive()
        else:
            assert row.preload_spin.get_sensitive()
    defdispvm_combo.set_active(initial_defdispvm + 1)
    assert initial_defdispvm_name != defdispvm_combo.get_active_id()
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if defdispvm_combo.get_active_id() == row.dispvm.name:
            assert not row.preload_spin.get_sensitive()
        else:
            assert row.preload_spin.get_sensitive()
    defdispvm_combo.set_active(initial_defdispvm)
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if initial_defdispvm_name == row.dispvm.name:
            assert not row.preload_spin.get_sensitive()
        else:
            assert row.preload_spin.get_sensitive()


def test_dvm_change_preload(real_builder, test_qapp, test_policy_manager):
    test_qapp._qubes["default-dvm"].features["preload-dispvm-max"] = 9
    test_qapp._qubes["test-alt-dvm"].features["preload-dispvm-max"] = 42
    test_qapp._qubes["test-alt-dvm-running"].features["preload-dispvm-max"] = 7
    test_qapp.update_vm_calls()

    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "test-alt-dvm-running":
            row.preload_spin.set_value(99)

    assert disposables_handler.get_unsaved() != ""
    assert "test-alt-dvm-running" in disposables_handler.get_unsaved()

    test_qapp.expected_calls[
        ("test-alt-dvm-running", "admin.vm.feature.Set", "preload-dispvm-max", b"99")
    ] = b"0\x00"
    disposables_handler.save()
    assert disposables_handler.get_unsaved() == ""

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "test-alt-dvm-running":
            row.preload_spin.set_value(0)
        if row.dispvm.name == "test-alt-dvm":
            row.preload_spin.set_value(3)
    assert disposables_handler.get_unsaved() != ""

    test_qapp.expected_calls[
        ("test-alt-dvm-running", "admin.vm.feature.Set", "preload-dispvm-max", b"0")
    ] = b"0\x00"
    test_qapp.expected_calls[
        ("test-alt-dvm", "admin.vm.feature.Set", "preload-dispvm-max", b"3")
    ] = b"0\x00"
    disposables_handler.save()
    assert disposables_handler.get_unsaved() == ""


def test_dvm_reset_preload(real_builder, test_qapp, test_policy_manager):
    test_qapp._qubes["default-dvm"].features["preload-dispvm-max"] = 9
    test_qapp._qubes["test-alt-dvm"].features["preload-dispvm-max"] = 42
    test_qapp._qubes["test-alt-dvm-running"].features["preload-dispvm-max"] = 7
    test_qapp.update_vm_calls()

    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    disposables_handler.defdispvm_combo.set_active_id("test-alt-dvm")

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.preload_spin.get_sensitive():
            row.preload_spin.set_value(99)
    assert disposables_handler.get_unsaved() != 0

    disposables_handler.reset()

    assert disposables_handler.get_unsaved() == ""
    assert disposables_handler.defdispvm_combo.get_active_id() == "default-dvm"
    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "default-dvm":
            assert not row.preload_spin.get_sensitive()
            assert row.preload_spin.get_value_as_int() == 9
        if row.dispvm.name == "test-alt-dvm":
            assert row.preload_spin.get_sensitive()
            assert row.preload_spin.get_value_as_int() == 42
        if row.dispvm.name == "test-alt-dvm-running":
            assert row.preload_spin.get_sensitive()
            assert row.preload_spin.get_value_as_int() == 7


@patch("subprocess.check_call")
def test_dvm_new_qube(mock_check_call, real_builder, test_qapp, test_policy_manager):
    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    old_dvms = [
        vm.name
        for vm in test_qapp.domains
        if getattr(vm, "template_for_dispvms", False)
    ]
    assert len(disposables_handler.dispvm_list_handler.vm_list.get_children()) == len(
        old_dvms
    )

    test_qapp._qubes["new-dvm"] = MockQube(
        name="new-dvm",
        qapp=test_qapp,
        label="purple",
        template_for_dispvms=True,
        features={"preload-dispvm-max": 41},
    )
    test_qapp.update_vm_calls()

    disposables_handler.dispvm_list_handler.add_vm_button.clicked()
    assert mock_check_call.call_count == 1

    new_vms = [
        row.dispvm.name
        for row in disposables_handler.dispvm_list_handler.vm_list.get_children()
    ]
    assert len(new_vms) == len(old_dvms) + 1
    assert "new-dvm" in new_vms

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "new-dvm":
            assert row.preload_spin.get_sensitive()
            assert row.preload_spin.get_value_as_int() == 41
            break
    else:
        assert False


@patch("subprocess.check_call")
def test_dvm_settings(mock_check_call, real_builder, test_qapp, test_policy_manager):
    disposables_handler = DisposablesHandler(
        test_qapp, test_policy_manager, real_builder
    )
    test_qapp._qubes["default-dvm"].netvm = None
    test_qapp._qubes["default-dvm"].features["preload-dispvm-max"] = 11
    test_qapp.update_vm_calls()

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "default-dvm":
            assert row.netqube.token_name == "sys-firewall"
            assert row.preload_spin.get_value_as_int() == 0
            assert row.settings_button.get_sensitive()
            row.settings_button.clicked()
            break
    else:
        assert False

    assert mock_check_call.call_count == 1

    for row in disposables_handler.dispvm_list_handler.vm_list.get_children():
        if row.dispvm.name == "default-dvm":
            assert row.netqube.token_name == "None"
            assert row.preload_spin.get_value_as_int() == 11
            break
    else:
        assert False
