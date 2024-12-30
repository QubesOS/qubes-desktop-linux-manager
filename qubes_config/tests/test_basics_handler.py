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
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=protected-access

import os
from unittest.mock import Mock, patch
from ..global_config.basics_handler import (
    KernelVersion,
    PropertyHandler,
    FeatureHandler,
    QMemManHelper,
    MemoryHandler,
    BasicSettingsHandler,
    KernelHolder,
)

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk


def test_kernel_sorting():
    # check if the sorting does not complain when weirdly-named kernels appear
    kernels = ["1.09", "1.1", "testkernel", "1.1a"]
    assert sorted(kernels, key=KernelVersion) == [
        "1.1",
        "1.1a",
        "1.09",
        "testkernel",
    ]


def test_property_handler(test_qapp):
    test_vm = test_qapp.domains["test-vm"]
    mock_holder = Mock()
    mock_holder.mock_trait = test_vm

    combobox = Gtk.ComboBox.new_with_entry()

    handler = PropertyHandler(
        qapp=test_qapp,
        trait_holder=mock_holder,
        trait_name="mock_trait",
        widget=combobox,
        readable_name="name",
    )

    assert handler.get_current_value() == test_vm
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("test-blue")
    assert handler.is_changed()
    assert handler.get_unsaved() == "name"

    # and reset
    handler.reset()
    assert handler.get_current_value() == test_vm
    assert handler.widget.get_active_id() == "test-vm"
    assert not handler.is_changed()

    # change stuff
    handler.widget.set_active_id("test-blue")
    assert handler.is_changed()
    assert handler.get_unsaved() == "name"

    handler.save()
    assert mock_holder.mock_trait == test_qapp.domains["test-blue"]
    assert handler.get_current_value() == test_qapp.domains["test-blue"]
    assert handler.widget.get_active_id() == "test-blue"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""


# when dealing with features, we need to be always using helper methods
@patch("qubes_config.global_config.basics_handler.get_feature")
@patch("qubes_config.global_config.basics_handler.apply_feature_change")
def test_feature_handler(mock_apply, mock_get, test_qapp):
    trait_options = {"a": 1, "b": None, "c": 2}

    test_vm = test_qapp.domains["test-vm"]

    mock_get.return_value = 1

    combobox = Gtk.ComboBoxText()
    handler = FeatureHandler(
        trait_holder=test_vm,
        trait_name="test_trait",
        widget=combobox,
        options=trait_options,
        readable_name="name",
    )

    # is correct selected?
    assert handler.get_current_value() == 1
    assert handler.widget.get_active_text() == "a"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("b")
    assert handler.widget.get_active_id() == "b"
    assert handler.is_changed()
    assert handler.get_unsaved() == "name"

    # and reset
    handler.reset()
    assert handler.get_current_value() == 1
    assert handler.widget.get_active_text() == "a"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("b")
    handler.save()
    mock_apply.assert_called_with(test_vm, "test_trait", None)
    assert handler.widget.get_active_id() == "b"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("c")
    handler.save()
    mock_apply.assert_called_with(test_vm, "test_trait", 2)
    assert handler.widget.get_active_id() == "c"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""


# when dealing with features, we need to be always using helper methods
@patch("qubes_config.global_config.basics_handler.get_boolean_feature")
@patch("qubes_config.global_config.basics_handler.apply_feature_change")
def test_bool_feature_handler(mock_apply, mock_get_bool, test_qapp):
    trait_options = {"a": False, "b": None, "c": True}

    test_vm = test_qapp.domains["test-vm"]

    mock_get_bool.return_value = True

    combobox = Gtk.ComboBoxText()
    handler = FeatureHandler(
        trait_holder=test_vm,
        trait_name="test_trait",
        widget=combobox,
        options=trait_options,
        readable_name="name",
        is_bool=True,
    )

    # is correct selected?
    assert handler.get_current_value()
    assert handler.widget.get_active_text() == "c"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("b")
    assert handler.widget.get_active_id() == "b"
    assert handler.is_changed()
    assert handler.get_unsaved() == "name"

    # and reset
    handler.reset()
    assert handler.widget.get_active_text() == "c"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("b")
    handler.save()
    mock_apply.assert_called_with(test_vm, "test_trait", None)
    assert handler.widget.get_active_id() == "b"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.widget.set_active_id("a")
    handler.save()
    mock_apply.assert_called_with(test_vm, "test_trait", False)
    assert handler.widget.get_active_id() == "a"
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""


