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
import pytest

from qrexec.policy.parser import Rule
from ..global_config.policy_rules import (
    RuleSimple,
    RuleTargeted,
    RuleDispVM,
    RuleTargetedAdminVM,
)


def make_rule(source, target, action):
    return Rule.from_line(
        None,
        f"Service\t*\t{source}\t{target}\t{action}",
        filepath=None,
        lineno=0,
    )


def test_simple_rule():
    basic_rule = make_rule("vm1", "vm2", "allow")
    wrapped_rule = RuleSimple(basic_rule)
    assert wrapped_rule.raw_rule == basic_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "allow"

    wrapped_rule.source = "vm2"
    assert str(wrapped_rule.raw_rule) == str(make_rule("vm2", "vm2", "allow"))
    wrapped_rule.target = "vm1"
    assert str(wrapped_rule.raw_rule) == str(make_rule("vm2", "vm1", "allow"))
    wrapped_rule.action = "deny"
    assert str(wrapped_rule.raw_rule) == str(make_rule("vm2", "vm1", "deny"))
    assert not wrapped_rule.is_rule_fundamental()
    assert wrapped_rule.is_rule_conflicting(
        other_action="deny", other_source="vm2", other_target="vm1"
    )
    fundamental_rule = make_rule("@anyvm", "@anyvm", "deny")
    assert RuleSimple(fundamental_rule).is_rule_fundamental()

    assert RuleSimple.get_rule_errors("@anyvm", "@anyvm", "deny") is None

    with pytest.raises(ValueError):
        wrapped_rule.action = "allow target=dom0"

    wrong_rule_3 = make_rule("vm1", "vm2", "allow")
    wrong_rule_3.argument = "+alamakota"
    with pytest.raises(ValueError):
        RuleSimple(wrong_rule_3)


def test_targeted_rule():
    deny_rule = make_rule("vm1", "vm2", "deny")
    wrapped_rule = RuleTargeted(deny_rule)
    assert wrapped_rule.raw_rule == deny_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "deny"

    allow_rule = make_rule("vm1", "@default", "allow target=vm2")
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "allow"

    ask_rule = make_rule("vm1", "@default", "ask default_target=vm2")
    wrapped_rule = RuleTargeted(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "ask"

    wrong_rule = make_rule("vm1", "@default", "ask default_target=vm2")
    wrong_rule.argument = "+alamakota"
    with pytest.raises(ValueError):
        RuleTargeted(wrong_rule)


def test_targeted_adminvm_rule():
    deny_rule = make_rule("vm1", "@adminvm", "deny")
    wrapped_rule = RuleTargetedAdminVM(deny_rule)
    assert wrapped_rule.raw_rule == deny_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "@adminvm"
    assert wrapped_rule.action == "deny"

    allow_rule = make_rule("vm1", "@adminvm", "allow")
    wrapped_rule = RuleTargetedAdminVM(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "@adminvm"
    assert wrapped_rule.action == "allow"

    ask_rule = make_rule("vm1", "@adminvm", "ask default_target=@adminvm")
    wrapped_rule = RuleTargetedAdminVM(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "@adminvm"
    assert wrapped_rule.action == "ask"


def test_targeted_rule_weird_cases():
    # if we get fed wrong-ish values:
    allow_rule = make_rule("vm1", "vm2", "allow")
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "allow"

    # but it should get converted to expected things if set
    wrapped_rule.target = "vm3"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@default", "allow target=vm3")
    )

    ask_rule = make_rule("vm1", "vm2", "ask")
    wrapped_rule = RuleTargeted(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "ask"

    # and same here
    wrapped_rule.target = "vm3"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@default", "ask default_target=vm3")
    )

    wrong_rule = make_rule("vm1", "@adminvm", "ask default_target=sys-usb")
    with pytest.raises(ValueError):
        RuleTargetedAdminVM(wrong_rule)

    wrong_rule_2 = make_rule("vm1", "sys-usb", "ask default_target=@adminvm")
    with pytest.raises(ValueError):
        RuleTargetedAdminVM(wrong_rule_2)

    wrong_rule_3 = make_rule("vm1", "vm2", "allow")
    wrong_rule_3.argument = "+alamakota"
    with pytest.raises(ValueError):
        RuleTargetedAdminVM(wrong_rule_3)


def test_targeted_tokens():
    # can't make a rule with @anyvm target here
    allow_rule = make_rule("vm1", "@anyvm", "allow")
    with pytest.raises(ValueError):
        RuleTargeted(allow_rule)

    # but dispvm is ok and should be treated like normal target
    allow_rule = make_rule("vm1", "@dispvm", "allow")
    wrapped_rule = RuleTargeted(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "@dispvm"
    assert wrapped_rule.action == "allow"

    wrapped_rule.target = "vm3"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@default", "allow target=vm3")
    )

    allow_rule = make_rule("vm1", "@default", "allow target=vm2")
    wrapped_rule = RuleTargeted(allow_rule)
    wrapped_rule.target = "@anyvm"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@anyvm", "allow")
    )

    ask_rule = make_rule("vm1", "@default", "ask default_target=vm2")
    wrapped_rule = RuleTargeted(ask_rule)
    wrapped_rule.target = "@anyvm"
    assert str(wrapped_rule.raw_rule) == str(make_rule("vm1", "@anyvm", "ask"))


def test_targeted_change_action():
    allow_rule = make_rule("vm1", "@default", "allow target=vm2")
    ask_rule = make_rule("vm1", "@default", "ask default_target=vm2")

    wrapped_allow = RuleTargeted(allow_rule)
    wrapped_ask = RuleTargeted(ask_rule)

    wrapped_allow.action = "ask"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)

    allow_rule = make_rule("vm1", "@default", "allow target=vm2")
    ask_rule = make_rule("vm1", "@default", "ask default_target=vm2")

    wrapped_allow = RuleTargeted(allow_rule)
    wrapped_ask = RuleTargeted(ask_rule)

    wrapped_ask.action = "allow"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)


