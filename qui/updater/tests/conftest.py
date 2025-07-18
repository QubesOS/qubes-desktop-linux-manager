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

import gi

from qubesadmin.tests.mock_app import MockQube, MockQubesComplete
from qui.updater.intro_page import UpdateRowWrapper
from qui.updater.summary_page import RestartRowWrapper
from qui.updater.utils import ListWrapper

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


@pytest.fixture
def test_qapp():
    qapp = MockQubesComplete()
    qapp._qubes["fedora-35"].updateable = True
    qapp._qubes["fedora-36"] = MockQube(
        name="fedora-36",
        qapp=qapp,
        klass="TemplateVM",
        netvm="",
        updateable=True,
        installed_by_rpm=True,
        features={
            "supported-service.qubes-u2f-proxy": "1",
            "service.qubes-update-check": "1",
            "service.updates-proxy-setup": "1",
        },
    )

    qapp._qubes["fedora-35"].features["updates-available"] = ""

    qapp._qubes["test-standalone"].updateable = True

    qapp.update_vm_calls()
    return qapp


def test_qapp_impl():
    return MockQubesComplete()


@pytest.fixture
def real_builder():
    """Gtk builder with actual config glade file registered"""
    builder = Gtk.Builder()
    builder.set_translation_domain("desktop-linux-manager")
    glade_ref = importlib.resources.files("qui") / "updater.glade"
    with importlib.resources.as_file(glade_ref) as path:
        builder.add_from_file(str(path))
    return builder


class MockWidget:
    def __init__(self):
        self.sensitive = None
        self.label = None
        self.visible = True
        self.text = None
        self.halign = None
        self.model = None
        self.buffer = None

    def set_sensitive(self, value: bool):
        self.sensitive = value

    def set_label(self, text):
        self.label = text

    def show(self):
        self.visible = True

    def set_visible(self, visible):
        self.visible = visible

    def set_text(self, text):
        self.text = text

    def set_halign(self, halign):
        self.halign = halign

    def set_model(self, model):
        self.model = model

    def get_buffer(self):
        return self.buffer


@pytest.fixture
def mock_next_button():
    return MockWidget()


@pytest.fixture
def mock_cancel_button():
    return MockWidget()


@pytest.fixture
def mock_label():
    return MockWidget()


@pytest.fixture
def mock_tree_view():
    return MockWidget()


@pytest.fixture
def mock_text_view():
    result = MockWidget()
    result.buffer = MockWidget()
    return result


@pytest.fixture
def mock_list_store():
    class MockListStore:
        def __init__(self):
            self.raw_rows = []

        def get_model(self):
            return self

        def get_iter(self, path):
            return path[0]

        def __getitem__(self, item):
            return self.raw_rows[item]

        def append(self, row):
            self.raw_rows.append(row)

        def remove(self, idx):
            self.raw_rows.remove(idx)

        def set_sort_func(self, _col, _sort_func, _data):
            """not used in tests"""
            pass

    return MockListStore()


@pytest.fixture
def mock_settings():
    class MockSettings:
        def __init__(self):
            self.update_if_stale = 7
            self.restart_service_vms = True
            self.restart_other_vms = True
            self.max_concurrency = None
            self.hide_skipped = True
            self.hide_updated = False

    return MockSettings()


@pytest.fixture
def all_vms_list(test_qapp, mock_list_store):
    result = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        result.append_vm(vm)
    return result


@pytest.fixture
def updatable_vms_list(test_qapp, mock_list_store):
    result = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass in ("AdminVM", "TemplateVM", "StandaloneVM"):
            result.append_vm(vm)
    return result


@pytest.fixture
def appvms_list(test_qapp, mock_list_store):
    result = ListWrapper(RestartRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        if vm.klass == "AppVM":
            result.append_vm(vm)
    return result


@pytest.fixture
def mock_thread():
    class MockThread:
        def __init__(self):
            self.started = False
            self.alive_requests_max: int = 3
            self.alive_request = 0

        def start(self):
            self.started = True

        def is_alive(self):
            self.alive_request += 1
            if self.alive_request > self.alive_requests_max:
                return False
            return True

    return MockThread()
