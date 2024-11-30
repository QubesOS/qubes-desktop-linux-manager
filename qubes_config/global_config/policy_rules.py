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
"""Classes providing simplified wrap around Rule objects."""
import abc

from typing import Dict, Optional
from qrexec.policy.parser import (
    Rule,
    Allow,
    Ask,
    Source,
    Target,
    Action,
    DispVM,
    DispVMTemplate,
)

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class AbstractRuleWrapper(abc.ABC):
    """Wrapper for Rule objects.
    ACTION_CHOICES provides human-understandable names for choosing
    action value in dropdowns."""

    ACTION_CHOICES: Dict[str, str] = {}

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        self._rule = rule

    @property
    @abc.abstractmethod
    def source(self):
        """Policy call source, represented as string."""

    @source.setter
    def source(self, new_value: str):
        """Policy call source setter, takes strings."""

    @property
    @abc.abstractmethod
    def target(self):
        """
        Policy call target (human-readable, it may not correspond to Target
        field in policy files, but may be e.g. allow target=???
        Represented as string.
        """

    @target.setter
    def target(self, new_value: str):
        """Policy call target setter, takes strings."""

    @property
    @abc.abstractmethod
    def action(self):
        """Policy action (ask, allow, deny). Represented as string."""

    @action.setter
    def action(self, new_value: str):
        """Policy action (ask, allow, deny) setter. Takes strings."""

    @property
    @abc.abstractmethod
    def raw_rule(self):
        """
        Rule object.
        """

    def is_rule_fundamental(self) -> bool:
        """
        Return True if the rule should be placed in the main list, False if it's
        an exception.
        """
        return self.source == "@anyvm" and self.target == "@anyvm"

    def is_rule_conflicting(
        self, other_source: str, other_target: str, other_action: str
    ) -> bool:
        # pylint: disable=unused-argument
        """
        Return True if rule with other_source and other_target would conflict
         with self.
        """
        return self.source == other_source and self.target == other_target

    @staticmethod
    # pylint: disable=unused-argument
    def get_rule_errors(source: str, target: str, action: str) -> Optional[str]:
        """Return None if rule is valid and str describing error if not."""
        return None


class RuleSimple(AbstractRuleWrapper):
    """
    Simple Rule wrapper, where:
    source = source
    target = target
    action = just action, without params.
    Returns and accepts strings as target/source/action.
    """

    ACTION_CHOICES = {"ask": _("ask"), "allow": _("always"), "deny": _("never")}

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)

        if (
            str(rule.action) not in ["ask", "deny", "allow"]
            or rule.argument is not None
        ):
            raise ValueError(_("Unrecognized action: ") + str(rule.action))

    @property
    def target(self):
        return str(self._rule.target)

    @target.setter
    def target(self, new_value):
        new_target = Target(new_value)
        self._rule.target = new_target

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return type(self._rule.action).__name__.lower()

    @action.setter
    def action(self, new_value):
        try:
            new_action = Action[new_value].value(self._rule)
        except KeyError:
            raise ValueError  # pylint: disable=raise-missing-from
        self._rule.action = new_action

    @property
    def raw_rule(self):
        return self._rule


class RuleSimpleAskIsAllow(RuleSimple):
    """Simple rule where there is no Allow and Ask is pretending to be Allow.
    Used chiefly by Clipboard rules."""

    ACTION_CHOICES = {"ask": _("always"), "deny": _("never")}

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)

        if str(rule.action) not in ["ask", "deny"] or rule.argument is not None:
            raise ValueError(_("Unrecognized action: ") + str(rule.action))

    @staticmethod
    def get_rule_errors(source: str, target: str, action: str) -> Optional[str]:
        # action must be a simple ask/allow/deny
        if action not in ["ask", "deny"]:
            return _("Unrecognized action: ") + action
        return None


class RuleSimpleNoAllow(RuleSimple):
    """Simple rule that has no Allow option"""

    ACTION_CHOICES = {"ask": _("can"), "deny": _("can not")}

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)

        if str(rule.action) not in ["ask", "deny"] or rule.argument is not None:
            raise ValueError(_("Unrecognized action: ") + str(rule.action))

    @staticmethod
    def get_rule_errors(source: str, target: str, action: str) -> Optional[str]:
        # action must be a simple ask/allow/deny
        if action not in ["ask", "deny"]:
            return _("Unrecognized action: ") + action
        return None


