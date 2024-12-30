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
# pylint: disable=missing-module-docstring,missing-function-docstring
# pylint: disable=missing-class-docstring

from unittest.mock import patch

from ..policy_editor.policy_editor import PolicyEditor

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


def test_open_file(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )


def test_open_file_not_found(test_policy_client):
    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.CANCEL
        policy_editor = PolicyEditor("new-file", test_policy_client)
        with patch.object(policy_editor, "_quit") as mock_quit:
            policy_editor.perform_setup()

            # should have quit
            assert (
                policy_editor.source_buffer.get_text(
                    policy_editor.source_buffer.get_start_iter(),
                    policy_editor.source_buffer.get_end_iter(),
                    False,
                )
                == ""
            )
            assert mock_quit.call_count == 1

    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        policy_editor = PolicyEditor("new-file", test_policy_client)
        with patch.object(policy_editor, "_quit") as mock_quit:
            policy_editor.perform_setup()

            # should not have quit, but file is not editable
            assert not policy_editor.source_view.get_sensitive()
            assert mock_quit.call_count == 0

    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        policy_editor = PolicyEditor("new-file", test_policy_client)
        with patch.object(policy_editor, "_quit") as mock_quit:
            policy_editor.perform_setup()

            # should not have quit, file is empty and editable
            assert policy_editor.source_view.get_sensitive()
            assert (
                policy_editor.source_buffer.get_text(
                    policy_editor.source_buffer.get_start_iter(),
                    policy_editor.source_buffer.get_end_iter(),
                    False,
                )
                == ""
            )
            assert mock_quit.call_count == 0


def test_detect_changes(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert not policy_editor.builder.get_object("button_save").get_sensitive()
    assert not policy_editor.builder.get_object(
        "button_save_exit"
    ).get_sensitive()
    assert policy_editor.error_info.get_style_context().has_class("error_ok")
    assert not policy_editor.error_info.get_style_context().has_class(
        "error_bad"
    )

    policy_editor.source_buffer.set_text("Test * @anyvm @anyvm allow")

    assert policy_editor.builder.get_object("button_save").get_sensitive()
    assert policy_editor.builder.get_object("button_save_exit").get_sensitive()
    assert policy_editor.error_info.get_style_context().has_class("error_ok")
    assert not policy_editor.error_info.get_style_context().has_class(
        "error_bad"
    )

    policy_editor.source_buffer.set_text("Test * @anyvm @anyvm andruty")

    assert not policy_editor.builder.get_object("button_save").get_sensitive()
    assert not policy_editor.builder.get_object(
        "button_save_exit"
    ).get_sensitive()
    assert policy_editor.error_info.get_style_context().has_class("error_bad")
    assert not policy_editor.error_info.get_style_context().has_class(
        "error_ok"
    )

    policy_editor.source_buffer.set_text("Test +any work @anyvm allow")

    assert policy_editor.builder.get_object("button_save").get_sensitive()
    assert policy_editor.builder.get_object("button_save_exit").get_sensitive()
    assert policy_editor.error_info.get_style_context().has_class("error_ok")
    assert not policy_editor.error_info.get_style_context().has_class(
        "error_bad"
    )


def test_open_another_file(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )

    assert not policy_editor.file_select_handler.dialog_window.get_visible()
    policy_editor.action_items["open"].activate()
    assert policy_editor.file_select_handler.dialog_window.get_visible()

    for row in policy_editor.file_select_handler.file_list.get_children():
        if row.filename == "b-test":
            policy_editor.file_select_handler.file_list.select_row(row)
            break

    policy_editor.file_select_handler.ok_button.clicked()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == """Test * test-vm @anyvm allow\n
Test * test-red test-blue deny"""
    )
    assert not policy_editor.builder.get_object("button_save").get_sensitive()
    assert not policy_editor.builder.get_object(
        "button_save_exit"
    ).get_sensitive()


def test_save_changes(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )
    assert test_policy_client.files["a-test"] == "Test * @anyvm @anyvm deny"

    policy_editor.source_buffer.set_text("Test * @anyvm @anyvm allow")
    policy_editor.action_items["save"].activate()

    assert test_policy_client.files["a-test"] == "Test * @anyvm @anyvm allow"
    assert not policy_editor.builder.get_object("button_save").get_sensitive()
    assert not policy_editor.builder.get_object(
        "button_save_exit"
    ).get_sensitive()
    assert policy_editor.error_info.get_style_context().has_class("error_ok")
    assert not policy_editor.error_info.get_style_context().has_class(
        "error_bad"
    )


def test_save_from_new(test_policy_client):
    policy_editor = PolicyEditor("c-test", test_policy_client)
    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        policy_editor.perform_setup()
    assert "c-test" not in test_policy_client.files

    policy_editor.source_buffer.set_modified(True)
    policy_editor.source_buffer.set_text("Test * vm1 vm2 allow")

    assert policy_editor.builder.get_object("button_save").get_sensitive()
    policy_editor.action_items["save"].activate()
    assert test_policy_client.files["c-test"] == "Test * vm1 vm2 allow"


