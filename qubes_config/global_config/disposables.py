# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2026 Marta Marczykowska-Górecka
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
"""
Disposables page handler
"""
import subprocess
from enum import Enum

import gi

import qubesadmin.vm
import qubesadmin.exc
from ..widgets.gtk_utils import load_icon
from .basics_handler import PropertyHandler
from .page_handler import PageHandler
from .policy_exceptions_handler import DispvmExceptionHandler
from .policy_manager import PolicyManager
from ..widgets.utils import get_feature, apply_feature_change
from ..widgets.gtk_widgets import NONE_CATEGORY, VMListModeler, TokenName

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class DispColumn(Enum):
    NAME = 0
    TEMPLATE = 1
    NETQUBE = 2
    PRELOAD = 3


class DispVMRow(Gtk.ListBoxRow):
    def __init__(
        self,
        dispvm: qubesadmin.vm.QubesVM,
        default_dispvm_model: VMListModeler,
        qubes_app,
        size_groups: dict[DispColumn, Gtk.SizeGroup],
    ):
        """
        A row representing a disposable template
        :param dispvm: relevant vm object
        :param default_dispvm_model: the selector helper for default disposable template
        :param qubes_app: Qubes object
        :param size_groups: list of sizegroups (see DispColumn enum) to ensure table
        looks like a table
        """
        super().__init__()

        self.dispvm = dispvm
        self.size_groups = size_groups
        self.default_dispvm_model = default_dispvm_model
        self.qapp = qubes_app
        self.initial_preload = 0

        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.box.set_spacing(5)
        self.add(self.box)

        self.name_widget = TokenName(self.dispvm.name, self.qapp)
        self.size_groups[DispColumn.NAME].add_widget(self.name_widget)
        self.box.pack_start(self.name_widget, False, True, 0)

        self.based_on = TokenName("", self.qapp)
        self.size_groups[DispColumn.TEMPLATE].add_widget(self.based_on)
        self.box.pack_start(self.based_on, False, True, 0)

        self.netqube = TokenName("", self.qapp)
        self.netqube.set_valign(Gtk.Align.CENTER)
        self.netqube.get_children()[0].set_margin_start(30)
        self.size_groups[DispColumn.NETQUBE].add_widget(self.netqube)
        self.box.pack_start(self.netqube, False, True, 0)

        self.last_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.size_groups[DispColumn.PRELOAD].add_widget(self.last_box)

        self.preload_spin = Gtk.SpinButton()
        self.preload_spin.set_alignment(0.5)
        self.preload_spin.set_vexpand(False)
        self.preload_spin.set_valign(Gtk.Align.CENTER)
        self.preload_spin.props.numeric = True
        self.preload_spin_adj = Gtk.Adjustment()
        self.preload_spin_adj.configure(0, 0, 99, 1, 5, 0)
        self.preload_spin.configure(self.preload_spin_adj, 0.1, 0)

        self.settings_button = Gtk.Button()
        self.settings_button.get_style_context().add_class("flat")
        self.settings_button.get_style_context().add_class("flat_button")
        self.settings_button.get_style_context().add_class("prefs_button")
        icon = Gtk.Image()
        icon.set_from_pixbuf(load_icon("qubes-vm-settings", 14, 14))
        self.settings_button.set_image(icon)
        self.settings_button.connect("clicked", self._launch_settings)

        self.last_box.pack_start(self.preload_spin, False, True, 0)
        self.last_box.pack_start(self.settings_button, False, True, 0)
        self.box.pack_start(self.last_box, False, True, 0)

        self.load_data()

    def load_data(self):
        if not self.dispvm.template_for_dispvms:
            self.get_parent().remove(self)
            return

        self.name_widget.set_token(str(self.dispvm.name))
        self.based_on.set_token(str(self.dispvm.template))
        self.netqube.set_token(str(self.dispvm.netvm))

        preload = self.dispvm.features.get("preload-dispvm-max", 0)

        if preload:
            self.initial_preload = int(preload)
        else:
            self.initial_preload = 0
        self.preload_spin.set_value(self.initial_preload)

        self.set_default_dispvm(self.default_dispvm_model.get_selected())

    def _launch_settings(self, *_args):
        """This is blocking by design."""
        subprocess.check_call(["qubes-vm-settings", self.dispvm.name])
        try:
            self.dispvm.clear_cache()  # qubes-vm-settings uses its own qapp,
            # so this is needed
            self.load_data()
        except qubesadmin.exc.QubesVMNotFoundError:
            # this VM was deleted
            self.get_parent().remove(self)

    def set_default_dispvm(self, default_dispvm_name: qubesadmin.vm.QubesVM):
        is_default = default_dispvm_name == self.dispvm

        if is_default:
            self.get_style_context().add_class("default_dvm_row")
            self.preload_spin.set_sensitive(False)
            self.preload_spin.set_tooltip_text(
                "Default disposable template uses the value configured below"
            )
        else:
            self.get_style_context().remove_class("default_dvm_row")
            self.preload_spin.set_sensitive(True)
            self.preload_spin.set_tooltip_text("")

    def save_changes(self):
        if self.preload_spin.get_value_as_int() != self.initial_preload:
            self.dispvm.features["preload-dispvm-max"] = (
                self.preload_spin.get_value_as_int()
            )
            self.initial_preload = self.preload_spin.get_value_as_int()