class RuleTargetedAdminVM(AbstractRuleWrapper):
    """
    Rule wrapper for rules with the following rules:
    - source is source
    - action is main action (e.g. 'allow target=vm' is allow
    - wrapped rule must have target=@adminvm
    - if action is ask, wrapped rule must have default_target=@adminvm
    Returns strings as target/source/action. Target is not settable.
    """

    ACTION_CHOICES = {
        "ask": _("enable"),
        "allow": _("allow"),
        "deny": _("disable"),
    }

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)
        if rule.argument is not None:
            raise ValueError(_("Rule cannot have an argument"))
        if rule.target != "@adminvm":
            raise ValueError(_("Target must be @adminvm"))
        if isinstance(rule.action, Ask):
            if rule.action.default_target != "@adminvm":
                raise ValueError(
                    _("If action is ask, default_target must be @adminvm")
                )
        if isinstance(rule.action, Allow):
            if rule.action.target:
                raise ValueError(
                    _("If action is allow, no parameters are allowed")
                )

    @property
    def target(self):
        return "@adminvm"

    @target.setter
    def target(self, new_value):
        raise ValueError(_("Cannot set target on this type of rule."))

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return type(self._rule.action).__name__.lower()

    @action.setter
    def action(self, new_value):
        new_action = Action[new_value].value(self._rule)
        self._rule.action = new_action
        if new_value == "ask":
            self._rule.action.default_target = "@adminvm"

    @property
    def raw_rule(self):
        return self._rule


class RuleTargeted(AbstractRuleWrapper):
    """
    Rule wrapper for rules with the following rules:
    - source is source
    - action is main action (e.g. 'allow target=vm' is allow
    - target can be:
        - if original rule target is @default, user allow's target or ask's
            default target, but neither of those should be ever set to a
            keyword
        - else use original rule's normal target
    Returns and accepts strings as target/source/action.
    """

    ACTION_CHOICES = {
        "ask": _("ask"),
        "allow": _("automatically"),
        "deny": _("never"),
    }

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)
        if rule.argument is not None:
            raise ValueError(_("Rule cannot have an argument"))
        errors = self.get_rule_errors(
            str(rule.source), str(rule.target), str(rule.action)
        )
        if errors:
            raise ValueError(errors)

    @property
    def target(self):
        if isinstance(self._rule.action, Ask):
            if self._rule.target == "@default":
                return str(self._rule.action.default_target)
        if isinstance(self._rule.action, Allow):
            if self._rule.target == "@default":
                return str(self._rule.action.target)
        return str(self._rule.target)

    @target.setter
    def target(self, new_value):
        new_target = Target(new_value)

        if new_value.startswith("@"):
            self._rule.target = new_target
            if hasattr(self._rule.action, "target"):
                self._rule.action.target = None
            if hasattr(self._rule.action, "default_target"):
                self._rule.action.default_target = None
            return

        if isinstance(self._rule.action, Ask):
            self._rule.target = Target("@default")
            self._rule.action.default_target = new_target
            return
        if isinstance(self._rule.action, Allow):
            self._rule.target = Target("@default")
            self._rule.action.target = new_target
            return

        self._rule.target = new_target

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return type(self._rule.action).__name__.lower()

    @action.setter
    def action(self, new_value):
        old_target = self.target
        new_action = Action[new_value].value(self._rule)
        self._rule.action = new_action
        self.target = old_target

    @property
    def raw_rule(self):
        return self._rule

    def is_rule_fundamental(self) -> bool:
        if super().is_rule_fundamental():
            return True
        return self.source == "@anyvm" and self.raw_rule.target == "@dispvm"

    @staticmethod
    def get_rule_errors(source: str, target: str, action: str) -> Optional[str]:
        if not source.startswith("@"):
            if target.startswith("@") and target != "@dispvm":
                if action in ("ask", "allow"):
                    return _(
                        "This type of action supports only single-qube "
                        "destination qubes for single-qube source qubes."
                    )
        return None

    def is_rule_conflicting(
        self, other_source: str, other_target: str, other_action: str
    ) -> bool:
        """
        Return True if rule with other_source and other_target would conflict
         with self.
        """
        if super().is_rule_conflicting(
            other_source, other_target, other_action
        ):
            return True
        if self.action == "allow" and other_source == self.source:
            return True
        return False


