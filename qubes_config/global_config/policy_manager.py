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
"""Class used to manage PolicyClient and do some convenience processing."""
import subprocess
from typing import Optional, List, Tuple

from qrexec.policy.admin_client import PolicyClient
from qrexec.policy.parser import StringPolicy, Rule
from qubes_config.widgets.utils import compare_rule_lists

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class PolicyManager:
    """
    Single manager for interacting with Qubes Policy.
    Should be used as a singleton.
    """

    def __init__(self):
        self.policy_client = PolicyClient()
        self.policy_disclaimer = _(
            """
# THIS IS AN AUTOMATICALLY GENERATED POLICY FILE.
# Any changes made manually may be overwritten by Qubes Configuration Tools.

"""
        )

    def get_all_policy_files(self, service: str) -> List[str]:
        """Just get a straightforward list of all relevant policy files."""
        try:
            return self.policy_client.policy_get_files(service)
        except subprocess.CalledProcessError:
            return []

    def get_conflicting_policy_files(
        self, service: str, own_file: str
    ) -> List[str]:
        """
        Get a list of policy files (as str) that apply to the selected service
        and are before it in load order.
        :param service: service name
        :param own_file: name of the config's own file
        :return: list of file names as str
        """
        files = sorted(self.get_all_policy_files(service))
        conflicting_files = []
        for f in files:
            if not f:
                # this is a workaround; if there is no file applicable to the
                # policy, PolicyClient returns a single empty string.
                continue
            if f >= own_file:
                break
            conflicting_files.append(f)
        return conflicting_files

    def get_rules_from_filename(
        self, filename: str, default_policy: str
    ) -> Tuple[List[Rule], Optional[str]]:
        """Get rules contained in a provided file. If the file does not exist,
        return default policy.
        Return list of Rule objects and str of the PolicyClient's token
        for the file."""
        try:
            rules_text, token = self.policy_client.policy_get(filename)
        except subprocess.CalledProcessError:
            if not default_policy:
                return [], None
            rules_text, token = default_policy, None

        rules = self.text_to_rules(rules_text)

        return rules, token

    def compare_rules_to_text(self, rules, file_text) -> bool:
        """Check if the list of rules is equivalent to policy file text."""
        second_rules = self.text_to_rules(file_text)
        return compare_rule_lists(rules, second_rules)

    @staticmethod
    def new_rule(
        service: str, source: str, target: str, action: str, argument: str = "*"
    ) -> Rule:
        """Create a new Rule object from given parameters: service, source,
        target and action should be provided according to policy file specs."""
        return Rule.from_line(
            None,
            f"{service}\t{argument}\t{source}\t{target}\t{action}",
            filepath=None,
            lineno=0,
        )

    def save_rules(
        self, file_name: str, rules_list: List[Rule], token: Optional[str]
    ):
        """Save provided list of rules to a file. Must provide
        a token corresponding to last file access, to avoid unexpected
        overwriting."""
        new_text = self.rules_to_text(rules_list)
        self.policy_client.policy_replace(file_name, new_text, token or "any")

    def rules_to_text(self, rules_list: List[Rule]) -> str:
        """Convert list of Rules to text ready to be stored in a file."""
        return (
            self.policy_disclaimer
            + "\n".join([str(rule) for rule in rules_list])
            + "\n"
        )

    @staticmethod
    def text_to_rules(text: str) -> List[Rule]:
        """Convert policy file text to a list of Rules."""
        return StringPolicy(policy={"__main__": text}).rules