class DispVmListHandler(PageHandler):
    """Handler for the list of disposable templates"""

    def __init__(
        self, qapp: qubesadmin.Qubes, dispvm_model: VMListModeler, builder: Gtk.Builder
    ):
        self.qapp = qapp
        self.dispvm_model = dispvm_model

        self.vm_list: Gtk.ListBox = builder.get_object("disp_template_list")
        self.add_vm_button = builder.get_object("disp_add_vm_button")

        self.size_groups = {}
        for col in DispColumn:
            grp = Gtk.SizeGroup()
            grp.add_widget(builder.get_object(f"disp_group_{col.value}"))
            grp.set_mode(Gtk.SizeGroupMode.HORIZONTAL)
            self.size_groups[col] = grp

        self.load_data()

        self.dispvm_model.connect_change_callback(self._default_dvm_changed)
        self.add_vm_button.connect("clicked", self._add_new_dvm_template)

    def _default_dvm_changed(self):
        new_def_dvm = self.dispvm_model.get_selected()
        for row in self.vm_list.get_children():
            if isinstance(row, DispVMRow):
                row.set_default_dispvm(new_def_dvm)

    def _add_new_dvm_template(self, *_args):
        # this is blocking by design
        subprocess.check_call(["qubes-new-qube", "--open-at", "disposable-template"])
        # needed
        self.qapp.domains.clear_cache()
        self.load_data()

    def load_data(self):
        for child in self.vm_list.get_children():
            if isinstance(child, DispVMRow):
                self.vm_list.remove(child)

        vms = [
            vm for vm in self.qapp.domains if getattr(vm, "template_for_dispvms", False)
        ]
        vms.sort(key=lambda x: x.name.lower())

        for vm in vms:
            new_row = DispVMRow(vm, self.dispvm_model, self.qapp, self.size_groups)
            self.vm_list.add(new_row)

        self.vm_list.show_all()

    def save(self):
        for row in self.vm_list.get_children():
            if isinstance(row, DispVMRow):
                row.save_changes()

    def reset(self):
        for row in self.vm_list.get_children():
            if isinstance(row, DispVMRow):
                row.preload_spin.set_value(row.initial_preload)

    def get_unsaved(self) -> str:
        results = []
        for row in self.vm_list.get_children():
            if isinstance(row, DispVMRow):
                if row.initial_preload != row.preload_spin.get_value_as_int():
                    results.append("preloading for {}".format(row.dispvm.name))
        return ",".join(results)


