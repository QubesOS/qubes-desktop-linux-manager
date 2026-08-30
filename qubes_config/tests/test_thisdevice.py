# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2026 Marta Marczykowska-Górecka
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
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ..global_config import thisdevice_handler
from ..global_config.thisdevice_handler import ThisDeviceHandler

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

HCL_REPORT = """---
layout:
  'hcl'
type:
  'notebook'
hvm:
  'yes'
iommu:
  'yes'
slat:
  'yes'
tpm:
  '1.2'
remap:
  'yes'
brand: |
  TestBrand
model: |
  TestModel
bios: |
  1.0
cpu: |
  TestCPU
chipset: |
  TestChipset
gpu: |
  TestGPU
memory: |
  16384
certified:
  'no'
versions:
  - works:
      'FIXME:yes|no|partial'
    qubes: |
      R4.3
    xen: |
      4.17.2
    kernel: |
      6.6.21
"""


class SynchronousThread:
    """Fake threading.Thread that runs the target immediately on start()."""

    def __init__(self, target=None, daemon=None):  # pylint: disable=unused-argument
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def sync_thisdevice(monkeypatch):
    """Make ThisDeviceHandler load its data synchronously, so that tests do
    not need to wait for a worker thread and a main loop iteration."""
    monkeypatch.setattr(
        thisdevice_handler, "threading", SimpleNamespace(Thread=SynchronousThread)
    )
    monkeypatch.setattr(
        thisdevice_handler,
        "GLib",
        SimpleNamespace(idle_add=lambda func, *args: func(*args)),
    )


def test_thisdevice_data_loaded(
    sync_thisdevice, test_qapp, test_policy_manager, real_builder
):
    with patch("subprocess.check_output") as mock_subprocess:
        mock_subprocess.return_value = HCL_REPORT.encode()
        handler = ThisDeviceHandler(test_qapp, real_builder, test_policy_manager)
        mock_subprocess.assert_called_once_with(["qubes-hcl-report", "-y"])

    assert "TestBrand" in handler.data_label.get_text()
    assert "TestModel" in handler.data_label.get_text()
    assert not handler.is_certified()


def test_thisdevice_report_failure(
    sync_thisdevice, test_qapp, test_policy_manager, real_builder
):
    with patch("subprocess.check_output") as mock_subprocess:
        mock_subprocess.return_value = b""
        handler = ThisDeviceHandler(test_qapp, real_builder, test_policy_manager)

    assert "Failed to load system data" in handler.data_label.get_text()


def test_thisdevice_report_error(
    sync_thisdevice, test_qapp, test_policy_manager, real_builder
):
    with patch("subprocess.check_output") as mock_subprocess:
        mock_subprocess.side_effect = OSError("no such file")
        handler = ThisDeviceHandler(test_qapp, real_builder, test_policy_manager)

    assert "Failed to load system data" in handler.data_label.get_text()


def test_thisdevice_placeholder_before_report(
    test_qapp, test_policy_manager, real_builder
):
    """The page must be usable while the report is still being collected."""
    started = []

    class PendingThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            started.append(self.target)

    with patch.object(
        thisdevice_handler, "threading", SimpleNamespace(Thread=PendingThread)
    ), patch("subprocess.check_output") as mock_subprocess:
        handler = ThisDeviceHandler(test_qapp, real_builder, test_policy_manager)
        # the report is collected in the worker thread, not during __init__
        mock_subprocess.assert_not_called()

    assert started
    assert "Loading hardware information" in handler.data_label.get_text()
