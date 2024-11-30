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
from unittest.mock import patch, call
from functools import partial

import pytest

import qubesadmin.exc
from ..global_config.updates_handler import (
    RepoHandler,
    UpdateCheckerHandler,
    UpdateProxy,
    UpdatesHandler,
)
from ..global_config.rule_list_widgets import NoActionListBoxRow

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class MockProcess:
    def __init__(self, stdout=b"", returncode=0, stderr=None):
        self.stderr = stderr
        self.returncode = returncode
        self.stdout = stdout


ALL_ENABLED = """qubes-dom0-current-testing\0c\0enabled
qubes-dom0-security-testing\0c\0enabled
qubes-dom0-current\0c\0enabled
qubes-templates-itl-testing\0c\0enabled
qubes-templates-itl\0c\0enabled
qubes-templates-community-testing\0c\0enabled
qubes-templates-community\0c\0enabled"""


MINIMAL = """qubes-dom0-current-testing\0c\0disabled
qubes-dom0-security-testing\0c\0disabled
qubes-dom0-current\0c\0enabled
qubes-templates-itl-testing\0c\0disabled
qubes-templates-itl\0c\0enabled
qubes-templates-community-testing\0c\0disabled
qubes-templates-community\0c\0disabled"""


MISSING = """qubes-dom0-current\0c\0enabled"""


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_repo_handler_all(mock_output, real_builder):
    mock_output.return_value = ALL_ENABLED
    handler = RepoHandler(real_builder)
    assert handler.dom0_testing_radio.get_active()
    assert handler.template_official_testing.get_active()
    assert handler.template_official.get_active()
    assert handler.template_community.get_active()
    assert handler.template_community_testing.get_active()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_repo_handler_minimal(mock_output, real_builder):
    mock_output.return_value = MINIMAL
    handler = RepoHandler(real_builder)
    assert handler.dom0_stable_radio.get_active()
    assert not handler.template_official_testing.get_active()
    assert handler.template_official.get_active()
    assert not handler.template_community_testing.get_active()
    assert not handler.template_community.get_active()
    assert not handler.template_community_testing.get_sensitive()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_repo_handler_missing_repos(mock_output, real_builder):
    mock_output.return_value = MISSING
    handler = RepoHandler(real_builder)
    assert handler.dom0_stable_radio.get_active()
    assert not handler.template_official_testing.get_active()
    assert handler.template_official.get_active()
    assert not handler.template_community_testing.get_active()
    assert not handler.template_community.get_active()
    assert not handler.template_community_testing.get_sensitive()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_repo_handler_error(mock_output, real_builder):
    mock_output.side_effect = RuntimeError()
    handler = RepoHandler(real_builder)
    assert not handler.dom0_stable_radio.get_sensitive()
    assert not handler.dom0_testing_sec_radio.get_sensitive()
    assert not handler.dom0_testing_radio.get_sensitive()
    assert not handler.template_official_testing.get_sensitive()
    assert not handler.template_community.get_sensitive()
    assert not handler.template_community_testing.get_sensitive()
    assert handler.problems_repo_box.get_visible()


def mock_qrexec(
    _vm, service, arg, repo_list="", enable_repos=None, disable_repos=None
):
    if "qubes.repos.List" in service:
        return repo_list

    if "qubes.repos.Enable" in service:
        if enable_repos and arg in enable_repos:
            return "ok\n"

    if "qubes.repos.Disable" in service:
        if disable_repos and arg in disable_repos:
            return "ok\n"

    assert False


def test_repo_handler_save(real_builder):
    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call",
        partial(mock_qrexec, repo_list=ALL_ENABLED),
    ):
        handler = RepoHandler(real_builder)

    assert handler.dom0_stable_radio.get_sensitive()
    assert handler.template_community_testing.get_sensitive()
    assert handler.template_official_testing.get_sensitive()

    handler.dom0_stable_radio.set_active(True)
    handler.template_community_testing.set_active(False)
    handler.template_official_testing.set_active(False)

    changed_result = """qubes-dom0-current-testing\0c\0disabled
qubes-dom0-security-testing\0c\0disabled
qubes-dom0-current\0c\0enabled
qubes-templates-itl-testing\0c\0disabled
qubes-templates-itl\0c\0enabled
qubes-templates-community-testing\0c\0disabled
qubes-templates-community\0c\0enabled"""

    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call",
        partial(
            mock_qrexec,
            repo_list=changed_result,
            enable_repos=[
                "qubes-dom0-current",
                "qubes-templates-itl",
                "qubes-templates-community",
            ],
            disable_repos=[
                "qubes-dom0-security-testing",
                "qubes-dom0-current-testing",
                "qubes-templates-itl-testing",
                "qubes-templates-community-testing",
            ],
        ),
    ):
        handler.save()


