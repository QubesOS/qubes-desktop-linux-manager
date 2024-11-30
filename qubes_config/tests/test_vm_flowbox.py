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
# pylint: disable=missing-function-docstring,missing-module-docstring
from unittest.mock import patch

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk

from ..global_config.vm_flowbox import (
    VMFlowboxHandler,
    VMFlowBoxButton,
    PlaceholderText,
)


def get_visible_vms(flowbox_handler: VMFlowboxHandler):
    visible_vms = []
    placeholder = None
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, PlaceholderText):
            placeholder = child
        else:
            assert isinstance(child, VMFlowBoxButton)
            assert child.get_visible()
            visible_vms.append(child.vm)
    assert placeholder
    assert placeholder.get_visible() != bool(visible_vms)
    return visible_vms


def test_simple_flowbox_init_empty(test_qapp, test_builder):
    flowbox_handler = VMFlowboxHandler(test_builder, test_qapp, "flowtest", [])
    assert not flowbox_handler.is_changed()

    assert len(flowbox_handler.flowbox.get_children()) == 1  # only placeholder
    assert isinstance(
        flowbox_handler.flowbox.get_children()[0], PlaceholderText
    )
    assert flowbox_handler.flowbox.get_children()[0].get_visible()
    assert not flowbox_handler.add_box.get_visible()


