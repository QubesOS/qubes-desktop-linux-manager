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
"""Template handling."""
import subprocess
from typing import Optional, List, Dict, Callable
import abc
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.vm
from ..widgets.gtk_widgets import VMListModeler
from ..widgets.gtk_utils import show_error
from .application_selector import ApplicationData

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

logger = logging.getLogger("qubes-new-qube")
WHONIX_QUBE_NAME = "sys-whonix"


class TemplateSelector(abc.ABC):
    """
    Abstract base class for various variants of template/source VM selection.
    """

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        self.qapp = qapp
        self.main_window = gtk_builder.get_object("main_window")

    @abc.abstractmethod
    def set_visible(self, state: bool):
        """
        Used whenever visibility of the widgets should change.
        :param state: bool, True for visible, False for hidden
        :return: None
        """

    @abc.abstractmethod
    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """
        Return which VM (if any) is currently selected.
        :return: None or QubesVM
        """

    @abc.abstractmethod
    def select_vm(self, vm_name: Optional[str]):
        """
        Select a vm given by name (or None, if it's possible).
        :param vm_name: str of vm's name
        :return: None
        """

    def emit_signal(self, widget=None):
        """
        Emit signal signifying template change to the main window widget.
        :param widget: widget emitting the signal
        :return: None
        """
        if widget is None or widget.get_active():
            self.main_window.emit("template-changed", self.get_selected_vm())

    @abc.abstractmethod
    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """


class TemplateSelectorCombo(TemplateSelector):
    """
    Simple combobox selector.
    """

    def __init__(
        self,
        gtk_builder: Gtk.Builder,
        qapp: qubesadmin.Qubes,
        name_suffix: str,
        filter_function: Callable[[qubesadmin.vm.QubesVM], bool],
        default_value: Optional[qubesadmin.vm.QubesVM],
    ):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        :param name_suffix: suffix of the object names, expected names are
        label_template_suffix, label_template_explanation_suffix and
        combo_template_suffix
        :param filter_function: function used to filter available VMs
        :param default_value: optional value to be marked as (default) and
        selected
        """
        super().__init__(gtk_builder, qapp)

        self.label: Gtk.Label = gtk_builder.get_object(
            f"label_template_{name_suffix}"
        )
        self.explain_label: Gtk.Label = gtk_builder.get_object(
            f"label_template_explanation_{name_suffix}"
        )
        self.combo: Gtk.ComboBox = gtk_builder.get_object(
            f"combo_template_{name_suffix}"
        )

        self.modeler = VMListModeler(
            combobox=self.combo,
            qapp=self.qapp,
            filter_function=filter_function,
            default_value=default_value,
        )
        # done separately to avoid recursion problem
        self.modeler.connect_change_callback(self.emit_signal)

    def set_visible(self, state: bool):
        """Change visibility of widgets to state (True-visible, False-hidden)"""
        self.label.set_visible(state)
        self.combo.set_visible(state)
        self.explain_label.set_visible(state)
        if state:
            self.emit_signal(self.combo)

    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get selected QubesVM object"""
        return self.modeler.get_selected()

    def select_vm(self, vm_name: Optional[str]):
        """Select qube provided by name."""
        self.modeler.select_value(vm_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """
        return self.modeler.is_vm_available(vm)