def test_repo_handler_save_2(real_builder):
    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call",
        partial(mock_qrexec, repo_list=ALL_ENABLED),
    ):
        handler = RepoHandler(real_builder)

    assert handler.dom0_stable_radio.get_sensitive()

    handler.dom0_testing_sec_radio.set_active(True)

    changed_result = """qubes-dom0-current-testing\0c\0disabled
qubes-dom0-security-testing\0c\0enabled
qubes-dom0-current\0c\0enabled
qubes-templates-itl-testing\0c\0enabled
qubes-templates-itl\0c\0enabled
qubes-templates-community-testing\0c\0enabled
qubes-templates-community\0c\0enabled"""

    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call",
        partial(
            mock_qrexec,
            repo_list=changed_result,
            enable_repos=[
                "qubes-dom0-current",
                "qubes-dom0-security-testing",
                "qubes-templates-itl",
                "qubes-templates-community",
                "qubes-templates-itl-testing",
                "qubes-templates-community-testing",
            ],
            disable_repos=["qubes-dom0-current-testing"],
        ),
    ):
        handler.save()


def test_repo_handler_save_fail(real_builder):
    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call",
        partial(mock_qrexec, repo_list=ALL_ENABLED),
    ):
        handler = RepoHandler(real_builder)

    handler.dom0_stable_radio.set_active(True)

    with patch(
        "qubes_config.global_config.updates_handler.qrexec_call"
    ) as mock_output:
        mock_output.side_effect = RuntimeError()
        with pytest.raises(qubesadmin.exc.QubesException):
            handler.save()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_repo_handler_unsaved(mock_output, real_builder):
    mock_output.return_value = MINIMAL
    handler = RepoHandler(real_builder)

    assert handler.get_unsaved() == ""

    handler.dom0_testing_radio.set_active(True)

    assert handler.get_unsaved() == "dom0 update source"

    handler.dom0_stable_radio.set_active(True)
    handler.template_official_testing.set_active(True)

    assert handler.get_unsaved() == "Official template update source"

    handler.template_community.set_active(True)
    handler.template_community_testing.set_active(True)

    assert (
        handler.get_unsaved() == "Official template update source\n"
        "Community template update source"
    )

    handler.reset()

    assert handler.dom0_stable_radio.get_active()
    assert not handler.template_official_testing.get_active()
    assert handler.template_official.get_active()
    assert not handler.template_community_testing.get_active()
    assert not handler.template_community.get_active()
    assert not handler.template_community_testing.get_sensitive()
    assert handler.get_unsaved() == ""


def test_updates_checker_dom0(real_builder, test_qapp):
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x001"
    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert handler.dom0_update_check.get_active()

    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"
    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert not handler.dom0_update_check.get_active()

    # default for this feature is Enabled
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"2\x00QubesFeatureNotFoundError\x00\x00feature1\x00"
    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert handler.dom0_update_check.get_active()


def test_updates_checker_init_state(real_builder, test_qapp):
    # initial values for all vms are feature not found
    handler = UpdateCheckerHandler(real_builder, test_qapp)

    assert handler.enable_radio.get_active()
    assert not handler.exceptions_check.get_active()
    assert not handler.flowbox_handler.selected_vms

    # disable enable check for 2 vms, explicitly enable for one
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x001"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"
    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert handler.enable_radio.get_active()
    assert handler.exceptions_check.get_active()
    assert handler.flowbox_handler.selected_vms == [
        test_qapp.domains["test-blue"],
        test_qapp.domains["test-red"],
    ]


