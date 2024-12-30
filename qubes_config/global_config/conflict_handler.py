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
"""Handle detecting and showing policy file conflicts."""
from typing import List

from .policy_manager import PolicyManager
from ..widgets.gtk_utils import load_icon

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class ConflictFileListRow(Gtk.ListBoxRow):
    """A ListBox row representing a policy file with conflicting info."""

    def __init__(self, file_name: str):
        super().__init__()
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)

        self.get_style_context().add_class("problem_row")

        self.label = Gtk.Label()
        self.label.set_text(file_name)
        self.label.get_style_context().add_class("red_code")
        self.box.pack_start(self.label, False, False, 0)

        if file_name.startswith("/etc/qubes-rpc"):
            self.icon = Gtk.Image()
            self.icon.set_from_pixbuf(load_icon("qubes-question", 14, 14))
            tooltip = _(
                "This is a legacy file from previous Qubes versions. "
                "Custom policy contained there will no longer "
                "be supported in Qubes 4.2."
            )
            self.set_tooltip_text(tooltip)
            self.box.pack_start(self.icon, False, False, 0)

    def __str__(self):
        # pylint: disable=arguments-differ
        return self.label.get_text()


class ConflictFileHandler:
    """Handler for conflicting policy files."""

    def __init__(
        self,
        gtk_builder: Gtk.Builder,
        prefix: str,
        service_names: List[str],
        own_file_name: str,
        policy_manager: PolicyManager,
    ):
        self.service_names = service_names
        self.own_file_name = own_file_name
        self.policy_manager = policy_manager

        self.problem_box: Gtk.Box = gtk_builder.get_object(
            f"{prefix}_problem_box"
        )
        self.problem_list: Gtk.ListBox = gtk_builder.get_object(
            f"{prefix}_problem_files_list"
        )

        conflicting_files = []

        for service in self.service_names:
            conflicting_files.extend(
                self.policy_manager.get_conflicting_policy_files(
                    service, self.own_file_name
                )
            )

        if conflicting_files:
            self.problem_box.set_visible(True)
            for file in conflicting_files:
                row = ConflictFileListRow(file)
                self.problem_list.add(row)
            self.problem_box.show_all()
        else:
            self.problem_box.set_visible(False)
