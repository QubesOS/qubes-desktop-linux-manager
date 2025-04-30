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
"""Conftest helper pytest file: fixtures container here are
 reachable by all tests"""
# pylint: disable=protected-access
# pylint: disable=redefined-outer-name

import pytest
import importlib.resources
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk

from ..global_config.global_config import GlobalConfig
from ..global_config.policy_manager import PolicyManager
from ..new_qube.new_qube_app import CreateNewQube

from qubesadmin.tests.mock_app import (
    MockQubesComplete,
    MockQube,
    MockQubes,
    MockQubesWhonix,
    QubesTestWrapper,
    GLOBAL_PROPERTIES,
    MockDevice,
)

@pytest.fixture
def test_qapp():
    test_qapp = MockQubesComplete()
    test_qapp._qubes["dom0"].features["gui-default-secure-copy-sequence"] = None
    test_qapp._qubes["sys-usb"].features[
        "supported-feature.keyboard-layout"
    ] = "1"
    test_qapp.update_vm_calls()
    return test_qapp


@pytest.fixture
def test_qapp_simple():
    test_qapp_simple = MockQubes()
    return test_qapp_simple


@pytest.fixture
def test_qapp_whonix():
    test_qapp_whonix = MockQubesWhonix()
    return test_qapp_whonix


@pytest.fixture
def test_qapp_broken():  # pylint: disable=redefined-outer-name
    """A qapp with no templates, no sys-net"""
    # pylint does not understand fixtures
    qapp = QubesTestWrapper()

    qapp._global_properties = GLOBAL_PROPERTIES.copy()

    qapp.set_global_property("clockvm", "")
    qapp.set_global_property("default_dispvm", "")
    qapp.set_global_property("default_netvm", "")
    qapp.set_global_property("default_template", "")
    qapp.set_global_property("updatevm", "")

    qapp.update_global_properties()
    qapp.update_vm_calls()

    return qapp


@pytest.fixture
def test_qapp_devices():
    test_qapp_devices = MockQubesComplete()

    test_qapp_devices._qubes["test-dev"] = MockQube(
        name="test-dev",
        qapp=test_qapp_devices,
        label="purple",
        devices_denied="m******",
    )
    test_qapp_devices._qubes["test-dev2"] = MockQube(
        name="test-dev2",
        qapp=test_qapp_devices,
        label="green",
        devices_denied="p02****u02****p07****p123***",
    )

    test_qapp_devices.update_vm_calls()

    # add some PCI devices
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="pci",
            device_id="0x8086:0x51f0::p028000",
            product="Network Card",
            vendor="unknown",
            backend_vm="dom0",
            assigned=[("sys-net", "required", None)],
            port="0c.0",
        )
    )
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="pci",
            product="USB Controller",
            backend_vm="dom0",
            assigned=[("sys-net", "required", None)],
            device_id="0x8086:0x461e::p0c0330",
            port="0d.0",
            vendor="ACME",
        )
    )
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="pci",
            device_id="0x8086:0x51f0::p300000",
            product="Piano Dropper",
            vendor="ACME",
            backend_vm="dom0",
            port="0f.0",
        )
    )
    # and one assigned with no-strict-reset
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="pci",
            device_id="0x8086:0x51c8::p040300",
            product="Whole Symphonic Orchestra",
            vendor="Berlin Philharmonie",
            backend_vm="dom0",
            assigned=[("test-red", "required", ["no-strict-reset"])],
            port="0h.0",
        )
    )

    # add two pre-assigned devices
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="usb",
            product="Anvil",
            vendor="ACME",
            backend_vm="sys-usb",
            assigned=[
                ("test-vm", "ask-to-attach", None),
                ("test-red", "ask-to-attach", None),
            ],
            device_id="3:4:b011010",
            port="2-22",
        )
    )
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="usb",
            product="Hammer",
            vendor="ACME",
            backend_vm="sys-usb",
            assigned=[("test-vm", "auto-attach", None)],
            device_id="1:2:u011010",
            port="2-23",
        )
    )

    # add an unassigned block device
    test_qapp_devices._devices.append(
        MockDevice(
            test_qapp_devices,
            dev_class="block",
            product="Ouroboros",
            vendor="ACME",
            backend_vm="sys-usb",
            device_id="444:888:b123422",
            port="sda",
        )
    )

    test_qapp_devices.update_vm_calls()

    # an assignment for a currently not-connected device

    call = ("test-vm", "admin.vm.device.usb.Assigned", None, None)
    assignment_string = (
        "sys-usb+2-30 device_id='0:0007:u01101' "
        "port_id='2-30' devclass='usb' "
        "backend_domain='sys-usb' mode='ask-to-attach' "
        "frontend_domain='test-vm'\n"
    ).encode()
    current_response = test_qapp_devices.expected_calls[call]
    test_qapp_devices.expected_calls[call] = (
        current_response + assignment_string
    )

    return test_qapp_devices