def test_updates_checker_init_disabled(real_builder, test_qapp):
    # set default to disabled (remember system default is still enabled)
    # disable it in two qubes explicitly
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = b"0\x00"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"
    # names for easier comparison in case of errors
    expected_qubes = [
        vm.name
        for vm in test_qapp.domains
        if vm.name not in ["test-red", "test-blue", "dom0"]
    ]
    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert handler.disable_radio.get_active()
    assert handler.exceptions_check.get_active()
    assert [
        str(vm) for vm in handler.flowbox_handler.selected_vms
    ] == expected_qubes


def test_updates_checker_exceptions(real_builder, test_qapp):
    # explicit enable in one vm, explicit disable in one vm
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x001"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"
    # no default
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00config.default."
        b"qubes-update-check\x00"
    )

    disabled_vms = ["test-blue"]

    handler = UpdateCheckerHandler(real_builder, test_qapp)
    assert handler.enable_radio.get_active()
    assert handler.exceptions_check.get_active()
    assert [
        str(vm) for vm in handler.flowbox_handler.selected_vms
    ] == disabled_vms

    # switch to disable
    handler.disable_radio.set_active(True)

    # checker should be disabled
    assert not handler.exceptions_check.get_active()

    # select exceptions
    handler.exceptions_check.set_active(True)
    # nothing should be selected
    assert not handler.flowbox_handler.selected_vms


def test_updates_checker_get_unsaved(real_builder, test_qapp):
    handler = UpdateCheckerHandler(real_builder, test_qapp)

    assert handler.get_unsaved() == ""

    handler.dom0_update_check.set_active(False)
    assert "dom0" in handler.get_unsaved()

    handler.dom0_update_check.set_active(True)
    assert handler.get_unsaved() == ""

    handler.disable_radio.set_active(True)
    assert "Default" in handler.get_unsaved()
    handler.enable_radio.set_active(True)
    assert handler.get_unsaved() == ""

    handler.disable_radio.set_active(True)
    handler.dom0_update_check.set_active(False)
    assert "dom0" in handler.get_unsaved()
    assert "Default" in handler.get_unsaved()


def test_updates_checker_get_unsaved_choice(real_builder, test_qapp):
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x001"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"
    # no default
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00config.default."
        b"qubes-update-check\x00"
    )

    handler = UpdateCheckerHandler(real_builder, test_qapp)

    assert handler.get_unsaved() == ""
    assert handler.enable_radio.get_active()

    # add a qube
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-red"])

    assert "Qubes" in handler.get_unsaved()

    # disable and enable
    handler.disable_radio.set_active(True)
    assert "Default" in handler.get_unsaved()
    assert "Qubes" in handler.get_unsaved()

    handler.enable_radio.set_active(True)
    assert "Default" not in handler.get_unsaved()
    assert "Qubes" in handler.get_unsaved()

    # reset flowbox
    handler.exceptions_check.set_active(True)
    handler.flowbox_handler.reset()

    assert handler.get_unsaved() == ""


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_updates_checker_save_dom0(mock_feature, real_builder, test_qapp):
    handler = UpdateCheckerHandler(real_builder, test_qapp)

    handler.dom0_update_check.set_active(False)
    handler.save()

    # only this feature was changed
    mock_feature.assert_called_with("dom0", handler.FEATURE_NAME, False)
    assert len(mock_feature.mock_calls) == 1


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_updates_checker_save_dom0_initial_none(
    mock_feature, real_builder, test_qapp
):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            UpdateCheckerHandler.FEATURE_NAME,
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00service."
        b"qubes-update-check\x00"
    )

    handler = UpdateCheckerHandler(real_builder, test_qapp)

    handler.dom0_update_check.set_active(True)
    handler.save()

    # nothing should have been changed
    assert not mock_feature.mock_calls


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_updates_checker_save_add_exception(
    mock_feature, real_builder, test_qapp
):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = b"0\x001"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"

    handler = UpdateCheckerHandler(real_builder, test_qapp)
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-blue"])
    handler.save()

    assert len(mock_feature.mock_calls) == 1
    mock_feature.assert_called_with(
        test_qapp.domains["test-blue"], handler.FEATURE_NAME, False
    )


