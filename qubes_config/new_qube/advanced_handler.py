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
"""Advanced settings handler"""
from typing import Optional, Dict, Any
import logging

import qubesadmin.vm
from ..widgets.gtk_widgets import TextModeler, ExpanderHandler

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

logger = logging.getLogger("qubes-new-qube")
WHONIX_QUBE_NAME = "sys-whonix"


class AdvancedHandler:
    """
    Class that handles advanced configuration.
    """

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp

        self.events: Gtk.Button = gtk_builder.get_object(
            "event_button_advanced"
        )
        self.box: Gtk.Box = gtk_builder.get_object("advanced_box")
        self.expander_icon: Gtk.Image = gtk_builder.get_object(
            "advanced_expander"
        )
        self.expander_label: Gtk.Label = gtk_builder.get_object(
            "advanced_label"
        )

        self.expander_handler = ExpanderHandler(
            event_button=self.events,
            data_container=self.box,
            icon=self.expander_icon,
            label=self.expander_label,
            text_shown=_("Hide advanced settings"),
            text_hidden=_("Show advanced settings"),
        )

        self.main_window: Gtk.Window = gtk_builder.get_object("main_window")

        self.provides_network_check: Gtk.CheckButton = gtk_builder.get_object(
            "advanced_provides_network"
        )
        self.install_system_check: Gtk.CheckButton = gtk_builder.get_object(
            "advanced_install_from_device"
        )
        self.launch_settings_check: Gtk.CheckButton = gtk_builder.get_object(
            "check_launch_settings"
        )

        self.pool: Gtk.ComboBoxText = gtk_builder.get_object(
            "storage_pool_combobox"
        )
        self.initram: Gtk.SpinButton = gtk_builder.get_object(
            "initram_spin_button"
        )

        pools: Dict[str, Any] = {}
        for pool in self.qapp.pools.values():
            if pool == self.qapp.default_pool:
                pools[f"default ({pool})"] = None
            else:
                pools[str(pool)] = str(pool)

        self.pool_handler = TextModeler(self.pool, pools)

        # discuss: max ram?
        self.initram.configure(
            Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100000,
                step_increment=1,
                page_increment=10,
                page_size=100,
            ),
            climb_rate=10,
            digits=0,
        )

        self.initram.connect("output", self._format_initram)

        self.install_system_check.set_sensitive(False)
        self.install_system_check.connect("toggled", self._install_changed)
        self.launch_settings_check.connect("toggled", self._settings_changed)

        self.main_window.connect("template-changed", self._template_changed)

    def _template_changed(self, _widget, vm_name):
        if vm_name is None:
            self.set_install_enabled(True)
        else:
            self.set_install_enabled(False)

    def set_install_enabled(self, state: bool):
        """Allow installing system"""
        self.install_system_check.set_active(state)
        self.install_system_check.set_sensitive(state)

    def _install_changed(self, *_args):
        if self.install_system_check.get_active():
            self.launch_settings_check.set_active(False)

    def _settings_changed(self, *_args):
        if (
            self.launch_settings_check.get_active()
            and self.install_system_check.get_sensitive()
        ):
            self.install_system_check.set_active(False)

    def _format_initram(self, _widget):
        value = self.initram.get_adjustment().get_value()
        if value == 0:
            text = "(default)"
            self.initram.set_text(text)
            return True
        return False

    def get_pool(self) -> Optional[str]:
        """Get selected storage pool"""
        return self.pool_handler.get_selected()

    def get_provides_network(self) -> bool:
        """Does the vm provide network?"""
        return self.provides_network_check.get_active()

    def get_init_ram(self) -> Optional[int]:
        """Get init_ram value, None if left at default."""
        if self.initram.get_value() == 0:
            return None
        return int(self.initram.get_value())

    def get_install_system(self) -> bool:
        """Should 'install system from device' window be shown after
        creation?"""
        return self.install_system_check.get_active()

    def get_launch_settings(self) -> bool:
        """Should settings be launched after creation?"""
        return self.launch_settings_check.get_active()
