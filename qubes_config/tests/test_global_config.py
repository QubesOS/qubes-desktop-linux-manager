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

import time
from unittest.mock import patch

from ..global_config.global_config import (
    GlobalConfig,
    ClipboardHandler,
    FileAccessHandler,
)
from ..global_config.basics_handler import BasicSettingsHandler

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk

# this entire file has a peculiar arrangement with mock signal registration:
# to enable tests from this file to run alone,
# a test_builder fixture is requested because it will try to register
# signals in "test" mode


show_dialog_with_icon_path = (
    "qubes_config.global_config.global_config.show_dialog_with_icon"
)


@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_init(
    mock_error, mock_subprocess, test_qapp, test_policy_manager, test_builder
):
    mock_subprocess.return_value = b""
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert test_builder

    # switch across pages, nothing should happen
    while (
        app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()
        ).get_name()
        != "thisdevice"
    ):
        app.main_notebook.next_page()

    # find clipboard
    app.main_notebook.set_current_page(0)

    while (
        app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()
        ).get_name()
        != "clipboard"
    ):
        app.main_notebook.next_page()

    clipboard_page_num = app.main_notebook.get_current_page()
    handler = app.get_current_page()
    assert isinstance(handler, ClipboardHandler)

    assert handler.copy_combo.get_active_id() == "default (Ctrl+Shift+C)"
    handler.copy_combo.set_active_id("Ctrl+Win+C")

    # try to move away from page, we should get a warning
    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        app.main_notebook.set_current_page(clipboard_page_num + 1)

    assert app.main_notebook.get_current_page() == clipboard_page_num + 1
    app.main_notebook.set_current_page(clipboard_page_num)

    assert handler.copy_combo.get_active_id() == "default (Ctrl+Shift+C)"
    handler.copy_combo.set_active_id("Ctrl+Win+C")

    # try to move away from page, we should get a warning
    with patch(show_dialog_with_icon_path) as mock_ask, patch(
        "qubes_config.global_config.basics_handler." "apply_feature_change"
    ) as mock_apply:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.set_current_page(clipboard_page_num + 1)
        mock_apply.assert_called_with(
            test_qapp.domains["dom0"],
            "gui-default-secure-copy-sequence",
            "Ctrl-Mod4-c",
        )

    mock_error.assert_not_called()


@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_page_change(
    mock_error, mock_subprocess, test_qapp, test_policy_manager, test_builder
):
    mock_subprocess.return_value = b""
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert test_builder

    while (
        app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()
        ).get_name()
        != "file"
    ):
        app.main_notebook.next_page()

    file_page_num = app.main_notebook.get_current_page()
    handler = app.get_current_page()
    assert isinstance(handler, FileAccessHandler)

    # make a small change
    handler.filecopy_handler.enable_radio.set_active(True)
    handler.filecopy_handler.add_button.clicked()

    for child in handler.filecopy_handler.current_rows:
        if child.editing:
            child.activate()
            child.source_widget.model.select_value("sys-net")
            child.validate_and_save()

    for row in handler.filecopy_handler.current_rows:
        if row.rule.source == "sys-net":
            break
    else:
        assert False  # didn't find the change

    # try to switch pages but refuse to save changes
    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.NO
        app.main_notebook.next_page()
        mock_ask.assert_called()

    # wait to make sure we don't accidentally catch the pre-corrected page
    while Gtk.events_pending():
        Gtk.main_iteration()
    time.sleep(1)

    assert app.main_notebook.get_current_page() == file_page_num + 1
    app.main_notebook.prev_page()

    # changes should not be made
    for row in handler.filecopy_handler.current_rows:
        assert row.rule.source != "sys-net"

    # make changes and try to stick to them
    handler.filecopy_handler.enable_radio.set_active(True)
    handler.filecopy_handler.add_button.clicked()

    for child in handler.filecopy_handler.current_rows:
        if child.editing:
            child.activate()
            child.source_widget.model.select_value("sys-net")
            child.validate_and_save()
            break
    else:
        assert False

    # file should not yet exist
    assert (
        handler.filecopy_handler.policy_file_name
        not in test_policy_manager.policy_client.files
    )

    # save changes
    with patch(show_dialog_with_icon_path) as mock_ask:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.next_page()
        mock_ask.assert_called()

    while Gtk.events_pending():
        Gtk.main_iteration()
    time.sleep(0.1)

    # changes should have been done
    assert (
        "sys-net"
        in test_policy_manager.policy_client.files[
            handler.filecopy_handler.policy_file_name
        ]
    )

    mock_error.assert_not_called()