@patch("qubes_config.global_config.vm_flowbox.ask_question")
@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_updates_checker_save_del_exception(
    mock_feature, mock_question, real_builder, test_qapp
):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = b"0\x001"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"

    handler = UpdateCheckerHandler(real_builder, test_qapp)

    mock_question.return_value = Gtk.ResponseType.YES
    for child in handler.flowbox_handler.flowbox.get_children():
        if hasattr(child, "vm") and str(child.vm) == "test-blue":
            child._remove_self()
    assert mock_question.mock_calls
    handler.save()

    assert len(mock_feature.mock_calls) == 1
    mock_feature.assert_called_with(
        test_qapp.domains["test-blue"], handler.FEATURE_NAME, None
    )


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_updates_checker_save_change_default(
    mock_feature, real_builder, test_qapp
):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = b"0\x001"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"

    handler = UpdateCheckerHandler(real_builder, test_qapp)
    handler.disable_radio.set_active(True)
    handler.exceptions_check.set_active(True)

    # add a qube
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-blue"])
    # re-add test-red
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-red"])

    handler.save()
    assert (
        call(
            test_qapp.domains["dom0"],
            "config.default.qubes-update-check",
            False,
        )
        in mock_feature.mock_calls
    )
    counter = 1

    for vm in test_qapp.domains:
        if vm.klass == "AdminVM":
            continue
        if vm.name == "test-blue":
            # this vm wasn't actually changed
            continue
        state = False if vm.name != "test-red" else None
        assert call(vm, handler.FEATURE_NAME, state) in mock_feature.mock_calls
        counter += 1

    assert len(mock_feature.mock_calls) == counter


@patch("qubes_config.global_config.vm_flowbox.ask_question")
def test_updates_check_reset(mock_question, real_builder, test_qapp):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "config.default.qubes-update-check",
            None,
        )
    ] = b"0\x001"
    test_qapp.expected_calls[
        ("test-red", "admin.vm.feature.Get", "service.qubes-update-check", None)
    ] = b"0\x00"
    test_qapp.expected_calls[
        (
            "test-blue",
            "admin.vm.feature.Get",
            "service.qubes-update-check",
            None,
        )
    ] = b"0\x00"

    handler = UpdateCheckerHandler(real_builder, test_qapp)

    # make some changes
    handler.dom0_update_check.set_active(False)
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-vm"])

    mock_question.return_value = Gtk.ResponseType.YES
    for child in handler.flowbox_handler.flowbox.get_children():
        if hasattr(child, "vm") and str(child.vm) == "test-vm":
            child._remove_self()
    assert mock_question.mock_calls

    handler.disable_radio.set_active(True)
    handler.exceptions_check.set_active(True)
    handler.flowbox_handler.add_selected_vm(test_qapp.domains["test-vm"])

    # reset
    handler.reset()
    assert handler.dom0_update_check.get_active()
    assert handler.enable_radio.get_active()
    assert handler.exceptions_check.get_active()
    assert handler.flowbox_handler.selected_vms == [
        test_qapp.domains["test-blue"],
        test_qapp.domains["test-red"],
    ]


def test_update_proxy_init_no_whonix(
    real_builder, test_qapp, test_policy_manager
):
    handler = UpdateProxy(
        real_builder, test_qapp, test_policy_manager, "proxy-test", "proxy"
    )

    # check default state
    assert not handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-net"
    assert not handler.current_exception_rules
    assert not handler.whonix_updatevm_box.get_visible()


def test_update_proxy_init_whonix(
    real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-test",
        "proxy",
    )

    # check default state
    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-net"
    assert handler.whonix_updatevm_model.get_selected() == "sys-whonix"
    assert not handler.current_exception_rules
    assert handler.whonix_updatevm_box.get_visible()


def test_update_proxy_init_policy_no_whonix(
    real_builder, test_qapp, test_policy_manager
):
    policy = """
Proxy * @type:TemplateVM @default allow target=sys-firewall
"""
    test_policy_manager.policy_client.policy_replace("proxy-file", policy)

    handler = UpdateProxy(
        real_builder, test_qapp, test_policy_manager, "proxy-file", "Proxy"
    )
    assert not handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-firewall"