class PreloadDispvmHandler(PageHandler):
    """Preloading settings handler.
    Requires:
    - SpinButton disp_preload_dispvm
    - CheckButton disp_preload_dispvm_check
    - SpinButton disp_preload_dispvm_threshold
    """

    MAX_PRELOAD_FEATURE = "preload-dispvm-max"
    MAX_THRESHOLD_FEATURE = "preload-dispvm-threshold"
    DEFAULT_MAX = 1

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
        defdispvm_model: VMListModeler,
    ):
        self.qapp = qapp
        self.defdispvm_model = defdispvm_model
        self.preload_dispvm_spin: Gtk.SpinButton = gtk_builder.get_object(
            "disp_preload_dispvm"
        )
        self.preload_dispvm_threshold_spin: Gtk.SpinButton = gtk_builder.get_object(
            "disp_preload_dispvm_threshold"
        )
        self.preload_dispvm_check: Gtk.CheckButton = gtk_builder.get_object(
            "disp_preload_dispvm_check"
        )

        self.initial_preload_state = False
        self.initial_preload_number = 0
        self.initial_threshold = 0

        self.load_data()

        self.defdispvm_model.connect_change_callback(self.on_defdispvm_changed)
        self.preload_dispvm_check.connect("toggled", self.on_check_changed)

        self.on_defdispvm_changed()
        self.on_check_changed()

    def load_data(self):
        # get value of the preload feature
        preload_val = get_feature(self.qapp.domains["dom0"], self.MAX_PRELOAD_FEATURE)

        if preload_val == "" or preload_val is None:
            self.preload_dispvm_check.set_active(False)
            self.preload_dispvm_spin.set_value(0)
            self.preload_dispvm_spin.set_sensitive(False)
            self.initial_preload_state = False
            self.initial_preload_number = 0
        else:
            preload_val_int = int(preload_val)
            self.preload_dispvm_check.set_active(True)
            self.preload_dispvm_spin.set_value(preload_val_int)
            self.preload_dispvm_spin.set_sensitive(True)
            self.initial_preload_state = True
            self.initial_preload_number = preload_val_int

        threshold_val = int(
            get_feature(self.qapp.domains["dom0"], self.MAX_THRESHOLD_FEATURE) or 0
        )
        self.initial_threshold = threshold_val
        self.preload_dispvm_threshold_spin.set_value(threshold_val)

    def on_defdispvm_changed(self):
        defdispvm = self.defdispvm_model.get_selected()
        if defdispvm:
            self.preload_dispvm_check.set_sensitive(True)
            self.preload_dispvm_threshold_spin.set_sensitive(True)
        else:
            self.preload_dispvm_check.set_sensitive(False)
            self.preload_dispvm_threshold_spin.set_sensitive(False)

    def on_check_changed(self, *_args):
        if self.preload_dispvm_check.get_active():
            self.preload_dispvm_spin.set_sensitive(True)
            if self.preload_dispvm_spin.get_value_as_int() == 0:
                self.preload_dispvm_spin.set_value(self.DEFAULT_MAX)
        else:
            self.preload_dispvm_spin.set_sensitive(False)

    @staticmethod
    def get_readable_description() -> str:  # pylint: disable=arguments-differ
        """Get human-readable description of the widget"""
        return _("Preloading from default disposable template")

    def is_changed(self) -> bool:
        """Has the user selected something different from the initial value?"""
        if self.preload_dispvm_check.get_active() != self.initial_preload_state:
            return True
        if self.preload_dispvm_spin.get_value_as_int() != self.initial_preload_number:
            return True
        if (
            self.preload_dispvm_threshold_spin.get_value_as_int()
            != self.initial_threshold
        ):
            return True
        return False

    def get_unsaved(self):
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.is_changed():
            return self.get_readable_description()
        return ""

    def save(self):
        """Save changes: update system value and mark it as new initial value"""
        if not self.is_changed():
            return

        if (
            self.preload_dispvm_threshold_spin.get_value_as_int()
            != self.initial_threshold
        ):
            threshold_value = str(self.preload_dispvm_threshold_spin.get_value_as_int())
            apply_feature_change(
                self.qapp.domains["dom0"],
                self.MAX_THRESHOLD_FEATURE,
                threshold_value,
            )
            self.initial_threshold = (
                self.preload_dispvm_threshold_spin.get_value_as_int()
            )

        if (
            self.preload_dispvm_check.get_active() != self.initial_preload_state
            or self.preload_dispvm_spin.get_value_as_int()
            != self.initial_preload_number
        ):
            if self.preload_dispvm_check.get_active():
                value = str(self.preload_dispvm_spin.get_value_as_int())
            else:
                value = None
            apply_feature_change(
                self.qapp.domains["dom0"],
                self.MAX_PRELOAD_FEATURE,
                value,
            )
            self.initial_preload_state = self.preload_dispvm_check.get_active()
            self.initial_preload_number = self.preload_dispvm_spin.get_value_as_int()

    def reset(self):
        """Reset selection to the initial value."""
        self.preload_dispvm_check.set_active(self.initial_preload_state)
        self.preload_dispvm_spin.set_sensitive(self.initial_preload_state)
        self.preload_dispvm_spin.set_value(self.initial_preload_number)
        self.preload_dispvm_threshold_spin.set_value(self.initial_threshold)


