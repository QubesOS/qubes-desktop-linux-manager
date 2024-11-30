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
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-module-docstring
import pytest

import qubesadmin.exc
from ..widgets.utils import (
    apply_feature_change,
    get_boolean_feature,
    get_feature,
    apply_feature_change_from_widget,
    BiDictionary,
)


def test_get_feature(test_qapp):
    """Test if get feature methods behave correctly, in
    particular when setting features to None and handling boolean features."""
    feature_name = "test_feature"
    default_value = "test"
    vm = test_qapp.domains["test-vm"]

    # missing feature
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", feature_name, None)
    ] = b"2\x00QubesFeatureNotFoundError\x00\x00Feature not set\x00"
    assert get_feature(vm, feature_name, default_value) == default_value

    # correct feature
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", feature_name, None)
    ] = b"0\0value1"
    assert get_feature(vm, feature_name, default_value) == "value1"

    # boolean feature
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", feature_name, None)
    ] = b"0\x001"
    assert get_boolean_feature(vm, feature_name, False) is True
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", feature_name, None)
    ] = b"2\x00QubesFeatureNotFoundError\x00\x00Feature not set\x00"
    assert get_boolean_feature(vm, feature_name, True) is True

    # set feature
    call = ("test-vm", "admin.vm.feature.Set", feature_name, b"1")
    test_qapp.expected_calls[call] = b"0\0"
    apply_feature_change(vm, feature_name, True)
    assert call in test_qapp.actual_calls

    call = ("test-vm", "admin.vm.feature.Set", feature_name, b"text")
    test_qapp.expected_calls[call] = b"0\0"
    apply_feature_change(vm, feature_name, "text")
    assert call in test_qapp.actual_calls

    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.List", None, None)
    ] = b"0\x00test_feature"
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Remove", feature_name, None)
    ] = b"0\x001"
    apply_feature_change(vm, feature_name, None)
    assert (
        "test-vm",
        "admin.vm.feature.Remove",
        feature_name,
        None,
    ) in test_qapp.actual_calls


def test_feature_unavailable(test_qapp):
    feature_name = "test_feature"
    default_value = "test"
    vm = test_qapp.domains["test-vm"]

    # missing feature
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Get", feature_name, None)
    ] = b"2\x00QubesDaemonAccessError\x00\x00Feature not available\x00"
    assert get_feature(vm, feature_name, default_value) == default_value

    with pytest.raises(qubesadmin.exc.QubesException):
        test_qapp.expected_calls[
            ("test-vm", "admin.vm.feature.Set", feature_name, b"1")
        ] = b"2\x00QubesDaemonAccessError\x00\x00Feature not available\x00"
        apply_feature_change(vm, feature_name, True)


def test_apply_change_from_widget(test_qapp):
    vm = test_qapp.domains["test-vm"]
    feature_name = "test-feature"

    class MockWidget:
        def __init__(self, changed, value):
            self.changed = changed
            self.value = value

        def is_changed(self):
            return self.changed

        def get_selected(self):
            return self.value

    # should not try to set anything
    apply_feature_change_from_widget(MockWidget(False, None), vm, feature_name)

    # set correctly
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Set", feature_name, b"1")
    ] = b"0\0"
    apply_feature_change_from_widget(MockWidget(True, True), vm, feature_name)

    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Set", feature_name, b"text")
    ] = b"0\0"
    apply_feature_change_from_widget(MockWidget(True, "text"), vm, feature_name)

    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.List", None, None)
    ] = b"0\x00other-feature"
    test_qapp.expected_calls[
        ("test-vm", "admin.vm.feature.Remove", feature_name, None)
    ] = b"0\x001"
    apply_feature_change_from_widget(MockWidget(True, None), vm, feature_name)


def test_bidict():
    d = {"a": 1, "b": 2}

    bidict = BiDictionary(d)
    assert bidict.inverted == {1: "a", 2: "b"}
    bidict["c"] = 3
    assert bidict.inverted == {1: "a", 2: "b", 3: "c"}
    del bidict["a"]
    assert bidict.inverted == {2: "b", 3: "c"}
    with pytest.raises(ValueError):
        bidict["b"] = 3

    with pytest.raises(ValueError):
        d = {"a": 1, "b": 1}
        BiDictionary(d)