def test_targeted_adminvm_change_action():
    allow_rule = make_rule("vm1", "@adminvm", "allow")
    ask_rule = make_rule("vm1", "@adminvm", "ask default_target=@adminvm")

    wrapped_allow = RuleTargetedAdminVM(allow_rule)
    wrapped_ask = RuleTargetedAdminVM(ask_rule)

    wrapped_allow.action = "ask"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)

    allow_rule = make_rule("vm1", "@adminvm", "allow")
    ask_rule = make_rule("vm1", "@adminvm", "ask default_target=@adminvm")

    wrapped_allow = RuleTargetedAdminVM(allow_rule)
    wrapped_ask = RuleTargetedAdminVM(ask_rule)

    wrapped_ask.action = "allow"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)


def test_targeted_adminvm_change_tokens():
    allow_rule = make_rule("vm1", "@adminvm", "allow")
    ask_rule = make_rule("vm1", "@adminvm", "ask default_target=@adminvm")
    deny_rule = make_rule("vm1", "@adminvm", "deny")

    wrapped_allow = RuleTargetedAdminVM(allow_rule)
    wrapped_ask = RuleTargetedAdminVM(ask_rule)
    wrapped_deny = RuleTargetedAdminVM(deny_rule)

    with pytest.raises(ValueError):
        wrapped_allow.target = "vm2"
    with pytest.raises(ValueError):
        wrapped_ask.target = "vm2"
    with pytest.raises(ValueError):
        wrapped_deny.target = "vm2"

    wrapped_allow.source = "vm2"
    wrapped_ask.source = "vm2"
    wrapped_deny.source = "vm2"

    assert str(wrapped_allow.raw_rule) == str(
        make_rule("vm2", "@adminvm", "allow")
    )
    assert str(wrapped_ask.raw_rule) == str(
        make_rule("vm2", "@adminvm", "ask default_target=@adminvm")
    )
    assert str(wrapped_deny.raw_rule) == str(
        make_rule("vm2", "@adminvm", "deny")
    )


def test_targeted_fundamental():
    fundamental_rule = make_rule("@anyvm", "@anyvm", "ask")
    assert RuleTargeted(fundamental_rule).is_rule_fundamental()

    fundamental_rule = make_rule("@anyvm", "@dispvm", "allow")
    fundamental_wrapped = RuleTargeted(fundamental_rule)
    assert fundamental_wrapped.is_rule_fundamental()

    fundamental_wrapped.target = "vm2"
    assert not fundamental_wrapped.is_rule_fundamental()


def test_targeted_validity():
    assert RuleTargeted.get_rule_errors(
        source="vm1", target="@anyvm", action="ask"
    )
    assert RuleTargeted.get_rule_errors(
        source="vm1", target="@anyvm", action="allow"
    )
    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="@anyvm", action="deny"
    )

    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="@dispvm", action="ask"
    )
    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="@dispvm", action="allow"
    )
    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="@dispvm", action="deny"
    )

    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="vm2", action="ask"
    )
    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="vm2", action="allow"
    )
    assert not RuleTargeted.get_rule_errors(
        source="vm1", target="vm2", action="deny"
    )


def test_targeted_conflict():
    rule_allow = make_rule("vm1", "@default", "allow target=vm2")
    rule_ask = make_rule("vm1", "@default", "ask default_target=vm2")
    rule_deny = make_rule("vm1", "vm2", "deny")

    wrapped_allow = RuleTargeted(rule_allow)
    wrapped_ask = RuleTargeted(rule_ask)
    wrapped_deny = RuleTargeted(rule_deny)

    assert wrapped_allow.is_rule_conflicting(
        other_source="vm1", other_target="vm2", other_action="deny"
    )
    assert wrapped_allow.is_rule_conflicting(
        other_source="vm1", other_target="vm2", other_action="ask"
    )
    assert wrapped_allow.is_rule_conflicting(
        other_source="vm1", other_target="vm3", other_action="allow"
    )

    assert wrapped_ask.is_rule_conflicting(
        other_source="vm1", other_target="vm2", other_action="deny"
    )
    assert not wrapped_ask.is_rule_conflicting(
        other_source="vm1", other_target="vm3", other_action="allow"
    )
    assert not wrapped_ask.is_rule_conflicting(
        other_source="vm1", other_target="vm3", other_action="ask"
    )

    assert wrapped_deny.is_rule_conflicting(
        other_source="vm1", other_target="vm2", other_action="allow"
    )
    assert not wrapped_deny.is_rule_conflicting(
        other_source="vm1", other_target="vm3", other_action="ask"
    )
    assert not wrapped_deny.is_rule_conflicting(
        other_source="vm1", other_target="vm3", other_action="allow"
    )


