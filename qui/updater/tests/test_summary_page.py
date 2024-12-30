# coding=utf-8
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023  Piotr Bartman <prbartman@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
import pytest
from unittest.mock import patch, call, Mock

import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk  # isort:skip

from qubes_config.widgets.gtk_utils import RESPONSES_OK
from qui.updater.intro_page import UpdateRowWrapper

from qui.updater.summary_page import (
    SummaryPage,
    AppVMType,
    RestartStatus,
    RestartRowWrapper,
)
from qui.updater.utils import HeaderCheckbox, UpdateStatus, ListWrapper


@patch("qui.updater.summary_page.SummaryPage.refresh_buttons")
def test_show(
    refresh_buttons,
    real_builder,
    test_qapp,
    appvms_list,
    mock_next_button,
    mock_cancel_button,
):
    test_qapp.expected_calls[
        ("test-blue", "admin.vm.feature.Get", "restart-after-update", None)
    ] = (b"0\x00" + "".encode())

    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )

    sut.list_store = appvms_list

    sut.show(0, 1, 2)

    assert sut.stack.get_visible_child() == sut.page
    assert (
        sut.label_summary.get_text() == "0 qubes updated successfully.\n"
        "1 qube attempted to update but found no updates.\n"
        "2 qubes failed to update."
    )
    assert sut.cancel_button.visible
    assert sut.cancel_button.label == "_Back"
    refresh_buttons.assert_called_once()


def test_on_header_toggled(
    real_builder, test_qapp, appvms_list, mock_next_button, mock_cancel_button
):
    test_qapp.expected_calls[
        ("test-blue", "admin.vm.feature.Get", "restart-after-update", None)
    ] = (b"0\x00" + "".encode())

    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )

    sut.list_store = appvms_list
    all_num = len(appvms_list)
    sut.head_checkbox._allowed[0] = AppVMType.SERVICEVM
    service_num = 3
    sut.head_checkbox._allowed[1] = AppVMType.NON_SERVICEVM
    non_excluded_num = 6

    sut.head_checkbox.state = HeaderCheckbox.NONE

    for expected in (0, service_num, non_excluded_num, all_num, 0):
        selected_num = len([row for row in sut.list_store if row.selected])
        assert selected_num == expected
        assert (
            sut.head_checkbox_button.get_inconsistent()
            and expected not in (0, all_num)
            or sut.head_checkbox_button.get_active()
            and expected == all_num
            or not sut.head_checkbox_button.get_active()
            and expected == 0
        )

        sut.on_header_toggled(None)


def test_on_checkbox_toggled(
    real_builder,
    test_qapp,
    appvms_list,
    mock_next_button,
    mock_cancel_button,
    mock_settings,
):
    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )

    sut.list_store = appvms_list
    sut.head_checkbox._allowed[0] = AppVMType.SERVICEVM
    sut.head_checkbox._allowed[1] = AppVMType.NON_SERVICEVM

    sut.head_checkbox.state = HeaderCheckbox.NONE
    sut.head_checkbox.set_buttons()

    # no selected row
    assert not sut.head_checkbox_button.get_inconsistent()
    assert not sut.head_checkbox_button.get_active()

    # only one row selected
    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    assert sut.head_checkbox_button.get_inconsistent()

    for i in range(len(sut.list_store)):
        sut.on_checkbox_toggled(_emitter=None, path=(i,))

    # almost all rows selected (except one)
    assert sut.head_checkbox_button.get_inconsistent()

    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    # all rows selected
    assert not sut.head_checkbox_button.get_inconsistent()
    assert sut.head_checkbox_button.get_active()

    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    # almost all rows selected (except one)
    assert sut.head_checkbox_button.get_inconsistent()

    for i in range(len(sut.list_store)):
        if i == 3:
            continue
        sut.on_checkbox_toggled(_emitter=None, path=(i,))

    # no selected row
    assert not sut.head_checkbox_button.get_inconsistent()
    assert not sut.head_checkbox_button.get_active()


# expected data based on test_qapp setup
UP_VMS = 7
UP_SERVICE_VMS = 3
UP_APP_VMS = 4


@pytest.mark.parametrize(
    "restart_service_vms, restart_other_vms, excluded, expected",
    (
        pytest.param(True, True, (), UP_VMS),
        pytest.param(True, False, (), UP_SERVICE_VMS),
        pytest.param(False, False, (), 0),
        pytest.param(False, True, (), UP_APP_VMS),
        pytest.param(True, True, ("test-blue",), UP_VMS - 1),
        pytest.param(True, False, ("test-blue",), UP_SERVICE_VMS),
        pytest.param(False, True, ("sys-usb",), UP_APP_VMS),
        pytest.param(True, False, ("sys-usb",), UP_SERVICE_VMS - 1),
    ),
)
def test_populate_restart_list(
    restart_service_vms,
    restart_other_vms,
    excluded,
    expected,
    real_builder,
    test_qapp,
    updatable_vms_list,
    mock_next_button,
    mock_cancel_button,
    mock_settings,
    mock_tree_view,
):
    mock_settings.restart_other_vms = restart_other_vms
    mock_settings.restart_service_vms = restart_service_vms
    for exclude in excluded:
        test_qapp.expected_calls[
            (exclude, "admin.vm.feature.Get", "restart-after-update", None)
        ] = (b"0\x00" + "".encode())

    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )
    sut.summary_list = mock_tree_view

    for row in updatable_vms_list:
        row.set_status(UpdateStatus.Success)
        if row.vm.klass == "TemplateVM":
            for i, appvm in enumerate(row.vm.appvms):
                if i < UP_VMS:
                    appvm.is_running = lambda *_args: True
                else:
                    appvm.is_running = lambda *_args: False

    sut.populate_restart_list(True, updatable_vms_list, mock_settings)

    assert len(sut.list_store) == UP_VMS
    assert sum(row.selected for row in sut.list_store) == expected


