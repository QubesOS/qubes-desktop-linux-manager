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
import asyncio
import gi

from unittest.mock import patch, call, Mock, AsyncMock

import pytest

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk

from qui.updater.intro_page import UpdateRowWrapper
from qui.updater.progress_page import ProgressPage, QubeUpdateDetails
from qui.updater.tests.conftest import mock_settings, expected_row, run_coroutine
from qui.updater.utils import ListWrapper, UpdateStatus

# pylint: disable=redefined-outer-name


@pytest.fixture
def mock_callback():
    return Mock()


@pytest.fixture
def progress_page(
    real_builder,
    mock_label,
    mock_next_button,
    mock_cancel_button,
    mock_callback,
):
    """Fixture providing an instantiated ProgressPage with standard mocks."""
    return ProgressPage(
        real_builder,
        Mock(),
        mock_label,
        mock_next_button,
        mock_cancel_button,
        mock_callback,
    )


@patch("asyncio.get_running_loop")
def test_init_update(
    mock_get_running_loop,
    progress_page,
    mock_next_button,
    mock_cancel_button,
    mock_label,
    mock_tree_view,
    all_vms_list,
    mock_callback,
):
    sentinel = object()
    mock_loop = Mock()
    mock_loop.create_task.return_value = sentinel
    mock_get_running_loop.return_value = mock_loop
    sut = progress_page

    sut.progress_list = mock_tree_view
    # avoid creating a real (never-awaited) coroutine object
    sut.perform_update = Mock()

    sut.init_update(all_vms_list, mock_settings)

    assert not mock_next_button.sensitive
    assert mock_cancel_button.sensitive
    assert mock_cancel_button.visible
    assert mock_cancel_button.label == "_Cancel updates"
    mock_loop.create_task.assert_called_once()
    assert sut.update_task is sentinel

    assert mock_label.text == "Update in progress..."
    assert mock_label.halign == Gtk.Align.CENTER

    assert sut.progress_list.model == all_vms_list.list_store_raw
    mock_callback.assert_not_called()


@patch("gi.repository.GLib.idle_add")
def test_perform_update(
    idle_add,
    progress_page,
    mock_next_button,
    mock_cancel_button,
    mock_label,
    updateable_vms_list,
    mock_callback,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list

    class VMConsumer:
        async def __call__(self, vm_rows, *args, **kwargs):
            self.vm_rows = vm_rows

    sut.update_selected = VMConsumer()

    run_coroutine(sut.perform_update(mock_settings))

    assert len(sut.update_selected.vm_rows) == len(sut.vms_to_update)

    calls = [
        call(mock_next_button.set_sensitive, True),
        call(mock_label.set_text, "Update finished"),
        call(mock_cancel_button.set_visible, False),
    ]
    idle_add.assert_has_calls(calls, any_order=True)
    mock_callback.assert_called_once()


@patch("gi.repository.GLib.idle_add")
@pytest.mark.parametrize(
    "interrupted",
    (
        pytest.param(True, id="interrupted"),
        pytest.param(False, id="not interrupted"),
    ),
)
def test_update_templates(
    idle_add,
    interrupted,
    progress_page,
    updateable_vms_list,
    mock_text_view,
    mock_settings,
    mock_callback,
):
    sut = progress_page

    sut.do_update_selected = AsyncMock()
    total_progress = []
    sut.set_total_progress = lambda prog: total_progress.append(prog)

    sut.update_details.progress_textview = mock_text_view
    # chose vm to show details
    sut.update_details.active_row = updateable_vms_list[0]
    for i, row in enumerate(updateable_vms_list):
        row.buffer = f"Details {i}"

    if interrupted:
        sut.interrupt_update()
    run_coroutine(sut.update_selected(updateable_vms_list, mock_settings))

    sut.update_details.set_active_row(updateable_vms_list[2])

    calls = [
        call(sut.set_total_progress, 100),
        call(mock_text_view.buffer.set_text, "Details 0"),
        call(mock_text_view.buffer.set_text, "Details 2"),
    ]
    idle_add.assert_has_calls(calls, any_order=True)
    if not interrupted:
        sut.do_update_selected.assert_called()
    mock_callback.assert_not_called()


def test_do_update_selected(
    progress_page,
    test_qapp,
    mock_list_store,
    mock_settings,
    mock_callback,
):
    class MockProc:
        def __init__(self):
            self.returncode = None

        async def wait(self):
            self.returncode = 40
            return self.returncode

    mock_proc = MockProc()
    mock_create = AsyncMock(return_value=mock_proc)

    sut = progress_page
    sut.read_stderrs = AsyncMock()
    sut.read_stdouts = AsyncMock()

    to_update = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass in ("AdminVM", "TemplateVM", "StandaloneVM"):
            expected_row(vm.name, test_qapp)
            to_update.append_vm(vm)

    rows = {row.name: row for row in to_update}

    with patch("asyncio.create_subprocess_exec", mock_create):
        run_coroutine(sut.do_update_selected(rows, mock_settings))

    mock_create.assert_called_once_with(
        "qubes-vm-update",
        "--show-output",
        "--just-print-progress",
        "--force-update",
        "--targets",
        ",".join(list(rows.keys())),
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    sut.read_stderrs.assert_called_once_with(mock_proc, rows)
    sut.read_stdouts.assert_called_once_with(mock_proc, rows)
    mock_callback.assert_not_called()
    assert sut.retcode == 40


def test_get_update_summary(
    progress_page,
    updateable_vms_list,
    mock_callback,
):
    sut = progress_page

    updateable_vms_list[0].set_status(UpdateStatus.NoUpdatesFound)
    updateable_vms_list[1].set_status(UpdateStatus.Error)
    updateable_vms_list[2].set_status(UpdateStatus.Cancelled)
    updateable_vms_list[3].set_status(UpdateStatus.Success)

    sut.vms_to_update = updateable_vms_list

    updated, no_updates, failed, cancelled = sut.get_update_summary()

    assert updated == 1
    assert no_updates == 1
    assert failed == 1
    assert cancelled == 1
    mock_callback.assert_not_called()


def test_set_active_row(real_builder, updateable_vms_list):
    sut = QubeUpdateDetails(real_builder)
    row = updateable_vms_list[0]
    sut.set_active_row(row)

    assert sut.details_label.get_text().strip() == "Details for"
    assert sut.qube_label.get_text().strip() == str(row.name)
    assert sut.qube_icon.get_visible()
    assert sut.qube_label.get_visible()
    assert sut.colon.get_visible()
    assert sut.progress_scrolled_window.get_visible()
    assert sut.progress_textview.get_visible()
    assert sut.copy_button.get_visible()
    assert not sut.restart_button.get_visible()


def test_set_active_row_none(real_builder):
    sut = QubeUpdateDetails(real_builder)

    sut.set_active_row(None)

    assert sut.details_label.get_text() == "Select a qube to see details."
    assert not sut.qube_icon.get_visible()
    assert not sut.qube_label.get_visible()
    assert not sut.colon.get_visible()
    assert not sut.progress_scrolled_window.get_visible()
    assert not sut.progress_textview.get_visible()
    assert not sut.copy_button.get_visible()
    assert not sut.restart_button.get_visible()


def test_set_active_row_error_state(real_builder, updateable_vms_list):
    sut = QubeUpdateDetails(real_builder)
    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)
    sut.set_active_row(row)

    assert sut.copy_button.get_visible()
    assert sut.restart_button.get_visible()


def test_set_active_row_cancelled_state(real_builder, updateable_vms_list):
    sut = QubeUpdateDetails(real_builder)
    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Cancelled)
    sut.set_active_row(row)

    assert sut.copy_button.get_visible()
    assert sut.restart_button.get_visible()


