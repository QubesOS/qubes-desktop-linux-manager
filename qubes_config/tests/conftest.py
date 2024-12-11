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
import pytest
import importlib.resources
import subprocess
from typing import Mapping, Union, Tuple, List
from qubesadmin.tests import QubesTest

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk

from ..global_config.global_config import GlobalConfig
from ..global_config.policy_manager import PolicyManager
from ..new_qube.new_qube_app import CreateNewQube

default_vm_properties = {
    "autostart": ("bool", True, "False"),
    "backup_timestamp": ("int", True, ""),
    "debug": ("bool", True, "False"),
    "default_user": ("str", True, "user"),
    "dns": ("str", True, "10.139.1.1 10.139.1.2"),
    "gateway": ("str", True, ""),
    "gateway6": ("str", True, ""),
    "icon": ("str", True, "appvm-green"),
    "include_in_backups": ("bool", True, "True"),
    "installed_by_rpm": ("bool", True, "False"),
    "ip": ("str", True, "10.137.0.2"),
    "ip6": ("str", True, ""),
    "kernel": ("str", True, "5.15.52-1.fc32"),
    "keyboard_layout": ("str", True, "us++"),
    "klass": ("str", True, "AppVM"),
    "label": ("label", False, "green"),
    "mac": ("str", True, "00:16:3e:5e:6c:00"),
    "maxmem": ("int", True, "4000"),
    "memory": ("int", True, "400"),
    "name": ("str", False, "testvm"),
    "provides_network": ("bool", True, "False"),
    "qid": ("int", False, "2"),
    "qrexec_timeout": ("int", True, "60"),
    "shutdown_timeout": ("int", True, "60"),
    "start_time": ("str", True, ""),
    "stubdom_mem": ("int", True, ""),
    "stubdom_xid": ("str", True, "-1"),
    "template_for_dispvms": ("bool", True, "False"),
    "updateable": ("bool", True, "False"),
    "uuid": ("str", False, "8fd73e95-a74b-4bf0-a87d-9978dbd1d8a4"),
    "vcpus": ("int", True, "2"),
    "virt_mode": ("str", True, "pvh"),
    "visible_gateway": ("str", True, "10.137.0.1"),
    "visible_gateway6": ("str", True, ""),
    "visible_ip": ("str", True, "10.137.0.2"),
    "visible_ip6": ("str", True, ""),
    "visible_netmask": ("str", True, "255.255.255.255"),
    "xid": ("str", True, "2"),
    "audiovm": ("vm", True, "dom0"),
    "default_dispvm": ("vm", False, "default-dvm"),
    "guivm": ("vm", True, "dom0"),
    "kernelopts": ("str", True, ""),
    "management_dispvm": ("vm", True, "default-mgmt-dvm"),
    "netvm": ("vm", False, "sys-firewall"),
    "template": ("vm", False, "fedora-36"),
}

possible_tags = ['whonix-updatevm', 'anon-gateway']