@patch("qubes_config.widgets.gtk_utils.show_dialog")
@patch("qui.updater.summary_page.show_dialog")
@patch("gi.repository.Gtk.Image.new_from_pixbuf")
@patch("threading.Thread")
@pytest.mark.parametrize(
    "alive_requests_max, status",
    (
        pytest.param(3, RestartStatus.OK),
        pytest.param(0, RestartStatus.OK),
        pytest.param(1, RestartStatus.ERROR_TMPL_DOWN),
        pytest.param(1, RestartStatus.NOTHING_TO_DO),
    ),
)
def test_restart_selected_vms(
    mock_threading,
    mock_new_from_pixbuf,
    mock_show_dialog_qui,
    mock_show_dialog,
    alive_requests_max,
    status,
    mock_thread,
    test_qapp,
    real_builder,
    mock_next_button,
    mock_cancel_button,
):
    # ARRANGE
    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )
    mock_thread.alive_requests_max = alive_requests_max
    mock_threading.return_value = mock_thread
    icon = "icon"
    mock_new_from_pixbuf.return_value = icon

    class MockDialog:
        def __init__(self):
            self.run_calls = 0
            self.destroy_calls = 0
            self.show_calls = 0
            self.deletable = True

        def run(self):
            self.run_calls += 1
            return Gtk.ResponseType.DELETE_EVENT

        def destroy(self):
            self.destroy_calls += 1

        def show(self):
            self.show_calls += 1

        def set_deletable(self, deletable):
            self.deletable = deletable

    mock_final_dialog = MockDialog()
    mock_waiting_dialog = MockDialog()
    mock_show_dialog.return_value = mock_final_dialog
    mock_show_dialog_qui.return_value = mock_waiting_dialog
    sut.status = status

    # ACT
    sut.restart_selected_vms(show_only_error=False)

    # ASSERT

    # waiting dialog cannot be closed
    if alive_requests_max:
        assert mock_waiting_dialog.run_calls == 0
        assert mock_waiting_dialog.show_calls == 1
        assert mock_waiting_dialog.destroy_calls == 1
        assert not mock_waiting_dialog.deletable
    else:
        assert mock_waiting_dialog.run_calls == 0
        assert mock_waiting_dialog.show_calls == 0
        assert mock_waiting_dialog.destroy_calls == 0

    if status == RestartStatus.NOTHING_TO_DO:
        mock_show_dialog.assert_not_called()
    else:
        # final dialog is blocking (run)
        assert mock_final_dialog.run_calls == 1
        assert mock_final_dialog.show_calls == 0
        assert mock_final_dialog.destroy_calls == 1
        assert mock_final_dialog.deletable

        calls = []
        if status == RestartStatus.OK:
            calls = [
                call(
                    None,
                    "Success",
                    "All qubes were restarted/shutdown successfully.",
                    RESPONSES_OK,
                    icon,
                )
            ]
        if status.is_error():
            calls = [
                call(
                    None,
                    "Failure",
                    "During restarting following errors occurs: " + sut.err,
                    RESPONSES_OK,
                    icon,
                )
            ]
        mock_show_dialog.assert_has_calls(calls)


@patch("qui.updater.summary_page.wait_for_domain_shutdown")
def test_perform_restart(
    _mock_wait_for_domain_shutdown,
    test_qapp,
    real_builder,
    mock_next_button,
    mock_cancel_button,
    mock_list_store,
):
    # ARRANGE

    expected_state_calls = [
        (tmpl, "admin.vm.CurrentState", None, None)
        for tmpl in ("fedora-35", "fedora-36")
    ]
    for call_ in expected_state_calls:
        test_qapp.expected_calls[call_] = b"0\x00power_state=Running mem=1024"

    to_shutdown = (
        "fedora-35",
        "fedora-36",
        "sys-firewall",
        "sys-net",
        "sys-usb",
        "test-blue",
        "test-red",
        "test-vm",
        "vault",
    )
    expected_shutdown_calls = [
        (tmpl, "admin.vm.Shutdown", "force", None) for tmpl in to_shutdown
    ]
    for call_ in expected_shutdown_calls:
        test_qapp.expected_calls[call_] = b"0\x00"

    to_start = (
        "sys-firewall",
        "sys-net",
        "sys-usb",
    )
    expected_start_calls = [
        (tmpl, "admin.vm.Start", None, None) for tmpl in to_start
    ]
    for call_ in expected_start_calls:
        test_qapp.expected_calls[call_] = b"0\x00"

    mock_log = Mock()
    sut = SummaryPage(
        real_builder,
        mock_log,
        mock_next_button,
        mock_cancel_button,
        back_by_row_selection=lambda *args: None,  # callback
    )

    sut.updated_tmpls = ListWrapper(UpdateRowWrapper, mock_list_store)
    sut.list_store = ListWrapper(RestartRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass in ("TemplateVM",):
            sut.updated_tmpls.append_vm(vm)
        if vm.klass in ("AppVM",):
            sut.list_store.append_vm(vm)
            sut.list_store[-1].selected = True

    # ACT
    sut.perform_restart()

    # ASSERT
    assert all(
        item in test_qapp.actual_calls
        for item in expected_state_calls
        + expected_shutdown_calls
        + expected_start_calls
    )