class DisposablesHandler(PageHandler):
    """Handler for all the disparate Disposables functions."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        gtk_builder: Gtk.Builder,
    ):
        """
        :param qapp: Qubes object
        :param policy_manager: PolicyManager object
        :param gtk_builder: Gtk.Builder for all the stuff we have
        """

        self.qapp = qapp
        self.policy_manager = policy_manager

        self.defdispvm_combo: Gtk.ComboBox = gtk_builder.get_object(
            "disp_defdispvm_combo"
        )
        self.defdispvm_handler = PropertyHandler(
            qapp=self.qapp,
            trait_holder=self.qapp,
            trait_name="default_dispvm",
            widget=self.defdispvm_combo,
            vm_filter=self._default_dispvm_filter,
            readable_name=_("Default disposable qube template"),
            additional_options=NONE_CATEGORY,
        )

        self.preload_handler = PreloadDispvmHandler(
            self.qapp, gtk_builder, self.defdispvm_handler.get_model()
        )

        self.dispvm_list_handler = DispVmListHandler(
            self.qapp, self.defdispvm_handler.get_model(), gtk_builder
        )

        self.open_in_dvm_handler = DispvmExceptionHandler(
            gtk_builder=gtk_builder,
            qapp=self.qapp,
            service_name="qubes.OpenInVM",
            policy_file_name="50-config-openinvm",
            prefix="openinvm",
            policy_manager=self.policy_manager,
        )
        self.openurl_handler = DispvmExceptionHandler(
            gtk_builder=gtk_builder,
            qapp=self.qapp,
            service_name="qubes.OpenURL",
            policy_file_name="50-config-openurl",
            prefix="url",
            policy_manager=self.policy_manager,
        )
        self.handlers: list[PageHandler | PropertyHandler] = [
            self.defdispvm_handler,
            self.preload_handler,
            self.dispvm_list_handler,
            self.openurl_handler,
            self.open_in_dvm_handler,
        ]

    @staticmethod
    def _default_dispvm_filter(vm) -> bool:
        return getattr(vm, "template_for_dispvms", False)

    def get_unsaved(self) -> str:
        """Get list of unsaved changes."""
        unsaved = []
        for handler in self.handlers:
            changes = handler.get_unsaved()
            if changes:
                unsaved.append(changes)

        return "\n".join(unsaved)

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        for handler in self.handlers:
            handler.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""

        for handler in self.handlers:
            handler.save()
