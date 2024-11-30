# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Marta Marczykowska-Górecka
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
# pylint: disable=missing-module-docstring,missing-function-docstring
from unittest.mock import patch

from ..global_config.policy_manager import PolicyManager
from ..global_config.policy_handler import PolicyHandler, VMSubsetPolicyHandler
from ..global_config.policy_rules import (
    SimpleVerbDescription,
    RuleSimple,
    RuleTargeted,
)
from ..widgets.utils import compare_rule_lists

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


show_dialog_with_icon_path = (
    "qubes_config.global_config.policy_handler.show_dialog_with_icon"
)


def add_rule(
    handler, source=None, target=None, action=None, expect_error: bool = False
):
    # attempt to add a new rule
    handler.add_button.clicked()
    # find the clicked row
    for row in handler.current_rows:
        if row.editing:
            if source:
                assert row.source_widget.combobox.get_visible()
                row.source_widget.model.select_value(source)
            if target:
                assert row.target_widget.combobox.get_visible()
                row.target_widget.model.select_value(target)
            if action:
                assert row.action_widget.combobox.get_visible()
                row.action_widget.model.select_value(action)
            if expect_error:
                with patch(
                    "qubes_config.global_config.rule_list_widgets.show_error"
                ) as mock_error:
                    assert not mock_error.mock_calls
                    row.validate_and_save()
                    assert mock_error.mock_calls
            else:
                row.validate_and_save()
            break
    else:
        assert False


def get_raw_rules(handler: PolicyHandler):
    text_buffer = handler.raw_handler.raw_text.get_buffer()
    raw_text = text_buffer.get_text(
        text_buffer.get_start_iter(), text_buffer.get_end_iter(), False
    )
    rules = handler.policy_manager.text_to_rules(raw_text)
    return rules


def test_policy_handler_empty(test_builder, test_qapp, test_policy_manager):
    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy="",
        service_name="Test2",
        policy_file_name="test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert not handler.current_rules
    assert handler.disable_radio.get_active()


