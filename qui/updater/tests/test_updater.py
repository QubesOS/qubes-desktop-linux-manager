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
from unittest.mock import patch, call, Mock, AsyncMock

import pytest

from qui.updater.updater import QubesUpdater, parse_args
from qui.updater.summary_page import RestartStatus
from qui.updater.tests.conftest import run_coroutine
from qubes_config.widgets import gtk_utils


def _make_updater(test_qapp, cliargs):
    """make QubesUpdater with a mock asyncio loop."""
    real_loop = asyncio.get_event_loop()
    loop = Mock()
    loop.scheduled = []
    loop.create_task.side_effect = (
        lambda coro: loop.scheduled.append(coro) or Mock()
    )
    loop.create_future.side_effect = real_loop.create_future
    return QubesUpdater(test_qapp, cliargs, loop)


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_setup(populate_vm_list, _mock_loger, _mock_log_handler, test_qapp):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_updater_enables_cache_and_owns_event_listener(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))

    assert test_qapp.cache_enabled is True
    assert sut.dispatcher is not None

    sut.loop.create_task.assert_called_once()
    assert sut.listen_events_task is not None


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_exit_cancels_event_listener(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.primary = True
    sut.listen_events_task = Mock()

    sut.exit_updater()

    sut.listen_events_task.cancel.assert_called_once()
    assert sut.exit_future.done()


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_window_close_interrupts_running_update(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.progress_page = Mock()
    running = Mock()
    running.done.return_value = False
    sut.progress_page.update_task = running
    sut.progress_page.exit_triggered = False
    sut.exit_updater = Mock()

    result = sut.window_close()

    # window must stay alive and exit is deferred to the scheduled coroutine
    assert result is True
    sut.exit_updater.assert_not_called()
    # `_interrupt_and_wait` coroutine was scheduled on the loop
    interrupt_coro = sut.loop.scheduled[-1]
    assert asyncio.iscoroutine(interrupt_coro)
    interrupt_coro.close()  # avoid 'coroutine never awaited' warning


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_window_close_exits_when_idle(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.progress_page = Mock()
    sut.progress_page.update_task = None
    sut.progress_page.exit_triggered = False
    sut.exit_updater = Mock()

    result = sut.window_close()

    assert result is False
    sut.exit_updater.assert_called_once()


@patch("qui.updater.updater.load_icon")
@patch("gi.repository.Gtk.Image.new_from_pixbuf")
@patch("qui.updater.updater.show_dialog")
@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_interrupt_and_wait_waits_then_exits(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    mock_show_dialog,
    _new_from_pixbuf,
    _load_icon,
    test_qapp,
):
    mock_show_dialog.return_value = Mock()
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.main_window = Mock()
    sut.progress_page = Mock()
    sut.exit_updater = Mock()
    # window close
    sut._exit_after_update = True

    async def scenario():
        sut.progress_page.update_task = asyncio.sleep(0)
        await sut._interrupt_and_wait()

    run_coroutine(scenario())

    sut.exit_updater.assert_called_once()


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_cancel_twice_schedules_single_notice(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.progress_page = Mock()
    running = Mock()
    running.done.return_value = False
    sut.progress_page.update_task = running
    sut.progress_page.exit_triggered = False

    # `interrupt_update()` sets `exit_triggered` synchronously
    def interrupt():
        sut.progress_page.exit_triggered = True

    sut.progress_page.interrupt_update = Mock(side_effect=interrupt)

    sut.cancel_updates()
    sut.cancel_updates()  # second click

    sut.progress_page.interrupt_update.assert_called_once()
    # ignore the coroutine scheduled at construction
    notices = [
        c for c in sut.loop.scheduled
        if asyncio.iscoroutine(c)
           and c.__qualname__.endswith("_interrupt_and_wait")
    ]
    assert len(notices) == 1
    for coro in sut.loop.scheduled:
        if asyncio.iscoroutine(coro):
            coro.close()


@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
def test_close_after_cancel_still_exits(
    _populate_vm_list,
    _get_logger,
    _file_handler,
    _listen_for_events,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
    sut.progress_page = Mock()
    running = Mock()
    running.done.return_value = False
    sut.progress_page.update_task = running
    sut.progress_page.exit_triggered = False

    def interrupt():
        sut.progress_page.exit_triggered = True

    sut.progress_page.interrupt_update = Mock(side_effect=interrupt)

    sut.cancel_updates()  # Cancel: does not request exit
    assert sut._exit_after_update is False

    result = sut.window_close()  # then close the window
    assert result is True
    # closing
    assert sut._exit_after_update is True
    # and no second notice (ignore the coroutine scheduled at construction)
    notices = [
        c for c in sut.loop.scheduled
        if asyncio.iscoroutine(c)
           and c.__qualname__.endswith("_interrupt_and_wait")
    ]
    assert len(notices) == 1
    for coro in sut.loop.scheduled:
        if asyncio.iscoroutine(coro):
            coro.close()


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("subprocess.check_output")
@patch("qui.updater.intro_page.IntroPage.select_rows_ignoring_conditions")
@patch("qui.updater.intro_page.IntroPage.get_vms_to_update")
def test_setup_non_interactive_nothing_to_do(
    get_vms, select, subproc, _mock_loger, _mock_log_handler, test_qapp
):

    sut = _make_updater(test_qapp, parse_args(("-n",), test_qapp))
    subproc.return_value = b"The admin VM will not be updated."
    get_vms.return_value = ()
    sut.perform_setup()
    select.assert_called_once()
    get_vms.assert_called_once()


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("subprocess.check_output")
@patch("qui.updater.intro_page.IntroPage.get_vms_to_update")
def test_setup_non_interactive_defers_update_start(
    get_vms, subproc, _mock_loger, _mock_log_handler, test_qapp
):
    sut = _make_updater(test_qapp, parse_args(("-n",), test_qapp))
    subproc.return_value = (
        b"Following templates and standalones will be updated:fedora-43"
    )
    get_vms.return_value = ("fedora-43",)
    sut.next_clicked = Mock()

    sut.perform_setup()

    # auto-start is only flagged; it must NOT be run during perform_setup
    # (app.run() has no running loop yet)
    assert sut.start_update is True
    assert not sut.do_nothing
    sut.next_clicked.assert_not_called()


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
@patch("qui.updater.intro_page.IntroPage.select_rows")
def test_setup_update_if_available(
    select, populate_vm_list, _mock_loger, _mock_log_handler, test_qapp
):
    sut = _make_updater(test_qapp, parse_args(("--update-if-available",), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    select.assert_called_once()
    assert sut.intro_page.head_checkbox.state == sut.intro_page.head_checkbox.SAFE


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
@patch("qui.updater.intro_page.IntroPage.select_rows")
def test_setup_force_update(
    select, populate_vm_list, _mock_loger, _mock_log_handler, test_qapp
):
    sut = _make_updater(test_qapp, parse_args(("--force-update",), test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    select.assert_called_once()
    assert sut.intro_page.head_checkbox.state == sut.intro_page.head_checkbox.ALL


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
@pytest.mark.parametrize(
    "args, sys, non_sys",
    (
        pytest.param(("--apply-to-all",), True, True, id="all"),
        pytest.param(("--apply-to-sys",), True, None, id="sys"),
        pytest.param(("--no-apply",), False, False, id="none"),
    ),
)
def test_setup_apply(
    populate_vm_list,
    _mock_loger,
    _mock_log_handler,
    test_qapp,
    args,
    sys,
    non_sys,
):
    sut = _make_updater(test_qapp, parse_args(args, test_qapp))
    sut.perform_setup()
    calls = [call(sut.qapp, sut.settings)]
    populate_vm_list.assert_has_calls(calls)
    assert sut.settings.restart_service_vms == sys
    assert (
        non_sys is not None
        and sut.settings.restart_other_vms == non_sys
        or sut.settings.overrides.apply_to_other is None
    )


@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
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
    ),
)
def test_retcode(
    _populate_vm_list,
    _mock_loger,
    _mock_log_handler,
    update_results,
    ret_code,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
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
    sut.progress_page.init_update.assert_called_once_with(vms_to_update, sut.settings)

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
        restart=True, vm_updated=vms_to_update, settings=sut.settings
    )
    assert sut.retcode == ret_code
    expected_summary = (
        update_results[0],
        update_results[1],
        update_results[2] + update_results[3],
    )
    sut.summary_page.show.assert_called_once_with(*expected_summary)


@patch("qui.updater.updater.show_dialog_with_icon_async")
@patch("qui.updater.summary_page.show_dialog_with_icon_async")
@patch("logging.FileHandler")
@patch("logging.getLogger")
@patch("qui.updater.intro_page.IntroPage.populate_vm_list")
@patch("qubesadmin.events.EventsDispatcher.listen_for_events")
def test_dialog(
    _listen_for_events,
    _populate_vm_list,
    _mock_loger,
    _mock_log_handler,
    summary_dialog_async,
    updater_dialog_async,
    test_qapp,
):
    sut = _make_updater(test_qapp, parse_args((), test_qapp))
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
    sut.progress_page.init_update.assert_called_once_with(vms_to_update, sut.settings)

    # set sut.summary_page.is_populated = False
    sut.summary_page.list_store = None

    def populate(**_kwargs):
        sut.summary_page.list_store = []

    sut.summary_page.populate_restart_list = Mock(side_effect=populate)
    sut.progress_page.get_update_summary = Mock()
    sut.progress_page.get_update_summary.return_value = (1, 0, 0, 0)
    sut.summary_page.show = Mock()
    sut.summary_page.show.return_value = None

    sut.summary_page.restart_selected_vms = AsyncMock()

    sut.summary_page.status = RestartStatus.OK
    sut.next_clicked(None)

    # next_clicked scheduled the restart phase on the loop, we run it now
    run_coroutine(sut.loop.scheduled[-1])

    updater_dialog_async.assert_awaited_once_with(
        None,
        "Success",
        "Qubes OS is up to date.",
        buttons=gtk_utils.RESPONSES_OK,
        icon_name="qubes-check-yes",
    )
    summary_dialog_async.assert_not_awaited()