@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_failure(
    mock_error, mock_subprocess, test_qapp, test_policy_manager, test_builder
):
    mock_subprocess.return_value = b""
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()

    assert test_builder

    # we should be at first page
    assert app.main_notebook.get_current_page() == 0
    handler = app.get_current_page()
    assert isinstance(handler, BasicSettingsHandler)

    # change something manually
    handler.fullscreen_combo.set_active_id("disallow")

    # try to switch pages, error will occur on saving
    with patch(show_dialog_with_icon_path) as mock_ask, patch(
        "qubes_config.global_config.global_config.GLib.timeout_add"
    ) as mock_timeout:
        mock_ask.return_value = Gtk.ResponseType.YES
        app.main_notebook.next_page()
        mock_ask.assert_called()
        mock_error.assert_called()

        # and we called the timer to switch back to self; can't check
        # if switch was successful because we don't have the main
        # loop in these tests
        mock_timeout.assert_called()


@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_broken_system(
    mock_error,
    mock_subprocess,
    test_qapp_broken,
    test_policy_manager,
    test_builder,
):
    mock_subprocess.return_value = b""
    app = GlobalConfig(test_qapp_broken, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert test_builder

    # switch across pages, nothing should happen
    while (
        app.main_notebook.get_nth_page(
            app.main_notebook.get_current_page()
        ).get_name()
        != "thisdevice"
    ):
        app.main_notebook.next_page()

    mock_error.assert_not_called()


@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_open_at(
    mock_error, mock_subprocess, test_qapp, test_policy_manager, real_builder
):
    mock_subprocess.return_value = b""
    app = GlobalConfig(test_qapp, test_policy_manager)
    # do not call do_activate - it will make Gtk confused and, in case
    # of errors, spawn an entire screenful of windows
    app.perform_setup()
    assert real_builder

    with patch("builtins.print", side_effect=print) as mock_print:
        app.scroll_to_location("basics")
        mock_print.assert_not_called()
        app.scroll_to_location("basics#default_qubes")
        mock_print.assert_not_called()
        app.scroll_to_location("basics#window_management")
        mock_print.assert_not_called()
        app.scroll_to_location("basics#memory_balancing")
        mock_print.assert_not_called()
        app.scroll_to_location("basics#linux_kernel")
        mock_print.assert_not_called()

        app.scroll_to_location("usb")
        mock_print.assert_not_called()
        app.scroll_to_location("usb#usb_input")
        mock_print.assert_not_called()
        app.scroll_to_location("usb#u2f")
        mock_print.assert_not_called()

        app.scroll_to_location("updates")
        mock_print.assert_not_called()
        app.scroll_to_location("updates#dom0_updates")
        mock_print.assert_not_called()
        app.scroll_to_location("updates#check_for_updates")
        mock_print.assert_not_called()
        app.scroll_to_location("updates#update_proxy")
        mock_print.assert_not_called()
        app.scroll_to_location("updates#template_repositories")
        mock_print.assert_not_called()

        app.scroll_to_location("splitgpg")
        mock_print.assert_not_called()

        app.scroll_to_location("clipboard")
        mock_print.assert_not_called()
        app.scroll_to_location("clipboard#clipboard_shortcut")
        mock_print.assert_not_called()
        app.scroll_to_location("clipboard#clipboard_policy")
        mock_print.assert_not_called()

        app.scroll_to_location("file")
        mock_print.assert_not_called()
        app.scroll_to_location("file#filecopy_policy")
        mock_print.assert_not_called()
        app.scroll_to_location("file#open_in_vm")
        mock_print.assert_not_called()

        app.scroll_to_location("url")
        mock_print.assert_not_called()

        app.scroll_to_location("thisdevice")
        mock_print.assert_not_called()

        # and check a faulty location
        app.scroll_to_location("error#words")
        mock_print.assert_called()

    mock_error.assert_not_called()
