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
from unittest.mock import Mock, patch
from qrexec.policy.parser import Rule
from ..global_config.policy_handler import PolicyHandler
from ..global_config.policy_rules import RuleSimple, SimpleVerbDescription
from ..global_config.rule_list_widgets import (
    VMWidget,
    ActionWidget,
    RuleListBoxRow,
    NoActionListBoxRow,
    FilteredListBoxRow,
)

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


def make_rule(source, target, action):
    return RuleSimple(
        Rule.from_line(
            None,
            f"Service\t*\t{source}\t{target}\t{action}",
            filepath=None,
            lineno=0,
        )
    )


VERB_DESCR = SimpleVerbDescription(
    {"ask": "ASK", "allow": "ALLOW", "deny": "DENY"}
)


def test_vm_widget(test_qapp):
    simple_widget = VMWidget(
        qapp=test_qapp, categories=None, initial_value="test-vm"
    )

    # test if parts of the widgets behave as expected
    # at the start, name should be visible and combo hidden
    assert simple_widget.name_widget.get_visible()
    assert not simple_widget.combobox.get_visible()

    simple_widget.set_editable(True)
    assert not simple_widget.name_widget.get_visible()
    assert simple_widget.combobox.get_visible()


def test_vm_widget_changes(test_qapp):
    simple_widget = VMWidget(
        qapp=test_qapp, categories=None, initial_value="test-vm"
    )
    assert not simple_widget.is_changed()
    assert str(simple_widget.get_selected()) == "test-vm"

    simple_widget.set_editable(True)
    simple_widget.combobox.set_active_id("test-blue")
    assert simple_widget.is_changed()

    # get back to ineditable, change should be discarded
    simple_widget.set_editable(False)
    assert simple_widget.name_widget.token_name == "test-vm"
    assert simple_widget.combobox.get_active_id() == "test-vm"
    assert str(simple_widget.get_selected()) == "test-vm"
    assert not simple_widget.is_changed()

    # let's change stuff for real
    simple_widget.set_editable(True)
    simple_widget.combobox.set_active_id("test-blue")
    assert simple_widget.is_changed()

    simple_widget.save()
    simple_widget.set_editable(False)

    assert not simple_widget.is_changed()
    assert simple_widget.name_widget.token_name == "test-blue"
    assert simple_widget.combobox.get_active_id() == "test-blue"
    assert str(simple_widget.get_selected()) == "test-blue"


def test_action_widget():
    rule = make_rule("vm1", "vm2", "allow")
    action_widget = ActionWidget(rule.ACTION_CHOICES, VERB_DESCR, rule)

    assert action_widget.name_widget.get_visible()
    assert not action_widget.combobox.get_visible()

    action_widget.set_editable(True)
    assert not action_widget.name_widget.get_visible()
    assert action_widget.combobox.get_visible()


def test_action_widget_choices():
    # RuleSimple names:
    rule = make_rule("vm1", "vm2", "allow")
    action_widget = ActionWidget(rule.ACTION_CHOICES, None, rule)

    assert not action_widget.is_changed()
    assert str(action_widget.get_selected()) == "allow"
    assert (
        action_widget.name_widget.get_text()
        == RuleSimple.ACTION_CHOICES["allow"]
    )

    action_widget.set_editable(True)
    action_widget.combobox.set_active_id(RuleSimple.ACTION_CHOICES["ask"])
    assert action_widget.is_changed()

    # get back to ineditable, change should be discarded
    action_widget.set_editable(False)
    assert str(action_widget.get_selected()) == "allow"
    assert (
        action_widget.name_widget.get_text()
        == RuleSimple.ACTION_CHOICES["allow"]
    )
    assert (
        action_widget.combobox.get_active_id()
        == RuleSimple.ACTION_CHOICES["allow"]
    )
    assert not action_widget.is_changed()

    # let's change stuff for real
    action_widget.set_editable(True)
    action_widget.combobox.set_active_id(RuleSimple.ACTION_CHOICES["ask"])
    assert action_widget.is_changed()

    action_widget.save()
    action_widget.set_editable(False)

    assert not action_widget.is_changed()
    assert str(action_widget.get_selected()) == "ask"
    assert (
        action_widget.name_widget.get_text() == RuleSimple.ACTION_CHOICES["ask"]
    )
    assert (
        action_widget.combobox.get_active_id()
        == RuleSimple.ACTION_CHOICES["ask"]
    )


def test_action_widget_verbdescr():
    # RuleSimple names:
    rule = make_rule("vm1", "vm2", "ask")
    action_widget = ActionWidget(rule.ACTION_CHOICES, VERB_DESCR, rule)

    assert action_widget.additional_text_widget
    ask_text = action_widget.additional_text_widget.get_text()
    assert ask_text.endswith("ASK")

    action_widget.combobox.set_active_id(RuleSimple.ACTION_CHOICES["allow"])
    allow_text = action_widget.additional_text_widget.get_text()
    assert allow_text.endswith("ALLOW")

    action_widget.combobox.set_active_id(RuleSimple.ACTION_CHOICES["deny"])
    deny_text = action_widget.additional_text_widget.get_text()
    assert deny_text.endswith("DENY")

    assert len(ask_text) == len(allow_text) == len(deny_text)