def test_simple_flowbox_init_not_empty(test_qapp, test_builder):
    initial_vms = [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    assert not flowbox_handler.is_changed()

    # placeholder plus two vms
    assert len(flowbox_handler.flowbox.get_children()) == 3

    visible_vms = get_visible_vms(flowbox_handler)
    assert sorted(visible_vms) == sorted(initial_vms)
    assert sorted(initial_vms) == flowbox_handler.selected_vms


@patch(
    "qubes_config.global_config.vm_flowbox.ask_question",
    return_value=Gtk.ResponseType.YES,
)
def test_flowbox_remove_button(mock_question, test_qapp, test_builder):
    initial_vms = [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    # remove test-vm
    assert not mock_question.mock_calls
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm.name == "test-vm":
            child.get_child().clicked()
    assert len(mock_question.mock_calls) == 1

    assert get_visible_vms(flowbox_handler) == [test_qapp.domains["test-blue"]]
    assert flowbox_handler.selected_vms == [test_qapp.domains["test-blue"]]

    # remove test-blue
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm.name == "test-blue":
            child.get_child().clicked()
    assert len(mock_question.mock_calls) == 2

    assert not get_visible_vms(flowbox_handler)
    assert not flowbox_handler.selected_vms


@patch(
    "qubes_config.global_config.vm_flowbox.ask_question",
    return_value=Gtk.ResponseType.NO,
)
def test_flowbox_remove_button_no(mock_question, test_qapp, test_builder):
    initial_vms = [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    # remove test-vm
    assert not mock_question.mock_calls
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm.name == "test-vm":
            child.get_child().clicked()
    assert len(mock_question.mock_calls) == 1

    assert get_visible_vms(flowbox_handler) == sorted(initial_vms)
    assert sorted(flowbox_handler.selected_vms) == sorted(initial_vms)


def test_flowbox_add_vm(test_qapp, test_builder):
    initial_vms = [test_qapp.domains["test-vm"]]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    # try to add a VM and abort
    assert not flowbox_handler.add_box.get_visible()
    flowbox_handler.add_button.clicked()
    assert flowbox_handler.add_box.get_visible()
    flowbox_handler.add_qube_model.select_value("test-blue")
    flowbox_handler.add_cancel.clicked()

    assert not flowbox_handler.add_box.get_visible()
    assert sorted(flowbox_handler.selected_vms) == sorted(initial_vms)
    assert sorted(get_visible_vms(flowbox_handler)) == sorted(initial_vms)

    # now try to add and do not abort
    flowbox_handler.add_button.clicked()
    assert flowbox_handler.add_box.get_visible()
    flowbox_handler.add_qube_model.select_value("test-blue")
    flowbox_handler.add_confirm.clicked()

    assert not flowbox_handler.add_box.get_visible()
    expected_vms = sorted(
        [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]
    )
    assert sorted(flowbox_handler.selected_vms) == expected_vms
    assert sorted(get_visible_vms(flowbox_handler)) == expected_vms

    # now try to add something that's already selected
    flowbox_handler.add_button.clicked()
    assert flowbox_handler.add_box.get_visible()
    flowbox_handler.add_qube_model.select_value("test-blue")
    with patch(
        "qubes_config.global_config.vm_flowbox.show_error"
    ) as mock_error:
        assert not mock_error.mock_calls
        flowbox_handler.add_confirm.clicked()
        assert mock_error.mock_calls
    # the box should not have hidden, maybe user wants to change selection
    assert flowbox_handler.add_box.get_visible()
    expected_vms = sorted(
        [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]
    )
    assert sorted(flowbox_handler.selected_vms) == expected_vms
    assert sorted(get_visible_vms(flowbox_handler)) == expected_vms


@patch(
    "qubes_config.global_config.vm_flowbox.ask_question",
    return_value=Gtk.ResponseType.YES,
)
def test_save_reset(_mock_question, test_qapp, test_builder):
    test_vm = test_qapp.domains["test-vm"]
    blue_vm = test_qapp.domains["test-blue"]

    initial_vms = [test_vm]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    assert not flowbox_handler.is_changed()

    # add something
    flowbox_handler.add_selected_vm(blue_vm)
    # correct vms in correct order
    assert flowbox_handler.selected_vms == [blue_vm, test_vm]
    assert get_visible_vms(flowbox_handler) == [blue_vm, test_vm]
    assert flowbox_handler.is_changed()
    assert flowbox_handler.added_vms == [blue_vm]
    assert not flowbox_handler.removed_vms

    # remove added qube
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm == blue_vm:
            child.get_child().clicked()
    assert flowbox_handler.selected_vms == [test_vm]
    assert get_visible_vms(flowbox_handler) == [test_vm]
    assert not flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert not flowbox_handler.removed_vms

    # remove more
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm == test_vm:
            child.get_child().clicked()
    assert not flowbox_handler.selected_vms
    assert not get_visible_vms(flowbox_handler)
    assert flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert flowbox_handler.removed_vms == [test_vm]

    # reset to start
    flowbox_handler.reset()
    assert flowbox_handler.selected_vms == [test_vm]
    assert get_visible_vms(flowbox_handler) == [test_vm]
    assert not flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert not flowbox_handler.removed_vms

    # add something and save
    flowbox_handler.add_selected_vm(blue_vm)
    flowbox_handler.save()
    assert flowbox_handler.selected_vms == [blue_vm, test_vm]
    assert get_visible_vms(flowbox_handler) == [blue_vm, test_vm]
    assert not flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert not flowbox_handler.removed_vms

    # remove all and save
    for child in flowbox_handler.flowbox.get_children():
        if isinstance(child, VMFlowBoxButton) and child.vm in [
            blue_vm,
            test_vm,
        ]:
            child.get_child().clicked()
    flowbox_handler.save()
    assert not flowbox_handler.selected_vms
    assert not get_visible_vms(flowbox_handler)
    assert not flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert not flowbox_handler.removed_vms

    # add something and reset to none
    flowbox_handler.add_selected_vm(blue_vm)
    flowbox_handler.reset()
    assert not flowbox_handler.selected_vms
    assert not get_visible_vms(flowbox_handler)
    assert not flowbox_handler.is_changed()
    assert not flowbox_handler.added_vms
    assert not flowbox_handler.removed_vms


def test_flowbox_verify(test_qapp, test_builder):
    test_vm = test_qapp.domains["test-vm"]
    red_vm = test_qapp.domains["test-red"]

    initial_vms = [test_vm]

    flowbox_handler = VMFlowboxHandler(
        test_builder,
        test_qapp,
        "flowtest",
        initial_vms=initial_vms,
        verification_callback=lambda vm: vm.name != "test-blue",
    )

    # attempt to add and see an erorr
    flowbox_handler.add_button.clicked()
    assert flowbox_handler.add_box.get_visible()
    flowbox_handler.add_qube_model.select_value("test-blue")
    # vm will not be added, but the verification callback is responsible
    # for messaging (it can propose additional actions)
    flowbox_handler.add_confirm.clicked()
    assert flowbox_handler.selected_vms == [test_vm]
    assert get_visible_vms(flowbox_handler) == [test_vm]
    assert not flowbox_handler.is_changed()

    # but adding correct stuff still works
    flowbox_handler.add_button.clicked()
    assert flowbox_handler.add_box.get_visible()
    flowbox_handler.add_qube_model.select_value("test-red")
    flowbox_handler.add_confirm.clicked()
    assert flowbox_handler.selected_vms == [red_vm, test_vm]
    assert get_visible_vms(flowbox_handler) == [red_vm, test_vm]
    assert flowbox_handler.is_changed()


def test_flowbox_visibility(test_qapp, test_builder):
    test_vm = test_qapp.domains["test-vm"]
    initial_vms = [test_vm]

    flowbox_handler = VMFlowboxHandler(
        test_builder, test_qapp, "flowtest", initial_vms=initial_vms
    )

    flowbox_handler.set_visible(True)
    assert flowbox_handler.selected_vms == [test_vm]

    flowbox_handler.set_visible(False)
    assert not flowbox_handler.selected_vms

    flowbox_handler.set_visible(True)
    assert flowbox_handler.selected_vms == [test_vm]