def add_expected_vm(qapp,
                    name: str,
                    klass: str,
                    properties: Mapping[str,
                                        Union[bool, str, int,
                                              Tuple[str, bool, str]]],
                    features,
                    tags):
    """Generate expected_calls entries to get info about a VM
    :param qapp: QubesTest object
    :param name: name of the VM
    :param klass: class of the VM (AppVM, TemplateVM etc)
    :param properties: dict of properties; values can be either a value
        directly, or tuple of (type, is_default, value)
    :param features: dict of expected features - use 'None' as value for
        feature that will be checked but is not present
    :param tags: list of tags
    :return:
    """
    vm_list_call = ('dom0', 'admin.vm.List', None, None)
    vm_list = b'0\x00'
    if vm_list_call in qapp.expected_calls:
        vm_list = qapp.expected_calls[vm_list_call]
    vm_list += f'{name} class={klass} state=Halted\n'.encode()
    qapp.expected_calls[vm_list_call] = vm_list
    properties_getall = b"0\x00"
    combined_properties = default_vm_properties.copy()
    for prop, value in properties.items():
        if isinstance(value, tuple):
            combined_properties[prop] = value
        elif value is None:
            try:
                del combined_properties[prop]
            except KeyError:
                pass
        elif prop in combined_properties:
            combined_properties[prop] = \
                (combined_properties[prop][0],
                 combined_properties[prop][1], str(value))
        else:
            raise KeyError(f"Unknown property '{prop}'")

    for prop, value in combined_properties.items():
        if prop == 'template' and klass in ("TemplateVM", "StandaloneVM"):
            qapp.expected_calls[(name, "admin.vm.property.Get", prop, None)] = \
                b'2\x00QubesNoSuchPropertyError\x00\x00No such property\x00'
            continue
        prop_line = f"default={value[1]} type={value[0]} {value[2]}"
        properties_getall += (f"{prop} " + prop_line + "\n").encode()
        qapp.expected_calls[(name, "admin.vm.property.Get", prop, None)] = \
            b"0\x00" + prop_line.encode()

    qapp.expected_calls[(name, "admin.vm.feature.List", None, None)] = \
        ("0\x00" + "".join(f"{feature}\n" for feature, value in
                           features.items() if value is not None)).encode()
    for feature, value in features.items():
        if value is None:
            qapp.expected_calls[
                (name, "admin.vm.feature.Get", feature, None)] = \
                b'2\x00QubesFeatureNotFoundError\x00\x00' + \
                str(feature).encode() + b'\x00'
        else:
            qapp.expected_calls[
                (name, "admin.vm.feature.Get", feature, None)] = \
                b"0\x00" + str(value).encode()

    qapp.expected_calls[(name, "admin.vm.tag.List", None, None)] = \
        ("0\x00" + "".join(f"{tag}\n" for tag in tags)).encode()

    for tag in possible_tags:
        qapp.expected_calls[(name, "admin.vm.tag.Get", tag, None)] = \
            b"0\x000"

    for tag in tags:
        qapp.expected_calls[(name, "admin.vm.tag.Get", tag, None)] = \
            b"0\x001"

    qapp.expected_calls[(name, "admin.vm.device.pci.List", None, None)] = \
        b"0\x00"

def add_dom0_vm_property(qapp, prop_name, prop_value):
    """Add a vm property to dom0"""
    if not prop_value:
        prop_value = ""
    qapp.expected_calls[('dom0', 'admin.property.Get', prop_name, None)] = \
        b'0\x00' + f'default=True type=vm {prop_value}'.encode()

def add_dom0_text_property(qapp, prop_name, prop_value):
    """Add a str property to dom0"""
    qapp.expected_calls[('dom0', 'admin.property.Get', prop_name, None)] = \
        b'0\x00' + f'default=True type=str {prop_value}'.encode()


def add_dom0_feature(qapp, feature, feature_value):
    """Add dom0 feature"""
    if feature_value is not None:
        qapp.expected_calls[('dom0', 'admin.vm.feature.Get', feature, None)] = \
            b'0\x00' + f'{feature_value}'.encode()
    else:
        qapp.expected_calls[('dom0', 'admin.vm.feature.Get', feature, None)] = \
            b'2\x00QubesFeatureNotFoundError\x00\x00' \
            + str(feature).encode() + b'\x00'

def add_feature_with_template_to_all(qapp, feature_name,
                                     enable_vm_names: List[str]):
    """Add possibility of checking for a feature with templated to all qubes;
    those listed in enabled_vm_names will have it set to 1, others will
    have it absent."""
    for vm in qapp.domains:
        if vm.name in enable_vm_names:
            result=b'0\x001'
        else:
            result = b'2\x00QubesFeatureNotFoundError\x00\x00' + \
                     str(feature_name).encode() + b'\x00'
        qapp.expected_calls[(vm, 'admin.vm.feature.CheckWithTemplate',
                             feature_name, None)] = result