class RuleDispVM(AbstractRuleWrapper):
    """
    Rule wrapper for rules used with target=@dispvm. The following applies:
    - source is source
    - in policy, target=@dispvm
    - if action = deny, wrapped rule does not show any target
    - if action = allow, show the target of target=...; store target as
    @dispvm:target_name, or @dispvm if it's default dispvm
    - if action = ask, show the target of default_target=...; store target as
    @dispvm:target_name, or @dispvm if it's default dispvm
    Returns and accepts strings as target/source/action.
    """

    ACTION_CHOICES = {"ask": _("ask"), "allow": _("always"), "deny": _("never")}

    def __init__(self, rule: Rule):
        """
        :param rule: Rule object
        """
        super().__init__(rule)

        if rule.argument is not None:
            raise ValueError(_("Rule cannot have an argument"))

        if str(rule.target) != "@dispvm":
            raise ValueError("Target must be @dispvm")

        if isinstance(rule.action, Ask) and not isinstance(
            rule.action.default_target, (DispVM, DispVMTemplate)
        ):
            raise ValueError("default_target must include @dispvm")
        if isinstance(rule.action, Allow) and not isinstance(
            rule.action.target, (DispVM, DispVMTemplate)
        ):
            raise ValueError("target must include @dispvm")

    @property
    def target(self):
        target = ""
        if isinstance(self._rule.action, Ask):
            target = str(self._rule.action.default_target or "")
        if isinstance(self._rule.action, Allow):
            target = str(self._rule.action.target or "")
        if target.startswith("@dispvm:"):
            target = target[len("@dispvm:") :]
        return target

    @target.setter
    def target(self, new_value):
        # when setting to a non-@dispvm, append @dispvm: at the start
        if not new_value.startswith("@dispvm"):
            new_value = "@dispvm:" + new_value
        new_target = Target(new_value)

        if isinstance(self._rule.action, Ask):
            self._rule.action.default_target = new_target
            return
        if isinstance(self._rule.action, Allow):
            self._rule.action.target = new_target
            return
        return  # deny has no target

    @property
    def source(self):
        return str(self._rule.source)

    @source.setter
    def source(self, new_value):
        new_source = Source(new_value)
        self._rule.source = new_source

    @property
    def action(self):
        return type(self._rule.action).__name__.lower()

    @action.setter
    def action(self, new_value):
        if self.action == "deny":
            old_target = "@dispvm"
        else:
            old_target = self.target
        new_action = Action[new_value].value(self._rule)
        self._rule.action = new_action
        if new_value != "deny":
            # when switching from anything to deny,
            # there is no need to change target
            self.target = old_target

    @property
    def raw_rule(self):
        return self._rule

    def is_rule_fundamental(self) -> bool:
        return False

    def is_rule_conflicting(
        self, other_source: str, other_target: str, other_action: str
    ) -> bool:
        """
        Return True if rule with other_source and other_target would conflict
         with self.
        """
        if other_source == self.source:
            return True
        return False


class AbstractVerbDescription(abc.ABC):
    """Class used to represent human-readable verb descriptions:
    Qube1 (will) ACTION (verb_description) Qube2"""

    @abc.abstractmethod
    def get_verb_for_action_and_target(self, action: str, target: str) -> str:
        """
        Get correct verb for a given action and target.
        """


class SimpleVerbDescription(AbstractVerbDescription):
    """Simplest verb description, where a given Action has one corresponding
    description"""

    def __init__(self, descr: Dict[str, str]):
        """
        :param descr: Dict of action: description, where action is one of
        ask, allow, deny
        """
        self.descr = descr
        if self.descr:
            self.max_length = max((len(x) for x in self.descr.values()))
        else:
            self.max_length = 0

    def get_verb_for_action_and_target(self, action: str, target: str) -> str:
        return self.descr.get(action, "").rjust(self.max_length, " ")


class TargetedVerbDescription(AbstractVerbDescription):
    """Verb description for more complex cases using target= and
    default_target."""

    def __init__(
        self,
        single_target_descr: Dict[str, str],
        multi_target_descr: Dict[str, str],
    ):
        """
        Both parameters are dicts of action: description, where action is one of
        ask, allow, deny
        :param single_target_descr: applies to actions where relevant target
        is a single VM or @dispvm
        :param multi_target_descr:  applies to other actions
        """
        self.single_target_descr = single_target_descr
        self.multi_target_descr = multi_target_descr

        self.max_length = max(
            (
                len(x)
                for x in [
                    *self.single_target_descr.values(),
                    *self.multi_target_descr.values(),
                ]
            )
        )

    def get_verb_for_action_and_target(self, action: str, target: str) -> str:
        if target.startswith("@") and target != "@dispvm":
            return self.multi_target_descr.get(action, "").rjust(
                self.max_length, " "
            )
        return self.single_target_descr.get(action, "").rjust(
            self.max_length, " "
        )