def test_deselect_file_on_hide(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    policy_editor.action_items["open"].activate()
    assert policy_editor.file_select_handler.dialog_window.get_visible()

    for row in policy_editor.file_select_handler.file_list.get_children():
        if row.filename == "b-test":
            policy_editor.file_select_handler.file_list.select_row(row)
            break

    policy_editor.file_select_handler.cancel_button.clicked()
    assert not policy_editor.file_select_handler.dialog_window.get_visible()

    policy_editor.action_items["open"].activate()
    assert policy_editor.file_select_handler.dialog_window.get_visible()
    assert (
        policy_editor.file_select_handler.file_list.get_selected_row() is None
    )
    policy_editor.file_select_handler.cancel_button.clicked()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )


def test_new_file_action(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    with patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.MessageDialog.run"
    ) as mock_run, patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.Entry.get_text"
    ) as mock_get:
        mock_get.return_value = "new-file"
        mock_run.return_value = Gtk.ResponseType.OK
        policy_editor.action_items["new"].activate()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == ""
    )

    policy_editor.source_buffer.set_modified(True)
    policy_editor.source_buffer.set_text("Test * vm1 vm2 allow")

    assert policy_editor.builder.get_object("button_save").get_sensitive()
    policy_editor.action_items["save"].activate()
    assert test_policy_client.files["new-file"] == "Test * vm1 vm2 allow"


def test_new_file_action_invalid(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    policy_editor.source_buffer.set_text("changed.service * vm1 vm2 allow")

    with patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.MessageDialog.run"
    ) as mock_run, patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.Entry.get_text"
    ) as mock_get, patch(
        "qubes_config.policy_editor.policy_editor.show_error"
    ), patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO  # don't save changes
        mock_get.return_value = "???!!!"
        mock_run.return_value = Gtk.ResponseType.OK
        policy_editor.action_items["new"].activate()

    assert policy_editor.filename == "a-test"
    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "changed.service * vm1 vm2 allow"
    )

    with patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.MessageDialog.run"
    ) as mock_run, patch(
        "qubes_config.policy_editor.policy_editor." "Gtk.Entry.get_text"
    ) as mock_get, patch(
        "qubes_config.policy_editor.policy_editor.show_error"
    ), patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO  # don't save changes
        mock_get.return_value = "b-test"
        mock_run.return_value = Gtk.ResponseType.OK
        policy_editor.action_items["new"].activate()

    assert policy_editor.filename == "a-test"
    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "changed.service * vm1 vm2 allow"
    )


def test_unsaved_exit(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )

    policy_editor.source_buffer.set_text("Test * vm1 vm2 allow")

    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask, patch.object(policy_editor, "_quit") as mock_quit:
        mock_ask.return_value = Gtk.ResponseType.CANCEL
        policy_editor.builder.get_object("button_cancel").clicked()
        # no quit, no save
        assert mock_quit.call_count == 0
        assert test_policy_client.files["a-test"] == "Test * @anyvm @anyvm deny"

    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask, patch.object(policy_editor, "_quit") as mock_quit:
        mock_ask.return_value = Gtk.ResponseType.NO
        policy_editor.builder.get_object("button_cancel").clicked()
        # quit, no save
        assert mock_quit.call_count == 1
        assert test_policy_client.files["a-test"] == "Test * @anyvm @anyvm deny"


def test_unsaved_exit_save(test_policy_client):
    policy_editor = PolicyEditor("a-test", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "Test * @anyvm @anyvm deny"
    )

    policy_editor.source_buffer.set_text("Test * vm1 vm2 allow")

    with patch(
        "qubes_config.policy_editor.policy_editor.ask_question"
    ) as mock_ask, patch.object(policy_editor, "_quit") as mock_quit:
        mock_ask.return_value = Gtk.ResponseType.YES
        policy_editor.builder.get_object("button_cancel").clicked()
        # quit, save
        assert mock_quit.call_count == 1
        assert test_policy_client.files["a-test"] == "Test * vm1 vm2 allow"


def test_includes(test_policy_client):
    policy_editor = PolicyEditor("include/include-1", test_policy_client)
    policy_editor.perform_setup()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == "!include include/include-2"
    )

    policy_editor.source_buffer.set_text(
        "!include include/include-2\n" "Test * vm1 vm2 allow"
    )

    policy_editor.action_items["save"].activate()

    assert (
        test_policy_client.include_files["include-1"]
        == "!include include/include-2\nTest * vm1 vm2 allow"
    )

    # open another
    policy_editor.action_items["open"].activate()
    assert policy_editor.file_select_handler.dialog_window.get_visible()

    for row in policy_editor.file_select_handler.file_list.get_children():
        if row.filename == "include/include-2":
            policy_editor.file_select_handler.file_list.select_row(row)
            break

    policy_editor.file_select_handler.ok_button.clicked()

    assert (
        policy_editor.source_buffer.get_text(
            policy_editor.source_buffer.get_start_iter(),
            policy_editor.source_buffer.get_end_iter(),
            False,
        )
        == """Test.Test +argument @anyvm @anyvm allow"""
    )