@pytest.fixture
def test_builder():
    """Test gtk_builder with loaded test glade file and registered signals."""
    try:
        GlobalConfig.register_signals()
    except RuntimeError:
        # signals already registered
        pass
    # test glade file contains very simple setup with correctly named widgets
    builder = Gtk.Builder()
    glade_ref = importlib.resources.files("qubes_config") / "tests/test.glade"
    with importlib.resources.as_file(glade_ref) as path:
        builder.add_from_file(str(path))
    return builder


@pytest.fixture
def real_builder():
    """Gtk builder with actual config glade file registered"""
    try:
        GlobalConfig.register_signals()
    except RuntimeError:
        # signals already registered
        pass
    # test glade file contains very simple setup with correctly named widgets
    builder = Gtk.Builder()
    glade_ref = (
        importlib.resources.files("qubes_config") / "global_config.glade"
    )
    with importlib.resources.as_file(glade_ref) as path:
        builder.add_from_file(str(path))
    return builder


@pytest.fixture
def new_qube_builder():
    """Gtk builder with actual config glade file registered"""
    try:
        CreateNewQube.register_signals()
    except RuntimeError:
        # signals already registered
        pass
    # test glade file contains very simple setup with correctly named widgets
    builder = Gtk.Builder()
    glade_ref = importlib.resources.files("qubes_config") / "new_qube.glade"
    with importlib.resources.as_file(glade_ref) as path:
        builder.add_from_file(str(path))
    return builder


class TestPolicyClient:
    """Testing policy client that does not interact with Policy API"""

    def __init__(self):
        self.file_tokens = {"a-test": "a", "b-test": "b"}
        self.files = {
            "a-test": """Test * @anyvm @anyvm deny""",
            "b-test": """Test * test-vm @anyvm allow\n
Test * test-red test-blue deny""",
        }
        self.service_to_files = {"Test": ["a-test", "b-test"]}
        self.include_file_tokens = {"include-1": "c", "include-2": "d"}

        self.include_files = {
            "include-1": """!include include/include-2""",
            "include-2": """Test.Test +argument @anyvm @anyvm allow""",
        }

    def policy_get_files(self, service_name):
        """Get files connected to a given service; does not
        take into account policy_replace"""
        return self.service_to_files.get(service_name, "")

    def policy_get(self, file_name):
        """Get file contents; takes into account policy_replace."""
        if file_name in self.files:
            return self.files[file_name], self.file_tokens[file_name]
        raise subprocess.CalledProcessError(2, "test")

    def policy_include_get(self, file_name):
        """Get file contents; takes into account policy_replace."""
        if file_name in self.include_files:
            return (
                self.include_files[file_name],
                self.include_file_tokens[file_name],
            )
        raise subprocess.CalledProcessError(2, "test")

    def policy_replace(self, filename, policy_text, token="any"):
        """Replace file contents with provided contents."""
        if token == "new":
            if filename in self.file_tokens:
                raise subprocess.CalledProcessError(2, "test")
        elif token != "any":
            if token != self.file_tokens.get(filename, ""):
                raise subprocess.CalledProcessError(2, "test")
        self.files[filename] = policy_text
        self.file_tokens[filename] = str(len(policy_text))

    def policy_include_replace(self, filename, policy_text, token="any"):
        """Replace file contents with provided contents."""
        if token != "any":
            if token != self.include_file_tokens.get(filename, ""):
                raise subprocess.CalledProcessError(2, "test")
        self.include_files[filename] = policy_text
        self.include_file_tokens[filename] = str(len(policy_text))

    def policy_list(self):
        return list(self.files.keys())

    def policy_include_list(self):
        return list(self.include_files.keys())


@pytest.fixture
def test_policy_client():
    """Policy client fixture"""
    return TestPolicyClient()


@pytest.fixture
def test_policy_manager():
    """Policy manager with patched out object requiring actual working
    Admin API methods"""
    manager = PolicyManager()
    manager.policy_client = TestPolicyClient()
    return manager
