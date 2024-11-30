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
# pylint: disable=missing-module-docstring,missing-function-docstring
# pylint: disable=missing-class-docstring
import subprocess
from unittest.mock import patch

from ..global_config.policy_manager import PolicyManager
from qrexec.policy.parser import Rule


def test_conflict_files():
    def return_files(service_name):
        if service_name == "test":
            return ["a-test", "b-test", "c-test"]
        return [""]

    manager = PolicyManager()
    with patch(
        "qubes_config.global_config.policy_manager."
        "PolicyClient.policy_get_files"
    ) as mock_get:
        mock_get.side_effect = return_files

        assert manager.get_conflicting_policy_files("test", "d-test") == [
            "a-test",
            "b-test",
            "c-test",
        ]
        assert manager.get_conflicting_policy_files("test", "c-test") == [
            "a-test",
            "b-test",
        ]
        assert manager.get_conflicting_policy_files("test", "b-test") == [
            "a-test"
        ]
        assert not manager.get_conflicting_policy_files("test", "a-test")
        assert not manager.get_conflicting_policy_files("other", "test")


@patch("qubes_config.global_config.policy_manager.PolicyClient.policy_get")
@patch("qubes_config.global_config.policy_manager.PolicyClient.policy_replace")
def test_get_policy_from_file_new_no_default(mock_replace, mock_get):
    manager = PolicyManager()

    mock_get.side_effect = subprocess.CalledProcessError(2, "test")

    assert manager.get_rules_from_filename("test", "") == ([], None)
    assert not mock_replace.mock_calls


def test_get_policy_from_file_new():
    class MockPolicy:
        def __init__(self):
            self.files = {}

        def policy_get(self, filename):
            if filename in self.files:
                return self.files[filename], filename
            raise subprocess.CalledProcessError(2, "test")

        def policy_replace(self, filename, text):
            self.files[filename] = text

    manager = PolicyManager()
    manager.policy_client = MockPolicy()

    test_default = "Test\t*\t@anyvm\t@anyvm\tdeny"

    # token should be None (the file is new), but rules should be appropriate
    got_rules, token = manager.get_rules_from_filename("test", test_default)
    assert token is None
    assert len(got_rules) == 1
    assert str(got_rules[0]) == test_default
    assert "test" not in manager.policy_client.files


def test_get_policy_from_file_existing():
    manager = PolicyManager()

    rules = "Test\t*\t@anyvm\t@anyvm\tdeny"

    def get_file(filename):
        if filename == "test":
            return rules, "test"
        return "", ""

    with patch(
        "qubes_config.global_config.policy_manager.PolicyClient.policy_get"
    ) as mock_get:
        mock_get.side_effect = get_file

        got_rules, token = manager.get_rules_from_filename("test", "")
        assert token == "test"
        assert len(got_rules) == 1
        assert str(got_rules[0]) == rules

        got_rules, token = manager.get_rules_from_filename("test2", "")
        assert token == ""
        assert len(got_rules) == 0


def test_compare_rules_to_text():
    manager = PolicyManager()

    rule_text_1 = """Test * @anyvm @anyvm deny"""
    rule_text_2 = """Test * @anyvm @anyvm deny
Test +Test2 work @anyvm allow"""
    rule_text_3 = """Test * @anyvm @anyvm deny
Test * work @anyvm allow"""

    rules_1 = [
        Rule.from_line(
            None, "Test * @anyvm @anyvm deny", filepath=None, lineno=0
        )
    ]
    rules_2 = [
        Rule.from_line(
            None, "Test * @anyvm @anyvm deny", filepath=None, lineno=0
        ),
        Rule.from_line(
            None, "Test +Test2 work @anyvm allow", filepath=None, lineno=0
        ),
    ]
    rules_3 = [
        Rule.from_line(
            None, "Test * @anyvm @anyvm deny", filepath=None, lineno=0
        ),
        Rule.from_line(
            None, "Test * work @anyvm allow", filepath=None, lineno=0
        ),
    ]

    assert manager.compare_rules_to_text(rules_1, rule_text_1)
    assert manager.compare_rules_to_text(rules_2, rule_text_2)
    assert manager.compare_rules_to_text(rules_3, rule_text_3)
    assert not manager.compare_rules_to_text(rules_1, rule_text_2)
    assert not manager.compare_rules_to_text(rules_2, rule_text_1)
    assert not manager.compare_rules_to_text(rules_2, rule_text_3)
    assert not manager.compare_rules_to_text(rules_3, rule_text_2)


def test_new_rule():
    manager = PolicyManager()

    rule_1 = Rule.from_line(
        None, "Test * @anyvm @anyvm deny", filepath=None, lineno=0
    )
    rule_2 = Rule.from_line(
        None,
        "Test +Test @anyvm vault allow target=dom0",
        filepath=None,
        lineno=0,
    )

    assert str(manager.new_rule("Test", "@anyvm", "@anyvm", "deny")) == str(
        rule_1
    )
    assert str(
        manager.new_rule(
            service="Test",
            source="@anyvm",
            target="vault",
            action="allow target=dom0",
            argument="+Test",
        )
    ) == str(rule_2)


def test_save_policy():
    manager = PolicyManager()

    rule_text = "Test\t*\t@anyvm\t@anyvm\tdeny"
    rule = Rule.from_line(
        None, "Test * @anyvm @anyvm deny", filepath=None, lineno=0
    )

    def replace_file(file_name: str, new_text: str, _token):
        if file_name == "test":
            if not new_text.startswith(manager.policy_disclaimer):
                assert False
            if not rule_text in new_text:
                assert False
            return
        assert False

    with patch(
        "qubes_config.global_config.policy_manager."
        "PolicyClient.policy_replace"
    ) as mock_replace:
        mock_replace.side_effect = replace_file
        manager.save_rules("test", [rule], "any")
