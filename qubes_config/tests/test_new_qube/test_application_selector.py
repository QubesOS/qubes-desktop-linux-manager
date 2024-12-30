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

from ...new_qube.application_selector import (
    ApplicationBoxHandler,
    ApplicationButton,
    AddButton,
    ApplicationRow,
)
from ...new_qube.template_handler import TemplateHandler


@patch("subprocess.check_output")
def test_app_handler(mock_subprocess, test_qapp, new_qube_builder):
    def mock_output(command):
        vm_name = command[-1]
        if command[1] == "--get-available":
            if vm_name == "fedora-35":
                return b"test.desktop|Test App|"
            if vm_name == "fedora-36":
                return (
                    b"test2.desktop|Test2 App|test2 desc\n"
                    b"egg.desktop|Egg|egg\n"
                    b"firefox.desktop|Firefox|firefox"
                )
        elif command[1] == "--get-default-whitelist":
            if vm_name == "fedora-36":
                return b"firefox.desktop"
        return b""

    mock_subprocess.side_effect = mock_output

    template_handler = TemplateHandler(new_qube_builder, test_qapp)
    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-36"]
    )
    app_selector = ApplicationBoxHandler(new_qube_builder, template_handler)

    # default template is selected at start, so:

    # there should be one app selected, Firefox, and the plus button
    assert len(app_selector.flowbox.get_children()) == 2

    for child in app_selector.flowbox.get_children():
        if isinstance(child, ApplicationButton):
            assert child.appdata.name == "Firefox"
            continue
        assert isinstance(child, AddButton)

    assert app_selector.get_selected_apps() == ["firefox.desktop"]

    available_apps = []
    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        available_apps.append(row.appdata.ident)

    # order depends on selection
    assert available_apps == ["firefox.desktop", "egg.desktop", "test2.desktop"]


@patch("subprocess.check_output")
def test_app_handler_show_hide(mock_subprocess, test_qapp, new_qube_builder):
    def mock_output(command):
        vm_name = command[-1]
        if command[1] == "--get-available":
            if vm_name == "fedora-35":
                return b"test.desktop|Test App|"
            if vm_name == "fedora-36":
                return (
                    b"test2.desktop|Test2 App|test2 desc\n"
                    b"egg.desktop|Egg|egg\n"
                    b"firefox.desktop|Firefox|firefox"
                )
        elif command[1] == "--get-default-whitelist":
            if vm_name == "fedora-36":
                return b"firefox.desktop"
        return b""

    mock_subprocess.side_effect = mock_output

    template_handler = TemplateHandler(new_qube_builder, test_qapp)
    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-36"]
    )
    app_selector = ApplicationBoxHandler(new_qube_builder, template_handler)

    # click the plus button
    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.button.clicked()
            break
    else:
        assert False  # button not found

    assert app_selector.apps_window.get_visible()

    # select another row:
    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        if row.appdata.name == "Egg":
            row.activate()

    app_selector.apps_close.clicked()

    assert app_selector.get_selected_apps() == [
        "egg.desktop",
        "firefox.desktop",
    ]
    assert len(app_selector.flowbox.get_children()) == 3

    # and try again, now deselect something and select something else
    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found

    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        if row.appdata.name in ("Egg", "Test2 App"):
            row.activate()

    app_selector.apps_close.clicked()

    assert app_selector.get_selected_apps() == [
        "firefox.desktop",
        "test2.desktop",
    ]
    assert len(app_selector.flowbox.get_children()) == 3


@patch("subprocess.check_output")
def test_app_handler_change_template(
    mock_subprocess, test_qapp, new_qube_builder
):
    def mock_output(command):
        vm_name = command[-1]
        if command[1] == "--get-available":
            if vm_name == "fedora-35":
                return (
                    b"test.desktop|Test App|\n"
                    b"tomato.desktop|Tomato|basil\n"
                    b"udon.desktop|Udon|noodles\n"
                    b"spaghetti.desktop|Spaghetti|pasta"
                )
            if vm_name == "fedora-36":
                return (
                    b"test2.desktop|Test2 App|test2 desc\n"
                    b"egg.desktop|Egg|egg\n"
                    b"firefox.desktop|Firefox|firefox"
                )
        elif command[1] == "--get-default-whitelist":
            if vm_name == "fedora-36":
                return b"firefox.desktop"
        return b""

    mock_subprocess.side_effect = mock_output

    template_handler = TemplateHandler(new_qube_builder, test_qapp)
    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-36"]
    )
    app_selector = ApplicationBoxHandler(new_qube_builder, template_handler)

    assert app_selector.get_selected_apps() == ["firefox.desktop"]

    template_handler.select_template("fedora-35")

    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found

    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        if row.appdata.name in ("Udon", "Spaghetti"):
            row.activate()

    app_selector.apps_close.clicked()

    assert app_selector.get_selected_apps() == [
        "spaghetti.desktop",
        "udon.desktop",
    ]

    # default is none
    template_handler.change_vm_type("qube_type_template")
    assert template_handler.get_selected_template() is None

    assert not app_selector.flowbox.get_visible()

    assert not app_selector.get_selected_apps()

    # select some apps
    template_handler.select_template("fedora-35")
    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found

    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        if row.appdata.name in ("Udon", "Spaghetti"):
            row.activate()

    app_selector.apps_close.clicked()

    assert app_selector.get_selected_apps() == [
        "spaghetti.desktop",
        "udon.desktop",
    ]

    # and now go back to none
    template_handler.select_template(None)
    assert not app_selector.get_selected_apps()


