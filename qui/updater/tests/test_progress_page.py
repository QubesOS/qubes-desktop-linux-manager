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
import gi
import subprocess

from unittest.mock import patch, call, Mock

import pytest

gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk

from qui.updater.intro_page import UpdateRowWrapper
from qui.updater.progress_page import ProgressPage, QubeUpdateDetails
from qui.updater.tests.conftest import mock_settings
from qui.updater.utils import ListWrapper, UpdateStatus


@patch('threading.Thread')
def test_init_update(
        mock_threading, mock_thread, real_builder, test_qapp,
        mock_next_button, mock_cancel_button, mock_label, mock_tree_view,
        all_vms_list):

    mock_threading.return_value = mock_thread
    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )

    sut.progress_list = mock_tree_view

    sut.init_update(all_vms_list, mock_settings)

    assert not mock_next_button.sensitive
    assert mock_cancel_button.sensitive
    assert mock_cancel_button.visible
    assert mock_cancel_button.label == "_Cancel updates"
    assert mock_thread.started

    assert mock_label.text == "Update in progress..."
    assert mock_label.halign == Gtk.Align.CENTER

    assert sut.progress_list.model == all_vms_list.list_store_raw
    mock_callback.assert_not_called()


@patch('gi.repository.GLib.idle_add')
def test_perform_update(
        idle_add, real_builder,
        mock_next_button, mock_cancel_button, mock_label, updatable_vms_list
):
    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )

    sut.vms_to_update = updatable_vms_list

    class VMConsumer:
        def __call__(self, vm_rows, *args, **kwargs):
            self.vm_rows = vm_rows

    sut.update_admin_vm = VMConsumer()
    sut.update_templates = VMConsumer()

    sut.perform_update(mock_settings)

    assert len(sut.update_admin_vm.vm_rows) == 1
    assert len(sut.update_templates.vm_rows) == 3

    calls = [call(mock_next_button.set_sensitive, True),
             call(mock_label.set_text, "Update finished"),
             call(mock_cancel_button.set_visible, False)]
    idle_add.assert_has_calls(calls, any_order=True)
    mock_callback.assert_called_once()


@patch('gi.repository.GLib.idle_add')
@patch('subprocess.check_output', return_value=b'')
@pytest.mark.parametrize(
    "interrupted",
    (
        pytest.param(True, id="interrupted"),
        pytest.param(False, id="not interrupted"),
    )
)
def test_update_admin_vm(
        mock_subprocess, idle_add,  interrupted, real_builder, test_qapp,
        mock_next_button, mock_cancel_button, mock_label, mock_text_view,
        mock_list_store
):
    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )

    admins = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass in ("AdminVM",):
            admins.append_vm(vm)

    sut.update_details.progress_textview = mock_text_view
    # chose vm to show details
    sut.update_details.active_row = admins[0]
    admins[0].buffer = "Update details"

    if interrupted:
        sut.interrupt_update()
    sut.update_admin_vm(admins=admins)

    calls = [call(mock_text_view.buffer.set_text, "Update details")]
    idle_add.assert_has_calls(calls)
    if not interrupted:
        mock_subprocess.assert_called()
    mock_callback.assert_not_called()


@patch('gi.repository.GLib.idle_add')
@pytest.mark.parametrize(
    "interrupted",
    (
        pytest.param(True, id="interrupted"),
        pytest.param(False, id="not interrupted"),
    )
)
def test_update_templates(
        idle_add, interrupted, real_builder, updatable_vms_list,
        mock_next_button, mock_cancel_button, mock_label, mock_text_view
):
    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )

    sut.do_update_templates = Mock()
    total_progress = []
    sut.set_total_progress = lambda prog: total_progress.append(prog)

    sut.update_details.progress_textview = mock_text_view
    # chose vm to show details
    sut.update_details.active_row = updatable_vms_list[0]
    for i, row in enumerate(updatable_vms_list):
        row.buffer = f"Details {i}"

    if interrupted:
        sut.interrupt_update()
    sut.update_templates(updatable_vms_list, mock_settings)

    sut.update_details.set_active_row(updatable_vms_list[2])

    calls = [call(sut.set_total_progress, 100),
             call(mock_text_view.buffer.set_text, "Details 0"),
             call(mock_text_view.buffer.set_text, "Details 2"),
             ]
    idle_add.assert_has_calls(calls, any_order=True)
    if not interrupted:
        sut.do_update_templates.assert_called()
    mock_callback.assert_not_called()


@patch('subprocess.Popen')
def test_do_update_templates(
        mock_subprocess, real_builder, test_qapp,
        mock_next_button, mock_cancel_button, mock_label, mock_list_store,
        mock_settings
):
    class MockPorc:
        def __init__(self, finish_after_n_polls=2):
            self.polls = 0
            self.returncode = 40
            self.finish_after_n_polls = finish_after_n_polls

        def wait(self):
            """Mock waiting."""
            pass

        def poll(self):
            """After several polls return 0 (process finished)."""
            self.polls += 1
            if self.polls < self.finish_after_n_polls:
                return None
            return self.returncode


    mock_subprocess.return_value = MockPorc()

    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )
    sut.read_stderrs = lambda *_args, **_kwargs: None
    sut.read_stdouts = lambda *_args, **_kwargs: None

    to_update = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass in ("TemplateVM", "StandaloneVM"):
            to_update.append_vm(vm)

    rows = {row.name: row for row in to_update}

    sut.do_update_templates(rows, mock_settings)

    calls = [call(
        ['qubes-vm-update',
         '--show-output',
         '--just-print-progress',
         '--force-update',
         '--targets',
         'fedora-35,fedora-36,test-standalone'],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE)]
    mock_subprocess.assert_has_calls(calls)
    mock_callback.assert_not_called()
    assert sut.retcode == 40


def test_get_update_summary(
        real_builder,
        mock_next_button, mock_cancel_button, mock_label, updatable_vms_list
):
    mock_log = Mock()
    mock_callback = Mock()
    sut = ProgressPage(
        real_builder, mock_log, mock_label, mock_next_button,
        mock_cancel_button, mock_callback
    )

    updatable_vms_list[0].set_status(UpdateStatus.NoUpdatesFound)
    updatable_vms_list[1].set_status(UpdateStatus.Error)
    updatable_vms_list[2].set_status(UpdateStatus.Cancelled)
    updatable_vms_list[3].set_status(UpdateStatus.Success)

    sut.vms_to_update = updatable_vms_list

    updated, no_updates, failed, cancelled = sut.get_update_summary()

    assert updated == 1
    assert no_updates == 1
    assert failed == 1
    assert cancelled == 1
    mock_callback.assert_not_called()


def test_set_active_row(real_builder, updatable_vms_list):
    sut = QubeUpdateDetails(real_builder)
    row = updatable_vms_list[0]
    sut.set_active_row(row)

    assert sut.details_label.get_text().strip() == "Details for"
    assert sut.qube_label.get_text().strip() == str(row.name)
    assert sut.qube_icon.get_visible()
    assert sut.qube_label.get_visible()
    assert sut.colon.get_visible()
    assert sut.progress_scrolled_window.get_visible()
    assert sut.progress_textview.get_visible()
    assert sut.copy_button.get_visible()


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
