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
# pylint: disable=unnecessary-dunder-call
from unittest.mock import patch, call, ANY

from ...new_qube.new_qube_app import CreateNewQube
from ...new_qube.application_selector import AddButton


def mock_output(command, *_args, **_kwargs):
    vm_name = command[-1]
    if command[1] == "--get-available":
        if vm_name == "fedora-35":
            return (
                b"green.desktop|Green App|\n"
                b"eggs.desktop|Eggs App|\n"
                b"ham.desktop|Ham App|"
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


@patch("subprocess.check_output", side_effect=mock_output)
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_simple_new_qube(
    mock_error, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()

    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")

    assert new_qube_app.create_button.get_sensitive()

    # the created qube should have default template (fedora-36), default label
    # (red), default networking, default apps (which is firefox here), no
    # providing network
    test_qapp.expected_calls[
        ("dom0", "admin.vm.Create.AppVM", "fedora-36", b"name=test label=red")
    ] = b"0\x00"

    # netvm is default
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Reset", "netvm", None)
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=AppVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen:
        mock_popen().__enter__().returncode = 0
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success

        assert (
            call(
                ["qvm-appmenus", "--set-whitelist", "-", "--update", "test"],
                stdin=-1,
            )
            in mock_popen.mock_calls
        )
        assert (
            call().__enter__().communicate(b"firefox.desktop")
            in mock_popen.mock_calls
        )

    mock_error.assert_not_called()
    # no more subprocess calls
    assert num_setup_calls == len(mock_subprocess.mock_calls)


@patch("subprocess.check_output", side_effect=mock_output)
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_complex_new_qube(
    mock_error, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()
    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")
    # select label
    new_qube_app.qube_label_combo.set_active_id("green")
    # select template and networking
    new_qube_app.template_handler.select_template("fedora-35")
    new_qube_app.network_selector.network_none.set_active(True)

    # choose some apps
    for child in new_qube_app.app_box_handler.flowbox.get_children():
        if isinstance(child, AddButton):
            child.activate()
            break
    else:
        assert False  # button not found
    for row in new_qube_app.app_box_handler.apps_list.get_children():
        if hasattr(row, "appdata") and (
            row.appdata.name in ["Green App", "Eggs App"]
        ):
            row.activate()

    new_qube_app.app_box_handler.apps_close.clicked()

    assert new_qube_app.create_button.get_sensitive()

    # the created qube should have template fedora-35, label green, no
    # networking, green.desktop and eggs.desktop apps and not provide network
    test_qapp.expected_calls[
        ("dom0", "admin.vm.Create.AppVM", "fedora-35", b"name=test label=green")
    ] = b"0\x00"

    # netvm is None
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "netvm", b"")
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=AppVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen:
        mock_popen().__enter__().returncode = 0
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success

        assert (
            call(
                ["qvm-appmenus", "--set-whitelist", "-", "--update", "test"],
                stdin=-1,
            )
            in mock_popen.mock_calls
        )
        assert (
            call().__enter__().communicate(b"eggs.desktop\ngreen.desktop")
            in mock_popen.mock_calls
        )

    mock_error.assert_not_called()
    # 2 additional calls were made: to list available apps and default apps
    assert num_setup_calls + 2 == len(mock_subprocess.mock_calls)


@patch("subprocess.check_output", side_effect=mock_output)
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_new_template_cloned(
    mock_error, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()
    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")

    new_qube_app.qube_type_template.clicked()
    assert new_qube_app.template_handler.selected_type == "qube_type_template"
    # select source for cloning
    new_qube_app.template_handler.select_template("fedora-35")

    assert new_qube_app.create_button.get_sensitive()

    # the created qube should be cloned from fedora-35, have green label
    # (conftest default), default networking, no apps and not provide network
    test_qapp.expected_calls[
        ("dom0", "admin.vm.Create.TemplateVM", None, b"name=test label=green")
    ] = b"0\x00"
    # but as user requested red label, we replace it
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "label", b"red")
    ] = b"0\x00"

    # netvm is default
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Reset", "netvm", None)
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.domains.clear_cache()
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=TemplateVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen, patch.object(
        test_qapp, "clone_vm"
    ) as mock_clone:
        mock_clone.return_value = test_qapp.domains["test"]
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success
        assert not mock_popen.mock_calls  # no apps added

    mock_error.assert_not_called()
    # 2 additional subprocess calls to get all apps and available apps for
    # the new template
    assert num_setup_calls + 2 == len(mock_subprocess.mock_calls)


@patch("subprocess.check_output", side_effect=mock_output)
@patch("subprocess.check_call")
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_new_standalone(
    mock_error, mock_check_call, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()
    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")

    new_qube_app.qube_type_standalone.clicked()
    assert new_qube_app.template_handler.selected_type == "qube_type_standalone"
    assert new_qube_app.template_handler.get_selected_template() is None

    assert new_qube_app.create_button.get_sensitive()

    # the created qube should be empty, have red label, default
    # networking, no apps and not provide network
    test_qapp.expected_calls[
        ("dom0", "admin.vm.Create.StandaloneVM", None, b"name=test label=red")
    ] = b"0\x00"

    # it's a standalone so it should be a hvm with no kernel
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "virt_mode", b"hvm")
    ] = b"0\x00"
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "kernel", b"")
    ] = b"0\x00"

    # netvm is default
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Reset", "netvm", None)
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=StandaloneVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen:
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success

        assert (
            call(["qubes-vm-boot-from-device", "test"])
            in mock_check_call.mock_calls
        )  # called install system to qube

        # but no apps were added
        assert (
            call(
                ["qvm-appmenus", "--set-whitelist", "-", "--update", ANY],
                stdin=-1,
            )
            not in mock_popen.mock_calls
        )

    mock_error.assert_not_called()
    # no more subprocess calls, no actual new template was selected
    assert num_setup_calls == len(mock_subprocess.mock_calls)


