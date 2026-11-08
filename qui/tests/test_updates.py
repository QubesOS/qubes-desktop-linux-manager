"""Tests for launching applications from the updates widget."""

# pylint: disable=protected-access

from unittest import mock

from qui.tray import updates


def test_spawn_detached():
    with mock.patch.object(updates.subprocess, "Popen") as popen:
        assert updates._spawn_detached(["app"]) is popen.return_value
    popen.assert_called_once_with(
        ["systemd-run", "--user", "--scope", "--quiet", "--", "app"]
    )


def test_launch_in_scope():
    with mock.patch.object(updates, "_spawn_detached") as spawn:
        updates.UpdatesTray.launch_updater()
        updates.UpdatesTray.launch_template_manager()
    assert spawn.call_args_list == [
        mock.call(["qubes-update-gui"]),
        mock.call(["qvm-template-gui"]),
    ]
