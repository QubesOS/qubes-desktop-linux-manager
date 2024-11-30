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
"""Network selection"""
from typing import Optional
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm
from ..widgets.gtk_widgets import QubeName, VMListModeler, ExpanderHandler

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

logger = logging.getLogger("qubes-new-qube")
WHONIX_QUBE_NAME = "sys-whonix"


class NetworkSelector:
    """
    Class that handles network configuration.
    """

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp

        self.network_default_icon: Optional[Gtk.Image] = None
        self.network_default_name: Optional[Gtk.Label] = None
        self.network_tor_icon: Optional[Gtk.Image] = None
        self.network_tor_name: Optional[Gtk.Label] = None

        self.network_default_box: Gtk.Box = gtk_builder.get_object(
            "network_default_box"
        )
        self.network_default_box.pack_start(
            QubeName(self.qapp.default_netvm), False, False, 0
        )

        self.network_tor_box: Gtk.Box = gtk_builder.get_object(
            "network_tor_box"
        )
        self.network_custom: Gtk.RadioButton = gtk_builder.get_object(
            "network_custom"
        )
        self.network_custom_combo: Gtk.ComboBox = gtk_builder.get_object(
            "network_custom_combo"
        )
        self.network_custom.connect("toggled", self._custom_toggled)

        self.network_none: Gtk.RadioButton = gtk_builder.get_object(
            "network_none"
        )
        self.network_tor: Gtk.RadioButton = gtk_builder.get_object(
            "network_tor"
        )
        self.network_default: Gtk.RadioButton = gtk_builder.get_object(
            "network_default"
        )

        if WHONIX_QUBE_NAME in self.qapp.domains:
            self.network_tor_box.pack_start(
                QubeName(self.qapp.domains[WHONIX_QUBE_NAME]), False, False, 0
            )
        else:
            self.network_tor_box.set_visible(False)
            self.network_tor_box.set_no_show_all(True)

        self.network_modeler = VMListModeler(
            self.network_custom_combo,
            self.qapp,
            lambda x: getattr(x, "provides_network", False),
        )

        self.network_tor.connect("toggled", self._netvm_changed)
        self.network_none.connect("toggled", self._netvm_changed)
        self.network_default.connect("toggled", self._netvm_changed)
        self.network_custom.connect("toggled", self._netvm_changed)
        self.network_custom_combo.connect("changed", self._netvm_changed_combo)

        self.network_current_box: Gtk.Box = gtk_builder.get_object(
            "box_network_current"
        )
        self.network_current_none: Gtk.Label = gtk_builder.get_object(
            "label_current_network_none"
        )
        self.network_current_widget = QubeName(self.qapp.default_netvm)
        self.network_current_box.pack_start(
            self.network_current_widget, False, False, 3
        )
        self.network_current_none.set_visible(False)

        self.button_toggle_settings: Gtk.Button = gtk_builder.get_object(
            "event_button_network_current"
        )
        self.box_network_settings: Gtk.Box = gtk_builder.get_object(
            "box_network_settings"
        )
        self.expander_image: Gtk.Image = gtk_builder.get_object(
            "network_settings_expander_icon"
        )

        self.expander_handler = ExpanderHandler(
            event_button=self.button_toggle_settings,
            data_container=self.box_network_settings,
            icon=self.expander_image,
        )

    def _custom_toggled(self, widget):
        self.network_custom_combo.set_sensitive(widget.get_active())

    def _netvm_changed_combo(self, _widget):
        self._netvm_changed(None)

    def _netvm_changed(self, widget: Optional[Gtk.RadioButton]):
        if widget and not widget.get_active():
            # do not perform this twice for every change of netvm
            return
        current_netvm = self.get_selected_netvm()
        self.network_current_none.set_visible(current_netvm is None)
        self.network_current_box.remove(self.network_current_widget)

        if current_netvm == qubesadmin.DEFAULT:
            current_netvm = self.qapp.default_netvm

        if current_netvm:
            self.network_current_widget = QubeName(current_netvm)
            self.network_current_box.pack_start(
                self.network_current_widget, False, False, 3
            )

    def get_selected_netvm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get which vm (if any) is selected as netvm"""
        if self.network_none.get_active():
            return None
        if self.network_tor.get_active():
            return self.qapp.domains[WHONIX_QUBE_NAME]
        if self.network_custom.get_active():
            tree_iter = self.network_custom_combo.get_active_iter()
            if tree_iter is not None:
                model = self.network_custom_combo.get_model()
                netvm = self.qapp.domains[model[tree_iter][1]]
                return netvm
        return qubesadmin.DEFAULT