@patch("subprocess.check_output", side_effect=mock_output)
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_new_disposable(
    mock_error, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()
    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")

    new_qube_app.qube_type_disposable.clicked()
    assert new_qube_app.template_handler.selected_type == "qube_type_disposable"
    assert new_qube_app.template_handler.get_selected_template() is None

    # select something better
    new_qube_app.template_handler.select_template("default-dvm")

    assert new_qube_app.create_button.get_sensitive()

    # the created qube should be empty, have red label, default
    # networking, no apps and not provide network
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.Create.DispVM",
            "default-dvm",
            b"name=test label=red",
        )
    ] = b"0\x00"

    # it's a standalone so it should be a hvm with no kernel
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "virt_mode", b"hvm")
    ] = b"0\x00"
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "kernel", b"")
    ] = b"0\x00"

    # netvm is default
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Reset", "netvm", None)
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=StandaloneVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen:
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success
        assert not mock_popen.mock_calls  # no apps added

    mock_error.assert_not_called()
    # 2 additional subprocess calls to get all apps and available apps for
    # the new template
    assert num_setup_calls + 2 == len(mock_subprocess.mock_calls)


@patch("subprocess.check_output", side_effect=mock_output)
@patch("subprocess.check_call")
@patch("qubes_config.new_qube.new_qube_app.show_error")
def test_advanced_new_qube(
    mock_error, _mock_check_call, mock_subprocess, test_qapp, new_qube_builder
):
    # the builder fixture must be called to register needed signals and
    # only do it once
    assert new_qube_builder
    new_qube_app = CreateNewQube(test_qapp)

    new_qube_app.perform_setup()

    num_setup_calls = len(mock_subprocess.mock_calls)

    assert not new_qube_app.create_button.get_sensitive()

    # enter name
    new_qube_app.qube_name.set_text("test")

    assert new_qube_app.create_button.get_sensitive()

    # we don't have to test install-to-qube, that gets tested with new empty
    # template
    new_qube_app.advanced_handler.launch_settings_check.set_active(True)
    new_qube_app.advanced_handler.initram.set_value(400)
    new_qube_app.advanced_handler.pool_handler.select_value("lvm")

    # the created qube should have default template (fedora-36), default label
    # (red), default networking, default apps (which is firefox here), no
    # providing network, launch settings after creation, initram 400 and
    # misc pool
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.CreateInPool.AppVM",
            "fedora-36",
            b"name=test label=red pool=lvm",
        )
    ] = b"0\x00"

    # netvm is default
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Reset", "netvm", None)
    ] = b"0\x00"

    # not provide network
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "provides_network", b"False")
    ] = b"0\x00"
    # memory
    test_qapp.expected_calls[
        ("test", "admin.vm.property.Set", "memory", b"400")
    ] = b"0\x00"

    # also add a call we do after adding the vm:
    test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)] = (
        test_qapp.expected_calls[("dom0", "admin.vm.List", None, None)]
        + "test class=AppVM state=Halted\n".encode()
    )

    with patch(
        "qubes_config.new_qube.new_qube_app.Gtk.MessageDialog"
    ) as mock_dialog, patch("subprocess.Popen") as mock_popen:
        mock_popen().__enter__().returncode = 0
        new_qube_app.create_button.clicked()
        assert mock_dialog.mock_calls  # called to tell us about the success

        assert (
            call(
                ["qvm-appmenus", "--set-whitelist", "-", "--update", "test"],
                stdin=-1,
            )
            in mock_popen.mock_calls
        )
        assert (
            call().__enter__().communicate(b"firefox.desktop")
            in mock_popen.mock_calls
        )

    mock_error.assert_not_called()
    # no more subprocess calls
    assert num_setup_calls == len(mock_subprocess.mock_calls)