def test_policy_handler_default_policy(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert compare_rule_lists(handler.current_rules, default_policy_rules)
    assert handler.disable_radio.get_active()
    assert not handler.add_button.get_sensitive()


def test_policy_handler_non_default_policy(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    current_policy = """TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    assert handler.enable_radio.get_active()
    assert compare_rule_lists(handler.current_rules, current_policy_rules)

    # when we switch to default, current_rules should be default
    handler.disable_radio.set_active(True)
    assert compare_rule_lists(handler.current_rules, default_policy_rules)

    # and when we switch to custom, back to custom
    handler.enable_radio.set_active(True)
    assert compare_rule_lists(handler.current_rules, current_policy_rules)


def test_policy_handler_enforce_deny_all(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""

    current_policy = """TestService * test-vm test-red allow"""
    current_policy_with_deny = """TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    current_policy_rules_with_deny = test_policy_manager.text_to_rules(
        current_policy_with_deny
    )

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert handler.enable_radio.get_active()
    assert compare_rule_lists(
        handler.current_rules, current_policy_rules_with_deny
    )


def test_policy_handler_add_rule(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert compare_rule_lists(handler.current_rules, default_policy_rules)
    assert handler.disable_radio.get_active()

    handler.enable_radio.set_active(True)

    add_rule(handler, source="test-red", action="allow")

    expected_policy = """TestService * test-red @anyvm allow
TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(handler.current_rules, expected_policy_rules)

    handler.save()
    assert compare_rule_lists(
        test_policy_manager.get_rules_from_filename("c-test", "")[0],
        expected_policy_rules,
    )


def test_policy_handler_add_rule_error(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert compare_rule_lists(handler.current_rules, default_policy_rules)
    assert handler.disable_radio.get_active()

    handler.enable_radio.set_active(True)

    # error should have occurred
    add_rule(
        handler,
        source="test-vm",
        target="test-blue",
        action="allow",
        expect_error=True,
    )
    # no superfluous rules were added
    assert compare_rule_lists(handler.current_rules, default_policy_rules)

    # but the row is being edited
    edited_row = None
    for row in handler.current_rows:
        if row.editing:
            if edited_row:
                assert False  # no two rows can be edited at the same time
            edited_row = row

    # and it can be fixed
    assert edited_row
    edited_row.target_widget.model.select_value("test-red")
    edited_row.validate_and_save()

    expected_policy = """TestService * test-vm test-blue allow
TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_policy_handler_add_rule_twice(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    handler.enable_radio.set_active(True)

    # click add_rule twice
    handler.add_button.clicked()
    handler.add_button.clicked()

    # no superfluous rules were yet added
    assert compare_rule_lists(handler.current_rules, default_policy_rules)

    # but there is a singular row is being edited
    edited_row = None
    for row in handler.current_rows:
        if row.editing:
            if edited_row:
                assert False  # no two rows can be edited at the same time
            edited_row = row

    # but if I try to edit another one, the previous one will vanish, because
    # it was unsaved
    for row in handler.current_rows:
        if not row.editing:
            row.activate()
            row.validate_and_save()
    # now no rows are edited
    for row in handler.current_rows:
        if row.editing:
            assert False  # wrong, we just closed an edited row

    # no superfluous rules were added
    assert compare_rule_lists(handler.current_rules, default_policy_rules)


def test_policy_handler_edit_rule(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    handler.enable_radio.set_active(True)

    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("test-red")
            row.validate_and_save()
            break
    else:
        assert False  # expected rule to edit not found!

    expected_policy = """TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_policy_handler_edit_double_click(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    handler.enable_radio.set_active(True)

    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("test-red")
            # second activation cannot cause the changes to be discarded
            with patch(show_dialog_with_icon_path) as mock_ask:
                row.activate()
                row.activate()
                assert not mock_ask.mock_calls
            row.validate_and_save()
            break
    else:
        assert False  # expected rule to edit not found!

    expected_policy = """TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_policy_handler_edit_cancel(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    handler.enable_radio.set_active(True)

    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            found_row = row
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("test-red")
            break
    else:
        assert False  # expected rule to edit not found!

    assert compare_rule_lists(handler.current_rules, default_policy_rules)

    # click another row, dismiss message
    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        for row in handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls

    assert compare_rule_lists(handler.current_rules, default_policy_rules)

    # now do the same, but do not dismiss the message
    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            found_row = row
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            # check the old selection was reset
            assert str(row.target_widget.model.get_selected()) == "test-blue"
            row.target_widget.model.select_value("test-red")
            break
    else:
        assert False  # expected rule to edit not found!

    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        for row in handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls

    expected_policy = """TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_policy_handler_close_all_fail(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * test-vm test-blue allow
TestService * test-vm test-red allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    handler.enable_radio.set_active(True)

    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            found_row = row
            row.activate()
            assert row.editing
            assert row.target_widget.combobox.get_visible()
            row.target_widget.model.select_value("test-red")
            break
    else:
        assert False  # expected rule to edit not found!

    # click another row, but, say you want to save changes, fail
    with patch(show_dialog_with_icon_path) as mock_ask, patch(
        "qubes_config.global_config.rule_list_widgets.show_error"
    ) as mock_error:
        mock_ask.return_value = Gtk.ResponseType.YES
        for row in handler.current_rows:
            if row != found_row:
                row.activate()
                break
        assert mock_ask.mock_calls
        assert mock_error.mock_calls

    assert compare_rule_lists(handler.current_rules, default_policy_rules)


def test_policy_handler_reset(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # this should have completely empty policy, enabled default policy
    assert compare_rule_lists(handler.current_rules, default_policy_rules)
    assert handler.disable_radio.get_active()

    handler.enable_radio.set_active(True)

    add_rule(handler, source="test-red", action="allow")

    expected_policy = """TestService * test-red @anyvm allow
TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(handler.current_rules, expected_policy_rules)

    handler.reset()
    assert compare_rule_lists(handler.current_rules, default_policy_rules)
    assert handler.disable_radio.get_active()

    handler.save()
    assert compare_rule_lists(
        test_policy_manager.get_rules_from_filename("c-test", "")[0],
        default_policy_rules,
    )


def test_policy_handler_view_raw(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
    TestService * @anyvm @anyvm deny"""
    default_policy_rules = test_policy_manager.text_to_rules(default_policy)

    current_policy = """TestService * test-vm test-red allow
    TestService * @anyvm @anyvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    assert compare_rule_lists(get_raw_rules(handler), current_policy_rules)
    handler.disable_radio.set_active(True)
    assert compare_rule_lists(get_raw_rules(handler), default_policy_rules)
    handler.enable_radio.set_active(True)
    assert compare_rule_lists(get_raw_rules(handler), current_policy_rules)

    add_rule(handler, "test-vm", "@anyvm", "ask")

    expected_policy = """TestService * test-vm test-red allow
TestService * test-vm @anyvm ask
TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    assert compare_rule_lists(get_raw_rules(handler), expected_policy_rules)


def test_policy_handler_edit_raw(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
    TestService * @anyvm @anyvm deny"""

    current_policy = """TestService * test-vm test-red allow
    TestService * @anyvm @anyvm deny"""

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    expected_policy = """TestService * test-vm test-red allow
    TestService * test-vm @anyvm ask
    TestService * @anyvm @anyvm deny"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)

    handler.raw_handler.text_buffer.set_text(expected_policy)
    handler.raw_handler.raw_save.clicked()

    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_policy_handler_edit_raw_error(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
    TestService * @anyvm @anyvm deny"""
    current_policy = """TestService * test-vm test-red allow
    TestService * @anyvm @anyvm deny"""
    current_policy_rules = test_policy_manager.text_to_rules(current_policy)

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    expected_policy = """TestService * test-vm test-red escargot
    TestService * test-vm @anyvm framboise
    TestService * @anyvm @anyvm deny"""

    handler.raw_handler.text_buffer.set_text(expected_policy)
    with patch(
        "qubes_config.global_config.policy_handler.show_error"
    ) as mock_error:
        assert not mock_error.mock_calls
        handler.raw_handler.raw_save.clicked()
        assert mock_error.mock_calls

    assert compare_rule_lists(handler.current_rules, current_policy_rules)

    expected_policy = """TestService * test-vm test-red allow
    TestService * test-vm @anyvm allow
    TestService * @anyvm @anyvm deny"""

    handler.raw_handler.text_buffer.set_text(expected_policy)
    handler.raw_handler.raw_cancel.clicked()

    assert compare_rule_lists(handler.current_rules, current_policy_rules)


def test_policy_handler_edit_raw_close(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
    TestService * @anyvm @anyvm deny"""
    current_policy = """TestService * test-vm test-red allow
    TestService * @anyvm @anyvm deny"""

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    # start adding a row
    handler.add_button.clicked()

    # raw is hidden
    assert not handler.raw_handler.raw_box.get_visible()

    for row in handler.current_rows:
        if row.editing:
            break
    else:
        assert False  # somehow the row didn't get added, bad

    # but now expand raw policy
    handler.raw_handler.raw_event_button.emit("clicked")
    for row in handler.current_rows:
        if row.editing:
            assert False  # the row should have closed
    assert handler.raw_handler.raw_box.get_visible()


def test_policy_handler_sorting(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
    TestService * @anyvm @anyvm deny"""
    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    raw_policy = """
TestService * @anyvm @anyvm deny
TestService * @type:TemplateVM @anyvm ask
TestService * test-vm @anyvm deny
TestService * test-vm test-red allow
TestService * test-vm @type:TemplateVM ask
TestService * test-red test-vm deny
TestService * test-red @anyvm allow
"""
    sensibly_sorted_policy = """
TestService * test-red test-vm deny
TestService * test-red @anyvm allow
TestService * test-vm test-red allow
TestService * test-vm @type:TemplateVM ask
TestService * test-vm @anyvm deny
TestService * @type:TemplateVM @anyvm ask
TestService * @anyvm @anyvm deny
"""
    expected_rules = test_policy_manager.text_to_rules(sensibly_sorted_policy)

    handler.raw_handler.text_buffer.set_text(raw_policy)
    handler.raw_handler.raw_save.clicked()

    assert compare_rule_lists(handler.current_rules, expected_rules)

    # but also raw should have been updated
    assert compare_rule_lists(get_raw_rules(handler), expected_rules)


def test_policy_handler_get_unsaved(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """TestService * test-vm test-blue allow
TestService * @anyvm @anyvm deny"""

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()

    handler.enable_radio.set_active(True)
    # still not unsaved, because actually everything is the same...
    assert not handler.get_unsaved()

    # add a rule
    add_rule(handler, "test-vm", "test-red", "deny")

    assert handler.get_unsaved()

    # remove the rule added
    for row in handler.current_rows:
        if row.rule.target == "test-red":
            row._do_delete_self(force=True)  # pylint: disable=protected-access
            break
    else:
        assert False  # failed to find the row we just added

    # no longer unsaved, because actually everything is the same
    assert not handler.get_unsaved()

    # modify a rule and save
    for row in handler.current_rows:
        if row.rule.target == "test-blue":
            row.target_widget.model.select_value("test-red")
            row.validate_and_save()
    assert handler.get_unsaved()
    handler.save()
    assert not handler.get_unsaved()


def test_policy_handler_get_unsaved_unsupported(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * test-vm test-blue allow target=test-red
TestService * @anyvm @anyvm deny"""

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy="",
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()
    assert handler.error_handler.get_errors()

    assert handler.enable_radio.get_active()
    handler.disable_radio.set_active(True)
    assert handler.get_unsaved()

    handler.enable_radio.set_active(True)

    assert not handler.get_unsaved()


####### Subset handler


def test_subset_handler(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * @anyvm test-blue allow"""

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()
    handler.enable_radio.set_active(True)

    # add main rule
    handler.add_select_button.clicked()
    assert handler.add_select_box.get_visible()
    handler.select_qube_model.select_value("vault")
    with patch(
        "qubes_config.global_config.policy_handler.ask_question"
    ) as mock_ask:
        handler.add_select_confirm.clicked()
        # vault is not networked
        assert not mock_ask.mock_calls

    expected_policy = """
TestService * @anyvm test-blue allow
TestService * @anyvm vault ask"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)

    # and another
    handler.add_select_button.clicked()
    assert handler.add_select_box.get_visible()
    handler.select_qube_model.select_value("test-red")
    with patch(
        "qubes_config.global_config.policy_handler.ask_question"
    ) as mock_ask:
        handler.add_select_confirm.clicked()
        # test-red is networked
        assert mock_ask.mock_calls

    expected_policy = """
TestService * @anyvm test-blue allow
TestService * @anyvm test-red ask
TestService * @anyvm vault ask"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_subset_handler_get_unsaved_unsupported(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    current_policy = """TestService * @anyvm test-blue allow target=test=red"""

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = PolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy="",
        service_name="TestService",
        policy_file_name="c-test",
        verb_description=SimpleVerbDescription({}),
        rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()
    assert handler.error_handler.get_errors()

    assert handler.enable_radio.get_active()
    handler.disable_radio.set_active(True)
    assert handler.get_unsaved()

    handler.enable_radio.set_active(True)

    assert not handler.get_unsaved()


def test_subset_handler_limited_choice(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * @anyvm test-blue allow
TestService * @anyvm test-red allow"""

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()
    handler.enable_radio.set_active(True)

    # available set should be limited
    handler.add_button.clicked()
    for row in handler.current_rows:
        if row.editing:
            test_blue = test_qapp.domains["test-blue"]
            test_red = test_qapp.domains["test-red"]
            vault = test_qapp.domains["vault"]
            assert row.target_widget.model.is_vm_available(test_blue)
            assert row.target_widget.model.is_vm_available(test_red)
            assert not row.target_widget.model.is_vm_available(vault)
            row.source_widget.model.select_value("test-vm")
            row.target_widget.model.select_value("test-blue")
            row.action_widget.model.select_value("deny")
            row.validate_and_save()
            edited_row = row
            break
    else:
        assert False  # row somehow not found

    expected_policy = """
TestService * test-vm test-blue deny
TestService * @anyvm test-blue allow
TestService * @anyvm test-red allow"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)

    # wait, I changed my mind...
    edited_row.activate()

    # changed my mind again, let's add a new key qube
    handler.add_select_button.clicked()
    assert handler.add_select_box.get_visible()
    # check that previous row is no longer being edited
    assert not edited_row.editing

    handler.select_qube_model.select_value("vault")
    handler.add_select_confirm.clicked()

    # check that choice was updated
    handler.add_button.clicked()
    for row in handler.current_rows:
        if row.editing:
            test_vm = test_qapp.domains["test-vm"]
            test_blue = test_qapp.domains["test-blue"]
            test_red = test_qapp.domains["test-red"]
            vault = test_qapp.domains["vault"]
            assert row.target_widget.model.is_vm_available(test_blue)
            assert row.target_widget.model.is_vm_available(test_red)
            assert row.target_widget.model.is_vm_available(vault)
            assert not row.target_widget.model.is_vm_available(test_vm)
            break
    else:
        assert False  # row somehow not found

    # never mind that, let's add more key qubes
    handler.add_select_button.clicked()
    # or not
    handler.add_select_cancel.clicked()
    # it should not have been added
    expected_policy = """
TestService * test-vm test-blue deny
TestService * @anyvm test-blue allow
TestService * @anyvm test-red allow
TestService * @anyvm vault ask"""
    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_subset_handler_remove_choice(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * test-vm test-blue deny
TestService * @anyvm test-blue allow
TestService * @anyvm vault ask"""

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleSimple,
    )

    assert not handler.get_unsaved()
    handler.enable_radio.set_active(True)

    # remove vault from key qubes
    for row in handler.main_list_box.get_children():
        if row.rule.target == "vault":
            with patch(
                "qubes_config.global_config.rule_list_widgets.ask_question"
            ) as mock_ask:
                mock_ask.return_value = Gtk.ResponseType.YES
                row._delete_self()  # pylint: disable=protected-access
                assert mock_ask.mock_calls

    # available set should be more limited
    handler.add_button.clicked()
    for row in handler.current_rows:
        if row.editing:
            test_blue = test_qapp.domains["test-blue"]
            test_red = test_qapp.domains["test-red"]
            vault = test_qapp.domains["vault"]
            assert row.target_widget.model.is_vm_available(test_blue)
            assert not row.target_widget.model.is_vm_available(test_red)
            assert not row.target_widget.model.is_vm_available(vault)
            break
    else:
        assert False  # row somehow not found

    # remove test blue too
    for row in handler.main_list_box.get_children():
        if row.rule.target == "test-blue":
            row._do_delete_self(force=True)  # pylint: disable=protected-access

    # there should be nothing left
    assert compare_rule_lists(handler.current_rules, [])


def test_subset_handler_duplicates(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * @anyvm vault ask"""

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleTargeted,
    )

    handler.enable_radio.set_active(True)
    add_rule(handler, source="test-blue", target="vault", action="allow")
    add_rule(handler, source="test-red", target="vault", action="ask")

    expected_policy = """
TestService * test-blue @default allow target=vault
TestService * test-blue vault allow
TestService * test-red @default ask default_target=vault
TestService * test-red vault ask
TestService * @anyvm vault ask
"""

    expected_policy_rules = test_policy_manager.text_to_rules(expected_policy)
    assert compare_rule_lists(handler.current_rules, expected_policy_rules)


def test_subset_handler_duplicates_load(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
TestService * test-blue @default allow target=vault
TestService * test-blue vault allow
TestService * @anyvm vault ask
"""

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleTargeted,
    )

    handler.enable_radio.set_active(True)

    # should only have one exception visible, not two
    assert len(handler.exception_list_box.get_children()) == 1


def test_subset_handler_unsupported(
    test_builder, test_qapp, test_policy_manager: PolicyManager
):
    default_policy = """
"""
    current_policy = """TestService * test-blue @default allow target=vault
TestService * test-blue vault allow
TestService * @anyvm vault allow target=test-blue
"""

    test_policy_manager.policy_client.policy_replace(
        "c-test", current_policy, "any"
    )

    handler = VMSubsetPolicyHandler(
        qapp=test_qapp,
        gtk_builder=test_builder,
        prefix="policytest",
        policy_manager=test_policy_manager,
        default_policy=default_policy,
        service_name="TestService",
        policy_file_name="c-test",
        main_verb_description=SimpleVerbDescription({}),
        main_rule_class=RuleSimple,
        exception_verb_description=SimpleVerbDescription({}),
        exception_rule_class=RuleTargeted,
    )

    assert handler.error_handler.error_box.get_visible()
    # no rules should have been loaded
    assert not handler.current_rules