@patch("subprocess.check_output")
def test_app_handler_do_template(mock_subprocess, test_qapp, new_qube_builder):
    def mock_output(command):
        vm_name = command[-1]
        if command[1] == "--get-available":
            if vm_name == "fedora-35":
                return (
                    b"test.desktop|Test App|\n"
                    b"tomato.desktop|Tomato|basil\n"
                    b"udon.desktop|Udon|noodles\n"
                    b"spaghetti.desktop|Spaghetti|pasta"
                )
            if vm_name == "fedora-36":
                return (
                    b"test2.desktop|Test2 App|test2 desc\n"
                    b"egg.desktop|Egg|egg\n"
                    b"firefox.desktop|Firefox|firefox"
                )
        elif command[1] == "--get-default-whitelist":
            if vm_name == "fedora-36":
                return b"firefox.desktop"
        return b""

    mock_subprocess.side_effect = mock_output

    template_handler = TemplateHandler(new_qube_builder, test_qapp)
    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-36"]
    )
    app_selector = ApplicationBoxHandler(new_qube_builder, template_handler)

    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found

    # try to find Udon
    app_selector.apps_search.set_text("Udon")

    assert app_selector.apps_list_placeholder.get_visible()
    app_selector.load_all_button.clicked()
    time.sleep(1)

    for child in app_selector.apps_list_other.get_children():
        # as we cannot use mapping in tests, let's just check the filter
        # function
        if app_selector._filter_func_app_list(child):
            child.activate()

            # the widget in ask window should have been changed to new tmpl
            assert app_selector.target_template_name_widget
            assert (
                app_selector.target_template_name_widget.vm
                == test_qapp.domains["fedora-35"]
            )
            app_selector.change_template_ok.clicked()
            break
    else:
        assert False  # didn't find udon

    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-35"]
    )


@patch("subprocess.check_output")
def test_app_handler_delete(mock_subprocess, test_qapp, new_qube_builder):
    def mock_output(command):
        vm_name = command[-1]
        if command[1] == "--get-available":
            if vm_name == "fedora-35":
                return (
                    b"test.desktop|Test App|\n"
                    b"tomato.desktop|Tomato|basil\n"
                    b"udon.desktop|Udon|noodles\n"
                    b"spaghetti.desktop|Spaghetti|pasta"
                )
            if vm_name == "fedora-36":
                return (
                    b"test2.desktop|Test2 App|test2 desc\n"
                    b"egg.desktop|Egg|egg\n"
                    b"firefox.desktop|Firefox|firefox"
                )
        elif command[1] == "--get-default-whitelist":
            if vm_name == "fedora-36":
                return b"firefox.desktop"
        return b""

    mock_subprocess.side_effect = mock_output

    template_handler = TemplateHandler(new_qube_builder, test_qapp)
    assert (
        template_handler.get_selected_template()
        == test_qapp.domains["fedora-36"]
    )
    app_selector = ApplicationBoxHandler(new_qube_builder, template_handler)

    assert app_selector.get_selected_apps() == ["firefox.desktop"]

    template_handler.select_template("fedora-35")

    for child in app_selector.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found

    for row in app_selector.apps_list.get_children():
        assert isinstance(row, ApplicationRow)
        if row.appdata.name in ("Udon", "Spaghetti"):
            row.activate()

    app_selector.apps_close.clicked()

    assert app_selector.get_selected_apps() == [
        "spaghetti.desktop",
        "udon.desktop",
    ]

    for button in app_selector.flowbox.get_children():
        if isinstance(button, ApplicationButton):
            if button.appdata.ident == "udon.desktop":
                button.activate()
                break
    else:
        assert False  # app button not found

    assert app_selector.get_selected_apps() == ["spaghetti.desktop"]
