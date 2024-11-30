# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Marta Marczykowska-Górecka
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

from ..global_config.conflict_handler import (
    ConflictFileListRow,
    ConflictFileHandler,
)


def test_row_normal_and_legacy():
    row_normal = ConflictFileListRow("test1")
    row_legacy = ConflictFileListRow("/etc/qubes-rpc/test")

    assert row_normal.get_style_context().has_class("problem_row")
    assert row_legacy.get_style_context().has_class("problem_row")

    assert (
        not row_normal.get_tooltip_text()
        or not "a legacy file" in row_normal.get_tooltip_text()
    )
    assert "a legacy file" in row_legacy.get_tooltip_text()


def test_conflict_handler_simple(test_builder, test_policy_manager):
    test_policy_manager.policy_client.service_to_files["ConflictTest"] = [
        "a",
        "b",
        "test",
        "z",
    ]
    test_policy_manager.policy_client.service_to_files["ConflictLegacy"] = [
        "/etc/qubes-rpc/test",
        "test",
        "z",
    ]

    conflict_handler = ConflictFileHandler(
        gtk_builder=test_builder,
        prefix="policytest",
        service_names=["ConflictTest"],
        own_file_name="test",
        policy_manager=test_policy_manager,
    )

    assert conflict_handler.problem_box.get_visible()
    children_labels = [
        str(child) for child in conflict_handler.problem_list.get_children()
    ]
    assert children_labels == ["a", "b"]


def test_conflict_handler_legacy(test_builder, test_policy_manager):
    test_policy_manager.policy_client.service_to_files["ConflictTest"] = [
        "a",
        "b",
        "test",
        "z",
    ]
    test_policy_manager.policy_client.service_to_files["ConflictLegacy"] = [
        "/etc/qubes-rpc/test",
        "test",
        "z",
    ]

    conflict_handler = ConflictFileHandler(
        gtk_builder=test_builder,
        prefix="policytest",
        service_names=["ConflictLegacy"],
        own_file_name="test",
        policy_manager=test_policy_manager,
    )

    assert conflict_handler.problem_box.get_visible()
    children_labels = [
        str(child) for child in conflict_handler.problem_list.get_children()
    ]
    assert children_labels == ["/etc/qubes-rpc/test"]


def test_conflict_handler_multiple(test_builder, test_policy_manager):
    test_policy_manager.policy_client.service_to_files["ConflictTest"] = [
        "a",
        "b",
        "test",
        "z",
    ]
    test_policy_manager.policy_client.service_to_files["ConflictLegacy"] = [
        "/etc/qubes-rpc/test",
        "test",
        "z",
    ]

    conflict_handler = ConflictFileHandler(
        gtk_builder=test_builder,
        prefix="policytest",
        service_names=["ConflictTest", "ConflictLegacy"],
        own_file_name="test",
        policy_manager=test_policy_manager,
    )

    assert conflict_handler.problem_box.get_visible()
    children_labels = [
        str(child) for child in conflict_handler.problem_list.get_children()
    ]
    assert sorted(children_labels) == sorted(["a", "b", "/etc/qubes-rpc/test"])


def test_conflict_handler_empty(test_builder, test_policy_manager):
    test_policy_manager.policy_client.service_to_files["ConflictTest"] = [
        "a",
        "b",
        "test",
        "z",
    ]
    test_policy_manager.policy_client.service_to_files["ConflictLegacy"] = [
        "/etc/qubes-rpc/test",
        "test",
        "z",
    ]

    conflict_handler = ConflictFileHandler(
        gtk_builder=test_builder,
        prefix="policytest",
        service_names=["ConflictTest"],
        own_file_name="a",
        policy_manager=test_policy_manager,
    )

    assert not conflict_handler.problem_box.get_visible()
