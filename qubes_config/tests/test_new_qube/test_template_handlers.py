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

from unittest.mock import patch, Mock, ANY

from ...new_qube.template_handler import TemplateHandler
from ...new_qube.application_selector import ApplicationData

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


@patch("subprocess.check_output")
def test_template_handler_normal(mock_subprocess, test_qapp, new_qube_builder):
    mock_subprocess.return_value = b""
    handler = TemplateHandler(new_qube_builder, test_qapp)

    # assert we start at app
    assert handler.selected_type == "qube_type_app"

    # check selected template
    assert handler.get_selected_template()
    assert handler.get_selected_template() == test_qapp.default_template
    assert handler.get_selected_template() == test_qapp.domains["fedora-36"]

    # select another
    handler.select_template("fedora-35")
    assert handler.get_selected_template() == test_qapp.domains["fedora-35"]

    assert handler.is_given_template_available(test_qapp.domains["fedora-36"])
    assert handler.is_given_template_available(test_qapp.domains["fedora-35"])
    assert not handler.is_given_template_available(test_qapp.domains["dom0"])
    assert not handler.is_given_template_available(test_qapp.domains["test-vm"])


@patch("subprocess.check_output")
def test_template_handler_none(mock_subprocess, test_qapp, new_qube_builder):
    mock_subprocess.return_value = b""
    handler = TemplateHandler(new_qube_builder, test_qapp)

    # assert we start at app
    assert handler.selected_type == "qube_type_app"
    handler.change_vm_type("qube_type_template")

    # templates are available
    assert handler.is_given_template_available(test_qapp.domains["fedora-36"])
    assert handler.is_given_template_available(test_qapp.domains["fedora-35"])
    assert not handler.is_given_template_available(
        test_qapp.domains["test-standalone"]
    )
    assert not handler.is_given_template_available(test_qapp.domains["dom0"])
    assert not handler.is_given_template_available(test_qapp.domains["test-vm"])

    radio_none = new_qube_builder.get_object("radio_template_none")
    radio_some = new_qube_builder.get_object("radio_template_template")
    combo: Gtk.ComboBox = new_qube_builder.get_object("combo_template_template")

    # none is selected
    assert handler.get_selected_template() is None
    assert not combo.get_sensitive()

    radio_some.set_active(True)

    # something is selected
    assert combo.get_sensitive()
    assert handler.get_selected_template()

    # select none
    radio_none.set_active(True)
    assert handler.get_selected_template() is None

    # select something
    radio_some.set_active(True)
    combo.set_active_id("fedora-36")
    assert handler.get_selected_template() == test_qapp.domains["fedora-36"]


@patch("subprocess.check_output")
def test_template_handler_select_vm(
    mock_subprocess, test_qapp, new_qube_builder
):
    mock_subprocess.return_value = b""
    handler = TemplateHandler(new_qube_builder, test_qapp)

    # assert we start at app
    assert handler.selected_type == "qube_type_app"

    # selecting template works
    assert handler.get_selected_template() == test_qapp.domains["fedora-36"]
    handler.select_template("fedora-35")
    assert handler.get_selected_template() == test_qapp.domains["fedora-35"]

    # switch to a type with None
    handler.change_vm_type("qube_type_template")
    assert handler.get_selected_template() is None

    handler.select_template("fedora-36")
    assert handler.get_selected_template() == test_qapp.domains["fedora-36"]

    handler.select_template(None)
    assert handler.get_selected_template() is None


@patch("subprocess.check_output")
def test_get_appdata(mock_subprocess, test_qapp, new_qube_builder):
    def mock_output(command):
        vm_name = command[-1]
        if vm_name == "fedora-35":
            return b"test.desktop|Test App|test desc"
        return b""

    mock_subprocess.side_effect = mock_output

    handler = TemplateHandler(new_qube_builder, test_qapp)

    fedora35 = test_qapp.domains["fedora-35"]
    testvm = test_qapp.domains["test-vm"]

    assert handler.get_available_apps(testvm) == []
    assert len(handler.get_available_apps(fedora35)) == 1

    app_data: ApplicationData = handler.get_available_apps(fedora35)[0]

    assert app_data.name == "Test App"
    assert app_data.ident == "test.desktop"
    assert app_data.template == fedora35

    assert handler.get_available_apps() == [app_data]


@patch("subprocess.check_output")
def test_template_emit_signal(mock_subprocess, test_qapp, new_qube_builder):
    mock_subprocess.return_value = b""
    handler = TemplateHandler(new_qube_builder, test_qapp)

    mock_emit = Mock()
    handler.main_window.connect("template-changed", mock_emit)

    handler.change_vm_type("qube_type_template")
    mock_emit.assert_called_with(ANY, None)

    radio_none = new_qube_builder.get_object("radio_template_none")
    radio_some = new_qube_builder.get_object("radio_template_template")
    combo: Gtk.ComboBox = new_qube_builder.get_object("combo_template_template")

    radio_some.set_active(True)

    # first available template
    mock_emit.assert_called_with(ANY, "fedora-35")

    combo.set_active_id("fedora-36")
    assert handler.get_selected_template() == test_qapp.domains["fedora-36"]

    # two calls because comboboxes are weird
    mock_emit.assert_called_with(ANY, "fedora-36")

    radio_none.set_active(True)

    mock_emit.assert_called_with(ANY, None)

    handler.change_vm_type("qube_type_app")

    # default template
    mock_emit.assert_called_with(ANY, "fedora-36")

    handler.select_template(test_qapp.domains["fedora-35"])

    mock_emit.assert_called_with(ANY, "fedora-35")