def test_qmemmanhelper(tmp_path):
    f = tmp_path / "test.ini"
    defaults = {"vm-min-mem": 200, "dom0-mem-boost": 350}

    helper = QMemManHelper()
    helper.QMEMMAN_CONFIG_PATH = str(f)

    # get defaults if file is empty
    assert helper.get_values() == defaults
    assert not f.exists()

    # write some file contents
    contents = """# The only section in this file
[global]
vm-min-mem = 300MiB
# a comment
dom0-mem-boost = 400MiB
# second comment

cache-margin-factor = 1.3
"""
    f.write_text(contents)
    assert helper.get_values() == {"vm-min-mem": 300, "dom0-mem-boost": 400}

    # now write some values
    helper.save_values({"vm-min-mem": 123, "dom0-mem-boost": 321})
    expected_text = """# The only section in this file
[global]
vm-min-mem = 123MiB
# a comment
dom0-mem-boost = 321MiB
# second comment

cache-margin-factor = 1.3
"""

    assert f.read_text() == expected_text

    # remove file contents, save and read values
    os.remove(f)
    helper.save_values({"vm-min-mem": 22, "dom0-mem-boost": 55})
    assert helper.get_values() == {"vm-min-mem": 22, "dom0-mem-boost": 55}


class MockHelper(Mock):
    MINMEM_NAME = "vm-min-mem"
    DOM0_NAME = "dom0-mem-boost"

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.values = {"vm-min-mem": 300, "dom0-mem-boost": 400}

    def get_values(self):
        return self.values

    def save_values(self, d):
        assert len(d) == 2 and "vm-min-mem" in d and "dom0-mem-boost" in d
        self.values["vm-min-mem"] = d["vm-min-mem"]
        self.values["dom0-mem-boost"] = d["dom0-mem-boost"]


@patch("qubes_config.global_config.basics_handler.QMemManHelper", MockHelper)
def test_memory_handler(test_builder):
    # pylint: disable=no-member
    # disable complaints about missing member - we have a patched QMemMan here
    handler = MemoryHandler(test_builder)
    assert isinstance(handler.mem_helper, MockHelper)

    assert handler.dom0_memory_spin.get_value() == 400
    assert handler.min_memory_spin.get_value() == 300
    assert handler.mem_helper.values == {
        "vm-min-mem": 300,
        "dom0-mem-boost": 400,
    }
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change stuff
    handler.dom0_memory_spin.set_value(1)
    handler.min_memory_spin.set_value(2)
    assert handler.mem_helper.values == {
        "vm-min-mem": 300,
        "dom0-mem-boost": 400,
    }
    assert handler.is_changed()
    assert handler.get_unsaved() == "Qube memory settings"

    # reset
    handler.reset()
    assert handler.dom0_memory_spin.get_value() == 400
    assert handler.min_memory_spin.get_value() == 300
    assert handler.mem_helper.values == {
        "vm-min-mem": 300,
        "dom0-mem-boost": 400,
    }
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""

    # change and save
    handler.dom0_memory_spin.set_value(10)
    handler.min_memory_spin.set_value(20)
    handler.save()
    assert handler.mem_helper.values == {"vm-min-mem": 20, "dom0-mem-boost": 10}
    assert not handler.is_changed()
    assert handler.get_unsaved() == ""


def test_kernels(test_qapp):
    combo = Gtk.ComboBoxText()

    handler = KernelHolder(test_qapp, combo)
    assert handler.widget.get_active_text() == "1.1"
    assert handler.get_unsaved() == ""

    # check that kernel dict is correct (see defaults in conftest)
    # 1.1\nmisc\n4.2
    assert handler._get_kernel_options() == {
        "1.1": "1.1",
        "4.2": "4.2",
        "misc": "misc",
        "(none)": None,
    }

    handler.widget.set_active_id("(none)")
    assert handler.get_unsaved() == "Default kernel"

    test_qapp.expected_calls[
        ("dom0", "admin.property.Set", "default_kernel", b"")
    ] = b"0\x00"
    handler.save()
    assert handler.get_unsaved() == ""


def test_basics_handler(real_builder, test_qapp):
    basics_handler = BasicSettingsHandler(real_builder, test_qapp)

    assert basics_handler.get_unsaved() == ""

    # all handlers are tested above, so now just use one as example
    # change clockvm
    clockvm_combo: Gtk.ComboBox = real_builder.get_object(
        "basics_clockvm_combo"
    )
    initial_clockvm = clockvm_combo.get_active_id()
    assert initial_clockvm != "test-blue"
    clockvm_combo.set_active_id("test-blue")

    assert basics_handler.get_unsaved() == "Clock qube"

    basics_handler.reset()

    assert clockvm_combo.get_active_id() == initial_clockvm
    assert basics_handler.get_unsaved() == ""

    clockvm_combo.set_active_id("test-blue")

    test_qapp.expected_calls[
        ("dom0", "admin.property.Set", "clockvm", b"test-blue")
    ] = b"0\x00"
    basics_handler.save()
