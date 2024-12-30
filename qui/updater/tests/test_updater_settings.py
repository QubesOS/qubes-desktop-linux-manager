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
from unittest.mock import Mock

import gi
import pytest

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk

from qui.updater.updater_settings import Settings


def init_features(test_qapp):
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-restart-servicevms",
            None,
        )
    ] = (
        b"0\x00" + str(1).encode()
    )
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "qubes-vm-update-restart-other", None)
    ] = (b"0\x00" + str(1).encode())
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-max-concurrency",
            None,
        )
    ] = (
        b"0\x00" + str(1).encode()
    )


def test_show_and_hide(test_qapp):
    init_features(test_qapp)
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)
    sut.show()
    sut.close_without_saving(None, None)


def test_update_if_stale(test_qapp):
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)
    assert sut.update_if_stale == 7
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-update-if-stale",
            None,
        )
    ] = (
        b"0\x00" + str(32).encode()
    )
    assert sut.update_if_stale == 32
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-update-if-stale",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-update-if-stale"
        + b"\x00"
    )
    assert sut.update_if_stale == 7


def test_restart_service_vms(test_qapp):
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-restart-servicevms",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-restart-servicevms"
        + b"\x00"
    )
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "qubes-vm-update-restart-system", None)
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-restart-system"
        + b"\x00"
    )
    assert sut.restart_service_vms
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-restart-servicevms",
            None,
        )
    ] = (
        b"0\x00" + "".encode()
    )
    assert not sut.restart_service_vms
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-restart-servicevms",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-restart-servicevms"
        + b"\x00"
    )
    assert sut.restart_service_vms


def test_restart_other_vms(test_qapp):
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "qubes-vm-update-restart-other", None)
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-restart-other"
        + b"\x00"
    )
    assert not sut.restart_other_vms
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "qubes-vm-update-restart-other", None)
    ] = (b"0\x00" + "1".encode())
    assert sut.restart_other_vms
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", "qubes-vm-update-restart-other", None)
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-restart-other"
        + b"\x00"
    )
    assert not sut.restart_other_vms


def test_max_concurrency(test_qapp):
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-max-concurrency",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-max-concurrency"
        + b"\x00"
    )
    assert sut.max_concurrency is None
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-max-concurrency",
            None,
        )
    ] = (
        b"0\x00" + "8".encode()
    )
    assert sut.max_concurrency == 8
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            "qubes-vm-update-max-concurrency",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + b"qubes-vm-update-max-concurrency"
        + b"\x00"
    )
    assert sut.max_concurrency is None


class MockCallback:
    def __init__(self):
        self.call_num = 0
        self.value = None

    def __call__(self, value):
        self.call_num += 1
        self.value = value


@pytest.mark.parametrize(
    "feature, default_value, new_value, button_name",
    (
        pytest.param(
            "update-if-stale",
            Settings.DEFAULT_UPDATE_IF_STALE,
            30,
            "days_without_update_button",
        ),
        pytest.param(
            "restart-servicevms",
            Settings.DEFAULT_RESTART_SERVICEVMS,
            False,
            "restart_servicevms_checkbox",
        ),
        pytest.param(
            "restart-other",
            Settings.DEFAULT_RESTART_OTHER_VMS,
            True,
            "restart_other_checkbox",
        ),
    ),
)
def test_save(feature, default_value, new_value, test_qapp, button_name):
    mock_callback = MockCallback()
    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, mock_callback)

    init_features(test_qapp)

    # set the backwards-compatible feature appropriately
    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Get",
            f"qubes-vm-update-restart-system",
            None,
        )
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + f"qubes-vm-update-restart-system".encode()
        + b"\x00"
    )

    sut.show()
    sut.save_and_close(None)

    assert mock_callback.call_num == 1
    if feature == "update-if-stale":
        assert mock_callback.value == default_value

    # set feature
    sut.show()
    button = getattr(sut, button_name)
    if button_name.endswith("checkbox"):
        button.set_active(new_value)
        new_value_str = "1" if new_value else ""
    else:
        button.set_value(new_value)
        new_value_str = str(new_value)

    test_qapp.expected_calls[
        (
            "dom0",
            "admin.vm.feature.Set",
            f"qubes-vm-update-{feature}",
            new_value_str.encode(),
        )
    ] = b"0\x00"
    sut.save_and_close(None)
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", f"qubes-vm-update-{feature}", None)
    ] = (b"0\x00" + str(new_value).encode())

    assert mock_callback.call_num == 2
    if feature == "update-if-stale":
        assert mock_callback.value == default_value

    # set different value for feature
    sut.show()
    if button_name.endswith("checkbox"):
        button.set_active(default_value)
    else:
        button.set_value(default_value)
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Set", f"qubes-vm-update-{feature}", None)
    ] = b"0\x00"
    sut.save_and_close(None)
    assert mock_callback.call_num == 3
    if feature == "update-if-stale":
        assert mock_callback.value == new_value
    test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Get", f"qubes-vm-update-{feature}", None)
    ] = (
        b"2\x00QubesFeatureNotFoundError\x00\x00"
        + f"qubes-vm-update-{feature}".encode()
        + b"\x00"
    )

    # do not set adminVM feature if nothing change
    sut.show()
    del test_qapp.expected_calls[
        ("dom0", "admin.vm.feature.Set", f"qubes-vm-update-{feature}", None)
    ]
    if button_name.endswith("checkbox"):
        button.set_active(default_value)
    else:
        button.set_value(default_value)
    sut.save_and_close(None)
    assert mock_callback.call_num == 4
    if feature == "update-if-stale":
        assert mock_callback.value == default_value


def test_limit_concurrency(test_qapp):
    dom0_set_max_concurrency = (
        "dom0",
        "admin.vm.feature.Set",
        "qubes-vm-update-max-concurrency",
    )
    dom0_get_max_concurrency = (
        "dom0",
        "admin.vm.feature.Get",
        "qubes-vm-update-max-concurrency",
        None,
    )

    mock_log = Mock()
    sut = Settings(Gtk.Window(), test_qapp, mock_log, lambda *args: None)

    #  False

    init_features(test_qapp)

    # Set True
    sut.show()
    sut.limit_concurrency_checkbox.set_active(True)
    test_qapp.expected_calls[
        (*dom0_set_max_concurrency, sut.DEFAULT_CONCURRENCY)
    ] = b"0\x00"
    sut.save_and_close(None)
    test_qapp.expected_calls[dom0_get_max_concurrency] = (
        b"0\x00" + str(sut.DEFAULT_CONCURRENCY).encode()
    )

    # Set concurrency to max value
    sut.show()
    sut.max_concurrency_button.set_value(sut.MAX_CONCURRENCY)
    test_qapp.expected_calls[
        (*dom0_set_max_concurrency, str(sut.MAX_CONCURRENCY).encode())
    ] = b"0\x00"
    sut.save_and_close(None)
    test_qapp.expected_calls[dom0_get_max_concurrency] = (
        b"0\x00" + str(sut.MAX_CONCURRENCY).encode()
    )

    # Set concurrency to max value again
    sut.show()
    sut.limit_concurrency_checkbox.set_active(True)
    del test_qapp.expected_calls[
        (*dom0_set_max_concurrency, sut.DEFAULT_CONCURRENCY)
    ]
    sut.save_and_close(None)

    # Set False
    sut.show()
    sut.limit_concurrency_checkbox.set_active(False)
    test_qapp.expected_calls[(*dom0_set_max_concurrency, None)] = b"0\x00"
    sut.save_and_close(None)
