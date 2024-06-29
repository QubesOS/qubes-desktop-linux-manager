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
from unittest.mock import patch, call, Mock

import pytest

from qui.updater.updater import QubesUpdater, parse_args
from qui.updater.summary_page import SummaryPage, RestartStatus
from qubes_config.widgets import gtk_utils


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
def test_setup(populate_vm_list, _mock_logging, __mock_logging, test_qapp):
    sut = QubesUpdater(test_qapp, parse_args((), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('subprocess.check_output')
@patch('qui.updater.intro_page.IntroPage.select_rows_ignoring_conditions')
@patch('qui.updater.intro_page.IntroPage.get_vms_to_update')
def test_setup_non_interactive_nothing_to_do(
        get_vms, select, subproc, _mock_logging, __mock_logging, test_qapp):
    sut = QubesUpdater(test_qapp, parse_args(('-n',), test_qapp))
    subproc.return_value = b''
    get_vms.return_value = ()
    sut.perform_setup()
    select.assert_called_once()
    get_vms.assert_called_once()


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
@patch('qui.updater.intro_page.IntroPage.select_rows')
def test_setup_update_if_available(
        select, populate_vm_list, _mock_logging, __mock_logging, test_qapp):
    sut = QubesUpdater(
        test_qapp, parse_args(('--update-if-available',), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    select.assert_called_once()
    assert (sut.intro_page.head_checkbox.state ==
            sut.intro_page.head_checkbox.SAFE)


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
@patch('qui.updater.intro_page.IntroPage.select_rows')
def test_setup_force_update(
        select, populate_vm_list, _mock_logging, __mock_logging, test_qapp):
    sut = QubesUpdater(
        test_qapp, parse_args(('--force-update',), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    select.assert_called_once()
    assert (sut.intro_page.head_checkbox.state ==
            sut.intro_page.head_checkbox.ALL)


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
@patch('qui.updater.intro_page.IntroPage.select_rows')
@patch('qui.updater.updater_settings.get_boolean_feature')
@pytest.mark.parametrize(
    "args, sys, non_sys",
    (
        pytest.param(('--apply-to-all',), True, True, id="all"),
        pytest.param(('--apply-to-sys',), True, None, id="sys"),
        pytest.param(('--no-apply',), False, False, id="none"),
    )
)
def test_setup_apply(
        get_feature, __select, populate_vm_list, _mock_logging, __mock_logging, test_qapp, args, sys, non_sys):
    sut = QubesUpdater(
        test_qapp, parse_args(args, test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    assert sut.settings.restart_service_vms == sys
    assert (non_sys is not None and sut.settings.restart_other_vms == non_sys
            or sut.settings.overrides.apply_to_other is None)


@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
@pytest.mark.parametrize(
    "update_results, ret_code",
    (
        pytest.param((0, 0, 0, 0), 100, id="nothing to do"),
        pytest.param((0, 0, 1, 0), 1, id="failed"),
        pytest.param((0, 0, 1, 0), 40, id="failed with retcode"),
        pytest.param((0, 0, 0, 1), 130, id="cancelled"),
        pytest.param((0, 0, 1, 1), 130, id="failed + cancelled"),
        pytest.param((0, 1, 0, 0), 100, id="no updates"),
        pytest.param((0, 1, 1, 0), 1, id="no updates + failed"),
        pytest.param((1, 0, 0, 0), 0, id="success"),
        pytest.param((1, 0, 1, 0), 1, id="success + failed"),
        pytest.param((1, 1, 0, 0), 0, id="success + no updated"),
        pytest.param((1, 1, 1, 1), 130, id="all"),
    )
)
def test_retcode(_populate_vm_list, _mock_logging, __mock_logging,
                 update_results, ret_code, test_qapp):
    sut = QubesUpdater(test_qapp, parse_args((), test_qapp))
    sut.perform_setup()

    sut.intro_page.get_vms_to_update = Mock()
    vms_to_update = Mock()
    sut.intro_page.get_vms_to_update.return_value = vms_to_update

    def set_vms(_vms_to_update, _settings):
        sut.progress_page.vms_to_update = _vms_to_update
    sut.progress_page.init_update = Mock(side_effect=set_vms)

    sut.next_clicked(None)

    assert not sut.intro_page.active
    assert sut.progress_page.is_visible
    sut.progress_page.init_update.assert_called_once_with(
        vms_to_update, sut.settings)

    # set sut.summary_page.is_populated = False
    sut.summary_page.list_store = None
    def populate(**_kwargs):
        sut.summary_page.list_store = []
    sut.summary_page.populate_restart_list = Mock(side_effect=populate)
    sut.progress_page.retcode = ret_code
    sut.progress_page.get_update_summary = Mock()
    sut.progress_page.get_update_summary.return_value = update_results
    sut.summary_page.show = Mock()
    sut.summary_page.show.return_value = None

    sut.next_clicked(None)

    sut.summary_page.populate_restart_list.assert_called_once_with(
        restart=True, vm_updated=vms_to_update, settings=sut.settings)
    assert sut.retcode == ret_code
    expected_summary = (update_results[0], update_results[1],
                        update_results[2] + update_results[3])
    sut.summary_page.show.assert_called_once_with(*expected_summary)


@patch('threading.Thread')
@patch('qui.updater.updater.show_dialog_with_icon')
@patch('qui.updater.summary_page.show_dialog_with_icon')
@patch('logging.FileHandler')
@patch('logging.getLogger')
@patch('qui.updater.intro_page.IntroPage.populate_vm_list')
def test_dialog(_populate_vm_list, _mock_logging, __mock_logging,
                dialog, dialog2, thread, test_qapp, monkeypatch):
    monkeypatch.setattr(SummaryPage, "perform_restart", lambda *_: None)
    sut = QubesUpdater(test_qapp, parse_args((), test_qapp))
    sut.perform_setup()

    sut.cliargs.non_interactive = True

    sut.intro_page.get_vms_to_update = Mock()
    vms_to_update = Mock()
    sut.intro_page.get_vms_to_update.return_value = vms_to_update

    def set_vms(_vms_to_update, _settings):
        sut.progress_page.vms_to_update = _vms_to_update
    sut.progress_page.init_update = Mock(side_effect=set_vms)

    sut.next_clicked(None)

    assert not sut.intro_page.active
    assert sut.progress_page.is_visible
    sut.progress_page.init_update.assert_called_once_with(
        vms_to_update, sut.settings)

    # set sut.summary_page.is_populated = False
    sut.summary_page.list_store = None
    def populate(**_kwargs):
        sut.summary_page.list_store = []
    sut.summary_page.populate_restart_list = Mock(side_effect=populate)
    sut.progress_page.get_update_summary = Mock()
    sut.progress_page.get_update_summary.return_value = (1, 0, 0, 0)
    sut.summary_page.show = Mock()
    sut.summary_page.show.return_value = None

    def ok(**_kwargs):
        sut.summary_page.status = RestartStatus.OK
        t = Mock()
        t.is_alive = Mock(return_value=False)
        return t
    thread.side_effect = ok

    sut.summary_page.status = RestartStatus.OK
    sut.next_clicked(None)

    dialog2.assert_has_calls(calls=[call(
        None, "Success", "Qubes OS is up to date.",
        buttons=gtk_utils.RESPONSES_OK, icon_name="qubes-check-yes")])
    dialog.assert_not_called()