def test_update_proxy_init_policy_whonix_new(
    real_builder, test_qapp_whonix, test_policy_manager
):
    policy = """
Proxy * @type:TemplateVM @default allow target=sys-firewall
"""
    test_policy_manager.policy_client.policy_replace("proxy-file", policy)

    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )
    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-firewall"
    assert handler.whonix_updatevm_model.get_selected() == "sys-whonix"


def test_update_proxy_init_policy_whonix(
    real_builder, test_qapp_whonix, test_policy_manager
):
    policy = """
Proxy * @type:TemplateVM @default allow target=sys-firewall
Proxy * @tag:whonix-updatevm @default allow target=anon-whonix
"""
    test_policy_manager.policy_client.policy_replace("proxy-file", policy)

    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )
    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-firewall"
    assert handler.whonix_updatevm_model.get_selected() == "anon-whonix"


def test_update_proxy_init_policy_exc(
    real_builder, test_qapp_whonix, test_policy_manager
):
    policy = """
Proxy * fedora-36 @default allow target=sys-net
Proxy * @type:TemplateVM @default allow target=sys-firewall
Proxy * @tag:whonix-updatevm @default allow target=anon-whonix
"""
    test_policy_manager.policy_client.policy_replace("proxy-file", policy)

    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )
    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-firewall"
    assert handler.whonix_updatevm_model.get_selected() == "anon-whonix"
    assert len(handler.current_exception_rules) == 1

    for rule in handler.current_exception_rules:
        assert rule.source == "fedora-36"
        assert rule.target == "sys-net"

    assert len(handler.exception_list_handler.rule_list.get_children()) == 1


def test_update_proxy_add_exception(
    real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )

    assert not handler.current_exception_rules
    handler.exception_list_handler.add_button.clicked()

    for child in handler.exception_list_handler.rule_list.get_children():
        assert isinstance(child, NoActionListBoxRow)
        if not child.editing:
            assert False  # wait where is a non-edited row from??
        # source should have not-networked vms
        fedora36 = test_qapp_whonix.domains["fedora-36"]
        sysnet = test_qapp_whonix.domains["sys-net"]
        assert child.source_widget.model.is_vm_available(fedora36)
        assert not child.source_widget.model.is_vm_available(sysnet)

        # target should have only providing-network vms
        assert child.target_widget.model.is_vm_available(sysnet)
        assert not child.target_widget.model.is_vm_available(fedora36)

        # select stuff
        child.source_widget.model.select_value("fedora-36")
        child.target_widget.model.select_value("sys-net")

        child.validate_and_save()

    desired_rules = test_policy_manager.text_to_rules(
        "Proxy * fedora-36 @default allow target=sys-net"
    )
    assert [str(rule.raw_rule) for rule in handler.current_exception_rules] == [
        str(rule) for rule in desired_rules
    ]

    # if I keep clicking add, I won't get random useless rules
    handler.exception_list_handler.add_button.clicked()
    handler.exception_list_handler.add_button.clicked()
    handler.exception_list_handler.add_button.clicked()

    # and the amount of rows is under control
    assert len(handler.exception_list_handler.rule_list.get_children()) == 2

    handler.close_all_edits()

    assert [str(rule.raw_rule) for rule in handler.current_exception_rules] == [
        str(rule) for rule in desired_rules
    ]