class TemplateSelectorNoneCombo(TemplateSelector):
    """
    Selector for a combination of None/combobox with VMs.
    """

    def __init__(
        self,
        gtk_builder: Gtk.Builder,
        qapp: qubesadmin.Qubes,
        name_suffix: str,
        filter_function: Callable[[qubesadmin.vm.QubesVM], bool],
        default_value: Optional[qubesadmin.vm.QubesVM],
    ):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        :param name_suffix: suffix of the object names
        :param filter_function: function used to filter available VMs
        :param default_value: optional value to be marked as (default) and
        selected
        """
        super().__init__(gtk_builder, qapp)

        self.label: Gtk.Label = gtk_builder.get_object(
            f"label_template_{name_suffix}"
        )
        self.explain_label: Gtk.Label = gtk_builder.get_object(
            f"label_template_explanation_{name_suffix}"
        )
        self.radio_none: Gtk.RadioButton = gtk_builder.get_object(
            f"radio_{name_suffix}_none"
        )
        self.box_template: Gtk.Box = gtk_builder.get_object(
            f"box_radio_{name_suffix}"
        )
        self.radio_template: Gtk.RadioButton = gtk_builder.get_object(
            f"radio_template_{name_suffix}"
        )
        self.combo_template: Gtk.ComboBox = gtk_builder.get_object(
            f"combo_template_{name_suffix}"
        )

        self.modeler = VMListModeler(
            combobox=self.combo_template,
            qapp=self.qapp,
            filter_function=filter_function,
            default_value=default_value,
        )

        self.radio_none.connect("toggled", self.emit_signal)
        self.radio_template.connect("toggled", self._radio_toggled)
        # done separately to avoid infinite recursion
        self.modeler.connect_change_callback(self.emit_signal)
        self.radio_none.set_active(True)

    def _radio_toggled(self, widget: Gtk.RadioButton):
        if widget.get_active():
            self.combo_template.set_sensitive(True)
            self.emit_signal()
        else:
            self.combo_template.set_sensitive(False)

    def set_visible(self, state: bool):
        """Change visibility of widgets to state (True-visible, False-hidden)"""
        self.label.set_visible(state)
        self.explain_label.set_visible(state)
        self.radio_none.set_visible(state)
        self.box_template.set_visible(state)
        if state:
            self.emit_signal(self.combo_template)

    def get_selected_vm(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get selected QubesVM object or None"""
        if self.radio_template.get_active():
            return self.modeler.get_selected()
        return None

    def select_vm(self, vm_name: Optional[str]):
        """Select qube provided by name."""
        if vm_name is None:
            self.radio_none.set_active(True)
            return
        self.radio_template.set_active(True)
        self.modeler.select_value(vm_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """
        Check if the given VM is available in the template list.
        """
        return self.modeler.is_vm_available(vm)


class TemplateHandler:
    """Class to handle a collection of template selectors"""

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: Gtk.Builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.main_window: Gtk.Window = gtk_builder.get_object("main_window")

        self.template_selectors: Dict[str, TemplateSelector] = {
            "qube_type_app": TemplateSelectorCombo(
                gtk_builder=gtk_builder,
                qapp=self.qapp,
                name_suffix="app",
                filter_function=lambda x: x.klass == "TemplateVM",
                default_value=self.qapp.default_template,
            ),
            "qube_type_template": TemplateSelectorNoneCombo(
                gtk_builder=gtk_builder,
                qapp=self.qapp,
                name_suffix="template",
                filter_function=lambda x: x.klass == "TemplateVM",
                default_value=None,
            ),
            "qube_type_standalone": TemplateSelectorNoneCombo(
                gtk_builder=gtk_builder,
                qapp=self.qapp,
                name_suffix="standalone",
                filter_function=lambda x: x.klass
                in ("TemplateVM", "StandaloneVM"),
                default_value=None,
            ),
            "qube_type_disposable": TemplateSelectorCombo(
                gtk_builder=gtk_builder,
                qapp=self.qapp,
                name_suffix="dispvm",
                filter_function=lambda x: getattr(
                    x, "template_for_dispvms", False
                ),
                default_value=self.qapp.default_dispvm,
            ),
        }

        self.selected_type: Optional[str] = None
        self.change_vm_type("qube_type_app")

        self._application_data: Dict[
            qubesadmin.vm.QubesVM, List[ApplicationData]
        ] = {}
        self._default_applications: Dict[qubesadmin.vm.QubesVM, List[str]] = {}

    def change_vm_type(self, vm_type: str):
        """Change selector to one appropriate for the type of VM
        being created"""
        for selector_type, selector in self.template_selectors.items():
            selector.set_visible(selector_type == vm_type)
        self.selected_type = vm_type
        self.main_window.emit("template-changed", self.get_selected_template())

    def get_selected_template(self) -> Optional[qubesadmin.vm.QubesVM]:
        """Get currently selected VM."""
        if self.selected_type:
            return self.template_selectors[self.selected_type].get_selected_vm()
        return None

    def is_given_template_available(
        self, template: qubesadmin.vm.QubesVM
    ) -> bool:
        """Check if given qubesVM is among available templates."""
        if self.selected_type:
            return self.template_selectors[self.selected_type].is_vm_available(
                template
            )
        return False

    def load_all_available_apps(self):
        for vm in self.qapp.domains:
            self.get_available_apps(vm)

    def get_available_apps(self, vm: Optional[qubesadmin.vm.QubesVM] = None):
        """Get apps available for a given template."""
        if vm:
            if vm in self._application_data:
                return self._application_data.get(vm, [])
            command = [
                "qvm-appmenus",
                "--get-available",
                "--i-understand-format-is-unstable",
                "--file-field",
                "Comment",
                vm.name,
            ]
            try:
                available_apps = [
                    ApplicationData.from_line(line, template=vm)
                    for line in subprocess.check_output(command)
                    .decode()
                    .splitlines()
                ]
                self._application_data[vm] = available_apps
            except subprocess.CalledProcessError:
                show_error(
                    self.main_window,
                    _("Failed to load application data"),
                    _("Failed to load application data for ") + vm.name,
                )
                available_apps = []
            return available_apps

        return [
            appdata
            for appdata_list in self._application_data.values()
            for appdata in appdata_list
        ]

    def get_default_apps(self, vm: qubesadmin.vm.QubesVM) -> List[str]:
        """Get list of default apps for a given template"""
        if vm in self._default_applications:
            return self._default_applications.get(vm, [])

        command = ["qvm-appmenus", "--get-default-whitelist", vm.name]
        try:
            default_applications = (
                subprocess.check_output(command).decode().splitlines()
            )
        except subprocess.CalledProcessError:
            show_error(
                self.main_window,
                _("Failed to load application data"),
                _("Failed to load default_applications for ") + vm.name,
            )
            default_applications = []
        self._default_applications[vm] = default_applications
        return default_applications

    def select_template(self, vm: Optional[str]):
        """Selected a vm in the current selector as provided by
        vm name or None"""
        if self.selected_type:
            self.template_selectors[self.selected_type].select_vm(vm)