def test_on_restart_clicked(real_builder, updateable_vms_list):
    mock_restart = Mock()
    sut = QubeUpdateDetails(real_builder, restart_callback=mock_restart)
    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)
    sut.set_active_row(row)
    assert sut.restart_button.get_visible()

    sut.on_restart_clicked(sut.restart_button)

    assert not sut.restart_button.get_visible()
    mock_restart.assert_called_once_with(row)


def test_restart_qube_update(
    progress_page,
    updateable_vms_list,
    mock_next_button,
    mock_label,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings

    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)
    sut.update_details.set_active_row(row)
    assert sut.update_details.restart_button.get_visible()

    sut.do_update_selected = AsyncMock()

    task = sut.restart_qube_update(row)
    assert not sut.update_details.restart_button.get_visible()
    assert row.status == UpdateStatus.InProgress
    assert mock_label.text == "Update in progress..."
    assert not mock_next_button.sensitive

    run_coroutine(task)
    sut.do_update_selected.assert_called_once()
    assert sut.do_update_selected.call_args[0][0] == {row.name: row}


def test_restart_qube_update_while_already_in_progress(
    progress_page,
    updateable_vms_list,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings

    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.InProgress)

    res = sut.restart_qube_update(row)
    assert res is None


@patch("gi.repository.GLib.idle_add")
def test_restart_resets_exit_triggered_and_reshows_cancel(
    idle_add,
    progress_page,
    updateable_vms_list,
    mock_cancel_button,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings
    sut.exit_triggered = True

    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)
    sut.do_update_selected = AsyncMock()

    task = sut.restart_qube_update(row)
    assert not sut.exit_triggered
    idle_add.assert_has_calls(
        [
            call(mock_cancel_button.set_label, "_Cancel updates"),
            call(mock_cancel_button.set_sensitive, True),
            call(mock_cancel_button.show),
        ],
        any_order=True,
    )
    run_coroutine(task)


def test_restart_updates_task_and_gathers_tasks(
    progress_page,
    updateable_vms_list,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings

    row1 = updateable_vms_list[0]
    row2 = updateable_vms_list[1]
    row1.set_status(UpdateStatus.Error)
    row2.set_status(UpdateStatus.Error)

    sut.do_update_selected = AsyncMock()

    task1 = sut.restart_qube_update(row1)
    assert sut.update_task is task1

    task2 = sut.restart_qube_update(row2)
    assert sut.update_task is not task2
    assert not sut.update_task.done()

    run_coroutine(sut.update_task)
    assert task1.done()
    assert task2.done()


@patch("gi.repository.GLib.idle_add")
def test_restart_recovers_in_progress_row_on_cancel(
    idle_add,
    progress_page,
    updateable_vms_list,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings

    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)

    async def fake_update(_rows, _settings):
        sut.exit_triggered = True

    sut.do_update_selected = fake_update

    task = sut.restart_qube_update(row)
    run_coroutine(task)

    idle_add.assert_any_call(row.set_status, UpdateStatus.Cancelled)


@patch("gi.repository.GLib.idle_add")
def test_restart_recovers_in_progress_row_on_error_retcode(
    idle_add,
    progress_page,
    updateable_vms_list,
    mock_settings,
):
    sut = progress_page
    sut.vms_to_update = updateable_vms_list
    sut.settings = mock_settings

    row = updateable_vms_list[0]
    row.set_status(UpdateStatus.Error)

    async def fake_update(_rows, _settings):
        sut.retcode = 1

    sut.do_update_selected = fake_update

    task = sut.restart_qube_update(row)
    run_coroutine(task)

    idle_add.assert_any_call(row.set_status, UpdateStatus.Error)