def test_update_proxy_add_exception_err(
    real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )
    handler.exception_list_handler.add_button.clicked()

    # can't add update proxy without anon-gateway for whonix vm
    for child in handler.exception_list_handler.rule_list.get_children():
        assert isinstance(child, NoActionListBoxRow)
        if not child.editing:
            assert False  # wait where is a non-edited row from??

        assert child.source_widget.model.is_vm_available("whonix-gw-15")
        assert child.target_widget.model.is_vm_available("sys-net")
        child.source_widget.model.select_value("whonix-gw-15")
        child.target_widget.model.select_value("sys-net")

        with patch(
            "qubes_config.global_config.rule_list_widgets.show_error"
        ) as mock_error:
            child.validate_and_save()
            assert mock_error.mock_calls


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_update_proxy_save_updatevm(
    mock_feature, real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )

    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-net"
    assert handler.whonix_updatevm_model.get_selected() == "sys-whonix"

    assert handler.updatevm_model.is_vm_available("sys-firewall")
    assert handler.whonix_updatevm_model.is_vm_available("anon-whonix")

    handler.updatevm_model.select_value("sys-firewall")
    handler.whonix_updatevm_model.select_value("anon-whonix")

    with patch.object(handler.policy_manager, "save_rules") as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
            """Proxy * @tag:whonix-updatevm @default allow target=anon-whonix
Proxy * @type:TemplateVM @default allow target=sys-firewall
"""
        )
        assert len(mock_save.mock_calls) == 1
        file, rules, arg = mock_save.mock_calls[0].args
        assert arg is None
        assert file == "proxy-file"
        assert [str(rule) for rule in expected_rules] == [
            str(rule) for rule in rules
        ]

        assert len(mock_feature.mock_calls) == 4
        assert (
            call(
                test_qapp_whonix.domains["sys-firewall"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["anon-whonix"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-whonix"],
                "service.qubes-updates-proxy",
                None,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-net"],
                "service.qubes-updates-proxy",
                None,
            )
            in mock_feature.mock_calls
        )


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_update_proxy_apply(
    mock_feature, real_builder, test_qapp_whonix, test_policy_manager
):
    # pylint: disable=unused-argument
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )

    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-net"
    assert handler.whonix_updatevm_model.get_selected() == "sys-whonix"

    assert handler.updatevm_model.is_vm_available("sys-firewall")
    assert handler.whonix_updatevm_model.is_vm_available("anon-whonix")

    handler.updatevm_model.select_value("sys-firewall")
    handler.whonix_updatevm_model.select_value("anon-whonix")

    handler.save()

    handler.reset()

    assert str(handler.updatevm_model.get_selected()) == "sys-firewall"
    assert str(handler.whonix_updatevm_model.get_selected()) == "anon-whonix"


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_update_proxy_save_justwhonix(
    mock_feature, real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )

    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-net"
    assert handler.whonix_updatevm_model.get_selected() == "sys-whonix"

    assert handler.whonix_updatevm_model.is_vm_available("anon-whonix")
    handler.whonix_updatevm_model.select_value("anon-whonix")

    with patch.object(handler.policy_manager, "save_rules") as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
            """Proxy * @tag:whonix-updatevm @default allow target=anon-whonix
Proxy * @type:TemplateVM @default allow target=sys-net
"""
        )
        assert len(mock_save.mock_calls) == 1
        file, rules, arg = mock_save.mock_calls[0].args
        assert arg is None
        assert file == "proxy-file"
        assert [str(rule) for rule in expected_rules] == [
            str(rule) for rule in rules
        ]

        assert len(mock_feature.mock_calls) == 3
        assert (
            call(
                test_qapp_whonix.domains["anon-whonix"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-net"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-whonix"],
                "service.qubes-updates-proxy",
                None,
            )
            in mock_feature.mock_calls
        )


