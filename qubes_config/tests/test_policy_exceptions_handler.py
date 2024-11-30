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
from unittest.mock import patch

from ..global_config.policy_manager import PolicyManager
from ..global_config.policy_exceptions_handler import DispvmExceptionHandler
from .test_policy_handler import add_rule
from ..widgets.utils import compare_rule_lists

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk

# policyexctest  -> missing tests!
# dispvmexctest


show_dialog_with_icon_path = (
    "qubes_config.global_config.policy_handler.show_dialog_with_icon"
)


def test_policy_exc_handler_empty(test_builder, test_qapp, test_policy_manager):
    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="Test2",
        policy_file_name="test",
    )

    # this should have completely empty policy
    assert not handler.list_handler.current_rules


def test_policy_exc_handler_load_state(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny
TestService * test-blue @dispvm ask default_target=@dispvm:default-dvm"""
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert handler.list_handler.current_rules
    rules = [
        str(rule).replace("\t", " ")
        for rule in handler.list_handler.current_rules
    ]
    expected_rules = [
        rule.replace("\t", " ") for rule in current_policy.split("\n")
    ]
    assert sorted(rules) == sorted(expected_rules)


def test_policy_exc_add_rule(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    add_rule(
        handler.list_handler,
        source="test-blue",
        action="ask",
        target="default-dvm",
    )

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny
TestService * test-blue @dispvm ask default_target=@dispvm:default-dvm"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )

    handler.save()
    assert compare_rule_lists(
        test_policy_manager.get_rules_from_filename("c-test", "")[0],
        expected_policy_rules,
    )


def test_policy_exc_add_rule_error(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # error should have occurred
    add_rule(
        handler.list_handler,
        source="test-red",
        target="default-dvm",
        action="allow",
        expect_error=True,
    )

    # no superfluous rules were added
    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # but the row is being edited
    edited_row = None
    for row in handler.list_handler.current_rows:
        if row.editing:
            if edited_row:
                assert False  # no two rows can be edited at the same time
            edited_row = row

    # and it can be fixed
    assert edited_row
    edited_row.source_widget.model.select_value("test-blue")
    edited_row.validate_and_save()

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny
TestService * test-blue @dispvm allow target=@dispvm:default-dvm"""

    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )


def test_policy_exc_add_rule_twice(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # click add_rule twice
    handler.list_handler.add_button.clicked()
    handler.list_handler.add_button.clicked()

    # no superfluous rules were yet added
    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # but there is a singular row is being edited
    edited_row = None
    for row in handler.list_handler.current_rows:
        if row.editing:
            if edited_row:
                assert False  # no two rows can be edited at the same time
            edited_row = row

    # but if I try to edit another one, the previous one will vanish, because
    # it was unsaved
    for row in handler.list_handler.current_rows:
        if not row.editing:
            row.activate()
            row.validate_and_save()
    # now no rows are edited
    for row in handler.list_handler.current_rows:
        if row.editing:
            assert False  # wrong, we just closed an edited row

    # no superfluous rules were added
    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )


def test_policy_exc_edit_rule(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    for row in handler.list_handler.current_rows:
        if row.rule.source == "test-red":
            row.activate()
            assert row.editing
            # not visible combobox - we have deny here
            assert not row.target_widget.combobox.get_visible()
            row.action_widget.model.select_value("allow")
            # now it should be visible
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("default-dvm")
            row.validate_and_save()
            break
    else:
        assert False  # expected rule to edit not found!

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm allow target=@dispvm:default-dvm"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )


def test_policy_exc_edit_double_click(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    for row in handler.list_handler.current_rows:
        if row.rule.source == "test-red":
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("@dispvm")
            # second activation cannot cause the changes to be discarded
            with patch(show_dialog_with_icon_path) as mock_ask:
                row.activate()
                row.activate()
                assert not mock_ask.mock_calls
            row.validate_and_save()
            break
    else:
        assert False  # expected rule to edit not found!

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )


def test_policy_exc_edit_cancel(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    for row in handler.list_handler.current_rows:
        if row.rule.source == "test-red":
            found_row = row
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("@dispvm")
            break
    else:
        assert False  # expected rule to edit not found!

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # click another row, dismiss message
    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        for row in handler.list_handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    # now do the same, but do not dismiss the message
    for row in handler.list_handler.current_rows:
        if row.rule.source == "test-red":
            found_row = row
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            # check the old selection was reset
            assert str(row.target_widget.model.get_selected()) == "default-dvm"
            row.target_widget.model.select_value("@dispvm")
            break
    else:
        assert False  # expected rule to edit not found!

    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        for row in handler.list_handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )


def test_policy_exc_close_all_fail(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    for row in handler.list_handler.current_rows:
        if row.rule.source == "test-red":
            found_row = row
            row.activate()
            assert row.editing
            assert row.source_widget.combobox.get_visible()
            row.source_widget.model.select_value("test-vm")
            break
    else:
        assert False  # expected rule to edit not found!

    # click another row, but, say you want to save changes, fail
    with patch(show_dialog_with_icon_path) as mock_ask, patch(
        "qubes_config.global_config.rule_list_widgets.show_error"
    ) as mock_error:
        mock_ask.return_value = Gtk.ResponseType.YES
        for row in handler.list_handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls
        assert mock_error.mock_calls

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )


def test_policy_handler_reset(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    add_rule(handler.list_handler, source="test-blue", action="deny")

    expected_policy = """TestService * test-vm @dispvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm
TestService * test-blue @dispvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(
        handler.list_handler.current_rules, expected_policy_rules
    )

    handler.reset()
    assert compare_rule_lists(
        handler.list_handler.current_rules, current_policy_rules
    )

    handler.save()
    assert compare_rule_lists(
        test_policy_manager.get_rules_from_filename("c-test", "")[0],
        current_policy_rules,
    )


def test_policy_exc_get_unsupported(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm @anyvm allow target=@dispvm
TestService * test-red @dispvm ask default_target=@dispvm:default-dvm"""
    # current_policy_rules = test_policy_manager.text_to_rules(current_policy)
    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = DispvmExceptionHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="dispvmexctest",
        policy_manager=test_policy_manager,
        service_name="TestService",
        policy_file_name="c-test",
    )

    assert not handler.get_unsaved()
    assert handler.list_handler.error_handler.get_errors()