def test_dispvm_rule():
    deny_rule = make_rule("vm1", "@dispvm", "deny")
    wrapped_rule = RuleDispVM(deny_rule)
    assert wrapped_rule.raw_rule == deny_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == ""
    assert wrapped_rule.action == "deny"

    allow_rule = make_rule("vm1", "@dispvm", "allow target=@dispvm:vm2")
    wrapped_rule = RuleDispVM(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "allow"

    ask_rule = make_rule("vm1", "@dispvm", "ask default_target=@dispvm:vm2")
    wrapped_rule = RuleDispVM(ask_rule)
    assert wrapped_rule.raw_rule == ask_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "ask"


def test_dispvm_tokens():
    # treat dispvm correctly
    allow_rule = make_rule("vm1", "@dispvm", "allow target=@dispvm:vm2")
    wrapped_rule = RuleDispVM(allow_rule)
    assert wrapped_rule.raw_rule == allow_rule
    assert wrapped_rule.source == "vm1"
    assert wrapped_rule.target == "vm2"
    assert wrapped_rule.action == "allow"

    wrapped_rule.target = "vm3"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@dispvm", "allow target=@dispvm:vm3")
    )
    wrapped_rule.target = "@dispvm"
    assert str(wrapped_rule.raw_rule) == str(
        make_rule("vm1", "@dispvm", "allow target=@dispvm")
    )


def test_dispvm_change_action():
    allow_rule = make_rule("vm1", "@dispvm", "allow target=@dispvm:vm2")
    ask_rule = make_rule("vm1", "@dispvm", "ask default_target=@dispvm:vm2")

    wrapped_allow = RuleDispVM(allow_rule)
    wrapped_ask = RuleDispVM(ask_rule)

    wrapped_allow.action = "ask"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)

    allow_rule = make_rule("vm1", "@dispvm", "allow target=@dispvm:vm2")
    ask_rule = make_rule("vm1", "@dispvm", "ask default_target=@dispvm:vm2")
    deny_rule = make_rule("vm1", "@dispvm", "deny")

    wrapped_allow = RuleDispVM(allow_rule)
    wrapped_ask = RuleDispVM(ask_rule)
    wrapped_deny = RuleDispVM(deny_rule)

    wrapped_ask.action = "allow"
    assert str(wrapped_allow.raw_rule) == str(wrapped_ask.raw_rule)

    wrapped_ask.action = "deny"
    assert str(wrapped_deny.raw_rule) == str(wrapped_ask.raw_rule)


def test_dispvm_validity():
    with pytest.raises(ValueError):
        rule = make_rule("vm1", "vm2", "deny")
        RuleDispVM(rule)

    with pytest.raises(ValueError):
        rule = make_rule("vm1", "@dispvm", "ask")
        RuleDispVM(rule)

    with pytest.raises(ValueError):
        rule = make_rule("vm1", "@dispvm", "allow")
        RuleDispVM(rule)

    with pytest.raises(ValueError):
        rule = make_rule("vm1", "vm2", "allow target=vm2")
        RuleDispVM(rule)

    with pytest.raises(ValueError):
        rule = make_rule("vm1", "@dispvm", "allow target=vm2")
        RuleDispVM(rule)

    with pytest.raises(ValueError):
        rule = make_rule("vm1", "@dispvm", "allow target=vm2")
        rule.argument = "+alamakota"
        RuleDispVM(rule)


def test_dispvm_conflict():
    rule_allow = make_rule("vm1", "@dispvm", "allow target=@dispvm:vm2")
    rule_ask = make_rule("vm1", "@dispvm", "ask default_target=@dispvm:vm2")
    rule_deny = make_rule("vm1", "@dispvm", "deny")

    wrapped_allow = RuleDispVM(rule_allow)
    wrapped_ask = RuleDispVM(rule_ask)
    wrapped_deny = RuleDispVM(rule_deny)

    for rule in [wrapped_ask, wrapped_allow, wrapped_deny]:
        assert rule.is_rule_conflicting(
            other_source="vm1", other_target="vm3", other_action="deny"
        )

        assert rule.is_rule_conflicting(
            other_source="vm1", other_target="vm3", other_action="ask"
        )

        assert rule.is_rule_conflicting(
            other_source="vm1", other_target="vm3", other_action="allow"
        )