def add_feature_to_all(qapp, feature_name, enable_vm_names: List[str]):
    """Add possibility of checking for a feature to all qubes; those listed
    in enabled_vm_names will have it set to 1, others will have it absent."""
    for vm in qapp.domains:
        if vm.name in enable_vm_names:
            result=b'0\x001'
        else:
            result = b'2\x00QubesFeatureNotFoundError\x00\x00' + \
                     str(feature_name).encode() + b'\x00'
        qapp.expected_calls[(vm, 'admin.vm.feature.Get',
                             feature_name, None)] = result


@pytest.fixture
def test_qapp():
    return test_qapp_impl()


def test_qapp_impl():
    """Test QubesApp"""
    qapp = QubesTest()
    qapp._local_name = 'dom0'  # pylint: disable=protected-access

    add_dom0_vm_property(qapp, 'clockvm', 'sys-net')
    add_dom0_vm_property(qapp, 'updatevm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_netvm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_template', 'fedora-36')
    add_dom0_vm_property(qapp, 'default_dispvm', 'fedora-36')

    add_dom0_text_property(qapp, 'default_kernel', '1.1')
    add_dom0_text_property(qapp, 'default_pool', 'file')

    add_dom0_feature(qapp, 'gui-default-allow-fullscreen', '')
    add_dom0_feature(qapp, 'gui-default-allow-utf8-titles', '')
    add_dom0_feature(qapp, 'gui-default-trayicon-mode', '')

    # setup labels
    qapp.expected_calls[('dom0', 'admin.label.List', None, None)] = \
        b'0\x00red\nblue\ngreen\n'

    # setup pools:
    qapp.expected_calls[('dom0', 'admin.pool.List', None, None)] = \
        b'0\x00linux-kernel\nlvm\nfile\n'
    qapp.expected_calls[('dom0', 'admin.pool.volume.List',
                         'linux-kernel', None)] = \
        b'0\x001.1\nmisc\n4.2\n'

    add_expected_vm(qapp, 'dom0', 'AdminVM',
                    {}, {'service.qubes-update-check': 1,
                         'config.default.qubes-update-check': None,
                         'config-usbvm-name': None,
                         'gui-default-secure-copy-sequence': None,
                         'gui-default-secure-paste-sequence': None,
                         'virtual-browser-action': None
                         }, [])
    add_expected_vm(qapp, 'sys-net', 'AppVM',
                    {'provides_network': ('bool', False, 'True')},
                    {'service.qubes-update-check': None,
                     'service.qubes-updates-proxy': 1}, [])

    add_expected_vm(qapp, 'sys-firewall', 'AppVM',
                    {'provides_network': ('bool', False, 'True')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'sys-usb', 'AppVM',
                    {},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'fedora-36', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'fedora-35', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'default-dvm', 'DispVM',
                    {'template_for_dispvms': ('bool', False, 'True')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-vm', 'AppVM',
                    {}, {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-blue', 'AppVM',
                    {'label': ('str', False, 'blue')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-red', 'AppVM',
                    {'label': ('str', False, 'red')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-standalone', 'StandaloneVM',
                    {'label': ('str', False, 'green')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'vault', 'AppVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    add_feature_with_template_to_all(qapp, 'supported-service.qubes-u2f-proxy',
                                     ['test-vm', 'fedora-35', 'sys-usb'])
    add_feature_with_template_to_all(qapp, 'service.updates-proxy-setup',
                                     ['fedora-36', 'fedora-35'])
    add_feature_to_all(qapp, 'service.qubes-u2f-proxy',
                                     ['test-vm'])

    for vm in qapp.domains:
        qapp.expected_calls[
            (vm.name, 'admin.vm.device.pci.Attached', None, None)] = b'0\x00'

    return qapp


@pytest.fixture
def test_qapp_whonix(test_qapp):  # pylint: disable=redefined-outer-name
    # pylint does not understand fixtures
    """Testing qapp with whonix vms added"""
    add_expected_vm(test_qapp, 'sys-whonix', 'AppVM',
                    {},
                    {'service.qubes-update-check': None,
                     'service.qubes-updates-proxy': 1}, ['anon-gateway'])
    add_expected_vm(test_qapp, 'anon-whonix', 'AppVM',
                    {},
                    {'service.qubes-update-check': None}, ['anon-gateway'])
    add_expected_vm(test_qapp, 'whonix-gw-15', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, ['whonix-updatevm'])
    add_expected_vm(test_qapp, 'whonix-gw-14', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, ['whonix-updatevm'])
    test_qapp.domains.clear_cache()
    add_feature_with_template_to_all(
        test_qapp, 'service.updates-proxy-setup',
        ['fedora-36', 'fedora-35', 'whonix-gw-15', 'whonix-gw-14'])
    return test_qapp

@pytest.fixture
def test_qapp_simple(): # pylint: disable=redefined-outer-name
    """A qapp with only one template, one sys-net and that's all"""
    # pylint does not understand fixtures
    qapp = QubesTest()
    qapp._local_name = 'dom0'  # pylint: disable=protected-access

    add_dom0_vm_property(qapp, 'clockvm', 'sys-net')
    add_dom0_vm_property(qapp, 'updatevm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_netvm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_template', 'fedora-36')
    add_dom0_vm_property(qapp, 'default_dispvm', 'fedora-36')

    add_dom0_text_property(qapp, 'default_kernel', '1.1')
    add_dom0_text_property(qapp, 'default_pool', 'file')

    add_dom0_feature(qapp, 'gui-default-allow-fullscreen', '')
    add_dom0_feature(qapp, 'gui-default-allow-utf8-titles', '')
    add_dom0_feature(qapp, 'gui-default-trayicon-mode', '')

    # setup labels
    qapp.expected_calls[('dom0', 'admin.label.List', None, None)] = \
        b'0\x00red\nblue\ngreen\n'

    # setup pools:
    qapp.expected_calls[('dom0', 'admin.pool.List', None, None)] = \
        b'0\x00linux-kernel\nlvm\nfile\n'
    qapp.expected_calls[('dom0', 'admin.pool.volume.List',
                         'linux-kernel', None)] = \
        b'0\x001.1\nmisc\n4.2\n'

    add_expected_vm(qapp, 'dom0', 'AdminVM',
                    {}, {'service.qubes-update-check': 1,
                         'config.default.qubes-update-check': None,
                         'config-usbvm-name': None,
                         'gui-default-secure-copy-sequence': None,
                         'gui-default-secure-paste-sequence': None,
                         'virtual-browser-action': None
                         }, [])
    add_expected_vm(qapp, 'sys-net', 'AppVM',
                    {'provides_network': ('bool', False, 'True')},
                    {'service.qubes-update-check': None,
                     'service.qubes-updates-proxy': 1}, [])

    add_expected_vm(qapp, 'fedora-36', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    for vm in qapp.domains:
        qapp.expected_calls[
            (vm.name, 'admin.vm.device.pci.Attached', None, None)] = b'0\x00'

    return qapp


@pytest.fixture
def test_qapp_broken():  # pylint: disable=redefined-outer-name
    """A qapp with no templates, no sys-net"""
    # pylint does not understand fixtures
    qapp = QubesTest()
    qapp._local_name = 'dom0'  # pylint: disable=protected-access

    add_dom0_vm_property(qapp, 'clockvm', None)
    add_dom0_vm_property(qapp, 'updatevm', None)
    add_dom0_vm_property(qapp, 'default_netvm', None)
    add_dom0_vm_property(qapp, 'default_template', None)
    add_dom0_vm_property(qapp, 'default_dispvm', None)

    add_dom0_text_property(qapp, 'default_kernel', '1.1')
    add_dom0_text_property(qapp, 'default_pool', 'file')

    add_dom0_feature(qapp, 'gui-default-allow-fullscreen', '')
    add_dom0_feature(qapp, 'gui-default-allow-utf8-titles', '')
    add_dom0_feature(qapp, 'gui-default-trayicon-mode', '')

    # setup labels
    qapp.expected_calls[('dom0', 'admin.label.List', None, None)] = \
        b'0\x00red\nblue\ngreen\n'

    # setup pools:
    qapp.expected_calls[('dom0', 'admin.pool.List', None, None)] = \
        b'0\x00linux-kernel\nlvm\nfile\n'
    qapp.expected_calls[('dom0', 'admin.pool.volume.List',
                         'linux-kernel', None)] = \
        b'0\x001.1\nmisc\n4.2\n'

    add_expected_vm(qapp, 'dom0', 'AdminVM',
                    {}, {'service.qubes-update-check': 1,
                         'config.default.qubes-update-check': None,
                         'config-usbvm-name': None,
                         'gui-default-secure-copy-sequence': None,
                         'gui-default-secure-paste-sequence': None,
                         'virtual-browser-action': None
                         }, [])

    #
    for vm in qapp.domains:
        qapp.expected_calls[
            (vm.name, 'admin.vm.device.pci.Attached', None, None)] = b'0\x00'

    return qapp


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
    glade_ref = (importlib.resources.files('qubes_config') /
                 'tests/test.glade')
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
    glade_ref = (importlib.resources.files('qubes_config') /
                 'global_config.glade')
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
    glade_ref = (importlib.resources.files('qubes_config') /
                 'new_qube.glade')
    with importlib.resources.as_file(glade_ref) as path:
        builder.add_from_file(str(path))
    return builder


class TestPolicyClient:
    """Testing policy client that does not interact with Policy API"""
    def __init__(self):
        self.file_tokens = {
            'a-test': 'a',
            'b-test': 'b'
        }
        self.files = {
            'a-test': """Test * @anyvm @anyvm deny""",
            'b-test': """Test * test-vm @anyvm allow\n
Test * test-red test-blue deny"""
        }
        self.service_to_files = {
            'Test': ['a-test', 'b-test']
        }
        self.include_file_tokens = {
            'include-1': 'c',
            'include-2': 'd'
        }

        self.include_files = {
            'include-1': """!include include/include-2""",
            'include-2': """Test.Test +argument @anyvm @anyvm allow"""
        }

    def policy_get_files(self, service_name):
        """Get files connected to a given service; does not
        take into account policy_replace"""
        return self.service_to_files.get(service_name, '')

    def policy_get(self, file_name):
        """Get file contents; takes into account policy_replace."""
        if file_name in self.files:
            return self.files[file_name], self.file_tokens[file_name]
        raise subprocess.CalledProcessError(2, 'test')

    def policy_include_get(self, file_name):
        """Get file contents; takes into account policy_replace."""
        if file_name in self.include_files:
            return self.include_files[file_name], \
                   self.include_file_tokens[file_name]
        raise subprocess.CalledProcessError(2, 'test')

    def policy_replace(self, filename, policy_text, token='any'):
        """Replace file contents with provided contents."""
        if token == 'new':
            if filename in self.file_tokens:
                raise subprocess.CalledProcessError(2, 'test')
        elif token != 'any':
            if token != self.file_tokens.get(filename, ''):
                raise subprocess.CalledProcessError(2, 'test')
        self.files[filename] = policy_text
        self.file_tokens[filename] = str(len(policy_text))

    def policy_include_replace(self, filename, policy_text, token='any'):
        """Replace file contents with provided contents."""
        if token != 'any':
            if token != self.include_file_tokens.get(filename, ''):
                raise subprocess.CalledProcessError(2, 'test')
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
