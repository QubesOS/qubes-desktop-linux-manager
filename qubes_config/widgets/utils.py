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
"""Qubes helper functions"""
import subprocess
import threading
import qubesadmin
import qubesadmin.exc
import qubesadmin.vm
from qrexec.policy.parser import Rule

from typing import Optional, Any, Dict, List

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


def get_feature(vm, feature_name, default_value=None):
    """Get feature, with a working default_value."""
    try:
        return vm.features.get(feature_name, default_value)
    except qubesadmin.exc.QubesDaemonAccessError:
        return default_value


def get_boolean_feature(vm, feature_name, default=False):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    else:
        result = default
    return result


def apply_feature_change_from_widget(
    widget, vm: qubesadmin.vm.QubesVM, feature_name: str
):
    """Change a feature value, taking into account weirdness with None.
    Widget must support is_changed and get_selected methods."""
    if widget.is_changed():
        value = widget.get_selected()
        apply_feature_change(vm, feature_name, value)


def apply_feature_change(
    vm: qubesadmin.vm.QubesVM, feature_name: str, new_value: Optional[Any]
):
    """Change a feature value, taking into account weirdness with None."""
    try:
        if new_value is None:
            if feature_name in vm.features:
                del vm.features[feature_name]
        else:
            vm.features[feature_name] = new_value
    except qubesadmin.exc.QubesDaemonAccessError:
        # pylint: disable=raise-missing-from
        raise qubesadmin.exc.QubesException(
            _(
                "Failed to set {feature_name} due to insufficient "
                "permissions"
            ).format(feature_name=feature_name)
        )


class BiDictionary(dict):
    """Helper bi-directional dictionary. By design, duplicate values
    cause errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inverted: Dict[Any, Any] = {}
        for key, value in self.items():
            if value in self.inverted:
                raise ValueError
            self.inverted[value] = key

    def __setitem__(self, key, value):
        if key in self:
            del self.inverted[self[key]]
        super().__setitem__(key, value)
        if value in self.inverted:
            raise ValueError
        self.inverted[value] = key

    def __delitem__(self, key):
        del self.inverted[self[key]]
        super().__delitem__(key)


def compare_rule_lists(
    rule_list_1: List[Rule], rule_list_2: List[Rule]
) -> bool:
    """Check if two provided rule lists are the same. Return True if yes."""
    if len(rule_list_1) != len(rule_list_2):
        return False
    for rule, rule_2 in zip(rule_list_1, rule_list_2):
        if str(rule) != str(rule_2):
            return False
    return True


def _open_url_in_dvm(url, default_dvm: qubesadmin.vm.QubesVM):
    subprocess.run(
        [
            "qvm-run",
            "-p",
            "--service",
            f"--dispvm={default_dvm}",
            "qubes.OpenURL",
        ],
        input=url.encode(),
        check=False,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )


def open_url_in_disposable(url: str, qapp: qubesadmin.Qubes):
    """Open provided url in disposable qube based on default disposable
    template"""
    default_dvm = qapp.default_dispvm
    open_thread = threading.Thread(
        group=None, target=_open_url_in_dvm, args=[url, default_dvm]
    )
    open_thread.start()