def test_rule_row(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler, rule=rule, qapp=test_qapp
    )

    # it should start in a non-editable mode
    assert not rule_row.action_widget.combobox.get_visible()
    assert not rule_row.target_widget.combobox.get_visible()
    assert not rule_row.source_widget.combobox.get_visible()

    assert rule_row.action_widget.get_selected() == "ask"
    assert rule_row.source_widget.get_selected() == "test-blue"
    assert rule_row.target_widget.get_selected() == "test-red"

    # but when we set it to editable, it should work
    rule_row.set_edit_mode(True)
    assert rule_row.action_widget.combobox.get_visible()
    assert rule_row.target_widget.combobox.get_visible()
    assert rule_row.source_widget.combobox.get_visible()

    # when changes are made and reverted, they should be not shown
    rule_row.source_widget.model.select_value("test-vm")
    assert rule_row.source_widget.get_selected() == "test-vm"
    assert rule_row.is_changed()
    rule_row.revert()
    assert rule_row.source_widget.get_selected() == "test-blue"
    assert not rule_row.is_changed()

    # and let's try making some changes
    rule_row.set_edit_mode(True)
    rule_row.source_widget.model.select_value("test-vm")
    assert rule_row.is_changed()

    # the patch is necessary because the row will try to invalidate
    # sorting... all well and good, but it has no parent here
    with patch.object(rule_row, "get_parent"):
        assert rule_row.validate_and_save()
        assert str(rule_row.rule.raw_rule) == str(
            make_rule("test-vm", "test-red", "ask").raw_rule
        )


def test_rule_delete_new(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None

    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler, rule=rule, qapp=test_qapp, is_new_row=True
    )

    rule_row.set_edit_mode(True)

    with patch(
        "qubes_config.global_config.rule_list_widgets."
        "RuleListBoxRow._do_delete_self"
    ) as mock_delete:
        # check that rule will try to delete itself if exiting edit mode
        # with no changes
        rule_row.set_edit_mode(False)
        assert mock_delete.mock_calls

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler, rule=rule, qapp=test_qapp, is_new_row=True
    )

    rule_row.set_edit_mode(True)
    rule_row.source_widget.model.select_value("test-vm")
    with patch(
        "qubes_config.global_config.rule_list_widgets."
        "RuleListBoxRow._do_delete_self"
    ) as mock_delete, patch.object(rule_row, "get_parent"):
        # check that rule will NOT try to delete itself if saving with changes
        assert rule_row.validate_and_save()
        assert not mock_delete.mock_calls

    # and now for a harder problem: let's try an invalid rule; it should
    # not save itself and try to delete itself
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler, rule=rule, qapp=test_qapp, is_new_row=True
    )

    rule_row.set_edit_mode(True)
    rule_row.source_widget.model.select_value("test-vm")
    assert rule_row.is_changed()

    # the rule should not have exited the edit mode
    with patch.object(rule, "get_rule_errors", return_value="a"), patch(
        "qubes_config.global_config.rule_list_widgets.show_error"
    ) as mock_error:
        rule_row.validate_and_save()
        assert mock_error.mock_calls


def test_no_action_row(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = NoActionListBoxRow(
        parent_handler=mock_handler, rule=rule, qapp=test_qapp
    )

    assert not rule_row.action_widget.get_visible()
    rule_row.set_edit_mode(True)
    assert not rule_row.action_widget.get_visible()
    rule_row.set_edit_mode(False)
    assert not rule_row.action_widget.get_visible()


def test_limited_selection_row(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = FilteredListBoxRow(
        parent_handler=mock_handler,
        rule=rule,
        qapp=test_qapp,
        filter_target=lambda vm: "test" in vm.name,
    )
    vm_blue = test_qapp.domains["test-blue"]
    vm_red = test_qapp.domains["test-red"]
    vm_test = test_qapp.domains["test-vm"]
    vm_vault = test_qapp.domains["vault"]

    # target available vms should be limited:
    assert rule_row.target_widget.model.is_vm_available(vm_blue)
    assert rule_row.target_widget.model.is_vm_available(vm_red)
    assert rule_row.target_widget.model.is_vm_available(vm_test)
    assert not rule_row.target_widget.model.is_vm_available(vm_vault)


def test_rule_row_init_delete(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler,
        rule=rule,
        qapp=test_qapp,
        enable_delete=False,
    )

    # try to find a non-sensitive delete button
    for child in rule_row.target_widget.get_children():
        if isinstance(child, Gtk.Button) and not child.get_sensitive():
            break
    else:
        assert False  # failed to find a non-working delete button

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler,
        rule=rule,
        qapp=test_qapp,
        enable_delete=True,
    )

    # try to find a sensitive delete button
    for child in rule_row.target_widget.get_children():
        if isinstance(child, Gtk.Button) and child.get_sensitive():
            break
    else:
        assert False  # failed to find a non-working delete button


def test_rule_row_init_edit_vm(test_qapp):
    mock_handler = Mock(spec=PolicyHandler)
    mock_handler.verify_new_rule.return_value = None
    rule = make_rule("test-blue", "test-red", "ask")

    rule_row = RuleListBoxRow(
        parent_handler=mock_handler,
        rule=rule,
        qapp=test_qapp,
        enable_vm_edit=False,
    )

    assert not rule_row.source_widget.combobox.get_visible()
    assert not rule_row.target_widget.combobox.get_visible()
    rule_row.set_edit_mode(True)
    assert not rule_row.source_widget.combobox.get_visible()
    assert not rule_row.target_widget.combobox.get_visible()
    rule_row.set_edit_mode(False)
    assert not rule_row.source_widget.combobox.get_visible()
    assert not rule_row.target_widget.combobox.get_visible()