@patch("qubes_config.global_config.updates_handler.apply_feature_change")
def test_update_proxy_save_add_rule(
    mock_feature, real_builder, test_qapp_whonix, test_policy_manager
):
    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )

    handler.exception_list_handler.add_button.clicked()
    for child in handler.exception_list_handler.rule_list.get_children():
        assert isinstance(child, NoActionListBoxRow)
        if not child.editing:
            assert False  # wait where is a non-edited row from??
        # select stuff
        child.source_widget.model.select_value("fedora-36")
        child.target_widget.model.select_value("sys-firewall")
        child.validate_and_save()

    with patch.object(handler.policy_manager, "save_rules") as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
            """Proxy * fedora-36 @default allow target=sys-firewall
Proxy * @tag:whonix-updatevm @default allow target=sys-whonix
Proxy * @type:TemplateVM @default allow target=sys-net
"""
        )
        assert len(mock_save.mock_calls) == 1
        file, rules, arg = mock_save.mock_calls[0].args
        assert arg is None
        assert file == "proxy-file"
        assert [str(rule) for rule in expected_rules] == [
            str(rule) for rule in rules
        ]

        assert len(mock_feature.mock_calls) == 3
        assert (
            call(
                test_qapp_whonix.domains["sys-whonix"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-firewall"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )
        assert (
            call(
                test_qapp_whonix.domains["sys-net"],
                "service.qubes-updates-proxy",
                True,
            )
            in mock_feature.mock_calls
        )


def test_update_proxy_reset(
    real_builder, test_qapp_whonix, test_policy_manager
):
    policy = """
Proxy * fedora-36 @default allow target=sys-net
Proxy * @type:TemplateVM @default allow target=sys-firewall
Proxy * @tag:whonix-updatevm @default allow target=anon-whonix"""
    test_policy_manager.policy_client.policy_replace("proxy-file", policy)

    handler = UpdateProxy(
        real_builder,
        test_qapp_whonix,
        test_policy_manager,
        "proxy-file",
        "Proxy",
    )
    assert handler.has_whonix
    assert handler.updatevm_model.get_selected() == "sys-firewall"
    assert handler.whonix_updatevm_model.get_selected() == "anon-whonix"
    assert len(handler.current_exception_rules) == 1

    for rule in handler.current_exception_rules:
        assert rule.source == "fedora-36"
        assert rule.target == "sys-net"

    assert len(handler.exception_list_handler.rule_list.get_children()) == 1
    assert not handler.is_changed()

    # change things

    assert handler.updatevm_model.is_vm_available(
        test_qapp_whonix.domains["sys-net"]
    )
    handler.updatevm_model.select_value("sys-net")

    # add exception
    handler.exception_list_handler.add_button.clicked()
    for child in handler.exception_list_handler.rule_list.get_children():
        assert isinstance(child, NoActionListBoxRow)
        if not child.editing:
            continue
        # select stuff
        child.source_widget.model.select_value("fedora-35")
        child.target_widget.model.select_value("sys-firewall")
        child.validate_and_save()
        break
    else:
        assert False  # edited row not found

    assert handler.is_changed()

    handler.reset()
    assert handler.updatevm_model.get_selected() == "sys-firewall"
    assert handler.whonix_updatevm_model.get_selected() == "anon-whonix"
    assert len(handler.current_exception_rules) == 1

    for rule in handler.current_exception_rules:
        assert rule.source == "fedora-36"
        assert rule.target == "sys-net"

    assert len(handler.exception_list_handler.rule_list.get_children()) == 1
    assert not handler.is_changed()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_complete_handler(
    mock_output, real_builder, test_qapp, test_policy_manager
):
    mock_output.return_value = ALL_ENABLED
    handler = UpdatesHandler(test_qapp, test_policy_manager, real_builder)

    # check if dom0 updatevm worked
    assert (
        handler.dom0_updatevm_model.get_selected()
        == test_qapp.domains["sys-net"]
    )

    # change selection
    assert handler.dom0_updatevm_model.is_vm_available(
        test_qapp.domains["sys-firewall"]
    )
    handler.dom0_updatevm_model.select_value("sys-firewall")

    # check that we have some unsaved
    assert "dom0 Update Proxy" in handler.get_unsaved()

    # and change some more stuff
    handler.update_checker.dom0_update_check.set_active(False)
    assert "dom0 Update Proxy" in handler.get_unsaved()
    assert 'dom0 "check for updates"' in handler.get_unsaved()

    # and reset
    handler.reset()

    assert handler.get_unsaved() == ""
    assert (
        handler.dom0_updatevm_model.get_selected()
        == test_qapp.domains["sys-net"]
    )
    assert handler.update_checker.dom0_update_check.get_active()


@patch("qubes_config.global_config.updates_handler.qrexec_call")
def test_complete_handle_dom0updatevm(
    mock_output, real_builder, test_qapp, test_policy_manager
):
    mock_output.return_value = ""
    handler = UpdatesHandler(test_qapp, test_policy_manager, real_builder)

    # check if dom0 updatevm worked
    assert (
        handler.dom0_updatevm_model.get_selected()
        == test_qapp.domains["sys-net"]
    )

    # change selection
    assert handler.dom0_updatevm_model.is_vm_available(
        test_qapp.domains["sys-firewall"]
    )
    handler.dom0_updatevm_model.select_value("sys-firewall")

    with pytest.raises(AssertionError):
        # should fail, no qapp call provided
        handler.save()

    # and now we provide the call

    test_qapp.expected_calls[
        ("dom0", "admin.property.Set", "updatevm", b"sys-firewall")
    ] = b"0\x00"

    handler.save()
