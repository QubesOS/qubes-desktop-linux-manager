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
"""
USB Devices-related functionality.
"""
from functools import partial
from typing import List, Union, Optional, Dict, Tuple, Set

from qrexec.policy.parser import Allow
from qubesadmin.device_protocol import DeviceCategory

from ..widgets.gtk_widgets import TokenName, TextModeler, VMListModeler
from ..widgets.utils import get_feature, apply_feature_change
from ..widgets.gtk_utils import ask_question, show_error
from .page_handler import PageHandler
from .policy_rules import RuleTargetedAdminVM, Rule
from .policy_manager import PolicyManager
from .policy_handler import ErrorHandler
from .vm_flowbox import VMFlowboxHandler
from .conflict_handler import ConflictFileHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class InputActionWidget(Gtk.Box):
    """A simple widget for a combobox for policy actions."""

    def __init__(
        self, rule: RuleTargetedAdminVM, action_choices: Dict[str, str]
    ):
        """
        :param rule: wrapped policy rule
        :param action_choices: Dictionary of "nice rule name": "actual action"
        """
        super().__init__()
        self.rule = rule
        self.service = rule.raw_rule.service
        self.combobox = Gtk.ComboBoxText()
        self.model = TextModeler(
            combobox=self.combobox,
            values=action_choices,
            selected_value=self.rule.action,
            style_changes=True,
        )
        self.add(self.combobox)
        self.show_all()

    def is_changed(self):
        """Was the widget changed?"""
        return self.model.is_changed()

    def reset(self):
        """Reset widget state to before changes."""
        self.model.reset()

    def update_changed(self):
        """Mark any changes in the widget as saved."""
        self.model.update_initial()


class InputDeviceHandler:
    """Handler for various qubes.Input policies."""

    ACTION_CHOICES = {
        _("always ask"): "ask",
        _("enable"): "allow",
        _("disable"): "deny",
    }

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        gtk_builder: Gtk.Builder,
        usb_qubes: Set[qubesadmin.vm.QubesVM],
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_file_name = "50-config-input"

        self.warn_box = gtk_builder.get_object("usb_input_problem_box_warn")
        self.warn_label: Gtk.Label = gtk_builder.get_object(
            "usb_input_problem_warn_label"
        )
        self.warn_box.set_visible(False)

        self.policy_grid: Gtk.Grid = gtk_builder.get_object("usb_input_grid")

        self.default_policy = ""

        self.usb_qubes = usb_qubes

        self.rules: List[Rule] = []
        self.current_token: Optional[str] = None

        # widgets indexed via tuples: service_name, usb-qube-name
        self.widgets: Dict[Tuple[str, str], InputActionWidget] = {}

        self.policy_order = [
            "qubes.InputKeyboard",
            "qubes.InputMouse",
            "qubes.InputTablet",
        ]

        self.load_rules()

        self.conflict_file_handler = ConflictFileHandler(
            gtk_builder=gtk_builder,
            prefix="usb_input",
            service_names=self.policy_order,
            own_file_name=self.policy_file_name,
            policy_manager=self.policy_manager,
        )

    def load_rules(self):
        self.default_policy = ""

        if not self.usb_qubes:
            self._warn(
                "No USB qubes found: to apply policy to USB input "
                "devices, connect your USB controller to a "
                "dedicated USB qube."
            )
            return

        for vm in self.usb_qubes:
            self.default_policy += f"""
qubes.InputMouse * {vm.name} @adminvm deny
qubes.InputKeyboard * {vm.name} @adminvm deny
qubes.InputTablet * {vm.name} @adminvm deny"""

        for col_num, vm in enumerate(self.usb_qubes):
            self.policy_grid.attach(
                TokenName(vm.name, self.qapp), 1 + col_num, 0, 1, 1
            )

        self.rules, self.current_token = (
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, self.default_policy
            )
        )

        for rule in self.rules:
            try:
                wrapped_rule = RuleTargetedAdminVM(rule)
            except ValueError:
                self._warn("Unexpected policy rule: " + str(rule))
                continue
            if wrapped_rule.source not in self.usb_qubes:
                # non-fatal
                self._warn("Unexpected policy rule: " + str(rule))
            designation = (rule.service, str(wrapped_rule.source))
            if designation in self.widgets:
                self._warn("Unexpected policy rules")
                continue
            self.widgets[designation] = InputActionWidget(
                wrapped_rule, self.ACTION_CHOICES
            )

        for service in self.policy_order:
            for vm in self.usb_qubes:
                if (service, vm.name) not in self.widgets:
                    rule = self.policy_manager.text_to_rules(
                        f"{service} * {vm.name} @adminvm deny"
                    )[0]
                    self.widgets[(service, vm.name)] = InputActionWidget(
                        RuleTargetedAdminVM(rule), self.ACTION_CHOICES
                    )

        for row_num, service in enumerate(self.policy_order):
            for col_num, vm in enumerate(self.usb_qubes):
                self.policy_grid.attach(
                    self.widgets[(service, vm.name)],
                    1 + col_num,
                    1 + row_num,
                    1,
                    1,
                )

        self.policy_grid.show_all()

    def _warn(self, error_descr: str):
        self.warn_label.set_text(
            self.warn_label.get_text() + "\n" + error_descr
        )
        self.warn_box.set_visible(True)

    def save(self):
        """Save user changes"""
        rules = []
        if not self.widgets:
            # no point in changing anything, there are no USB qubes
            return
        for widget in self.widgets.values():
            widget.rule.action = widget.model.get_selected()
            rules.append(widget.rule.raw_rule)

        self.policy_manager.save_rules(
            self.policy_file_name, rules, self.current_token
        )
        _r, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, self.default_policy
        )

        for widget in self.widgets.values():
            widget.update_changed()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = []
        for widget in self.widgets.values():
            if widget.is_changed():
                name = widget.service[len("qubes.Input") :]
                unsaved.append(_("{name} input settings").format(name=name))
        return "\n".join(unsaved)

    def reset(self):
        """Reset changes to the initial state."""
        for widget in self.widgets.values():
            widget.reset()
        self.warn_label.set_text("Unexpected policy file contents:")


class U2FPolicyHandler:
    """Handler for u2f policy and services."""

    SERVICE_FEATURE = "service.qubes-u2f-proxy"
    SUPPORTED_SERVICE_FEATURE = "supported-service.qubes-u2f-proxy"
    AUTH_POLICY = "u2f.Authenticate"
    REGISTER_POLICY = "u2f.Register"
    POLICY_REGISTER_POLICY = "policy.RegisterArgument"

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        gtk_builder: Gtk.Builder,
        usb_qubes: Set[qubesadmin.vm.QubesVM],
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_filename = "50-config-u2f"
        self.usb_qubes = usb_qubes

        self.default_policy = ""
        self.deny_all_policy = """
u2f.Authenticate * @anyvm @anyvm deny
u2f.Register * @anyvm @anyvm deny
policy.RegisterArgument +u2f.Register @anyvm @anyvm deny
"""

        self.problem_fatal_box: Gtk.Box = gtk_builder.get_object(
            "usb_u2f_fatal_problem"
        )
        self.problem_fatal_label: Gtk.Label = gtk_builder.get_object(
            "usb_u2f_fatal_problem_label"
        )

        self.enable_check: Gtk.CheckButton = gtk_builder.get_object(
            "usb_u2f_enable_check"
        )  # general enable
        self.box: Gtk.Box = gtk_builder.get_object(
            "usb_u2f_enable_box"
        )  # general box

        self.register_check: Gtk.CheckButton = gtk_builder.get_object(
            "usb_u2f_register_check"
        )
        self.register_box: Gtk.Box = gtk_builder.get_object(
            "usb_u2f_register_box"
        )
        self.register_all_radio: Gtk.RadioButton = gtk_builder.get_object(
            "usb_u2f_register_all_radio"
        )
        self.register_some_radio: Gtk.RadioButton = gtk_builder.get_object(
            "usb_u2f_register_some_radio"
        )

        self.blanket_check: Gtk.CheckButton = gtk_builder.get_object(
            "usb_u2f_blanket_check"
        )

        self.usb_qube_combo: Gtk.ComboBox = gtk_builder.get_object(
            "u2f_usb_combo"
        )

        self.initially_enabled_vms: List[qubesadmin.vm.QubesVM] = []
        self.available_vms: List[qubesadmin.vm.QubesVM] = []
        self.initial_register_vms: List[qubesadmin.vm.QubesVM] = []
        self.initial_blanket_vms: List[qubesadmin.vm.QubesVM] = []
        self.allow_all_register: bool = False
        self.current_token: Optional[str] = None
        self.rules: List[Rule] = []
        self.usb_qube_model: Optional[VMListModeler] = None

        self.error_handler = ErrorHandler(gtk_builder, "usb_u2f")

        self._initialize_data()

        self.enable_some_handler = VMFlowboxHandler(
            gtk_builder,
            self.qapp,
            "usb_u2f_enable_some",
            self.initially_enabled_vms,
            lambda vm: vm in self.available_vms,
        )

        self.register_some_handler = VMFlowboxHandler(
            gtk_builder,
            self.qapp,
            "usb_u2f_register_some",
            self.initial_register_vms,
            lambda vm: vm in self.available_vms,
            verification_callback=self._verify_additional_vm,
        )

        self.blanket_handler = VMFlowboxHandler(
            gtk_builder,
            self.qapp,
            "usb_u2f_blanket",
            self.initial_blanket_vms,
            lambda vm: vm in self.available_vms,
            verification_callback=self._verify_additional_vm,
        )

        self.widget_to_box = {
            self.enable_check: self.box,
            self.register_check: self.register_box,
            self.blanket_check: self.blanket_handler,
            self.register_some_radio: self.register_some_handler,
        }

        for widget, box in self.widget_to_box.items():
            widget.connect("toggled", partial(self._enable_clicked, box))
            self._enable_clicked(box, widget)

        self.initial_enable_state: bool = self.enable_check.get_active()
        self.initial_register_state: bool = self.register_check.get_active()
        self.initial_register_all_state: bool = (
            self.register_all_radio.get_active()
        )
        self.initial_blanket_check_state: bool = self.blanket_check.get_active()

        self.conflict_file_handler = ConflictFileHandler(
            gtk_builder=gtk_builder,
            prefix="usb_u2f",
            service_names=[
                self.REGISTER_POLICY,
                self.POLICY_REGISTER_POLICY,
                self.AUTH_POLICY,
            ],
            own_file_name=self.policy_filename,
            policy_manager=self.policy_manager,
        )

        if self.usb_qube_model:
            self.usb_qube_model.connect_change_callback(
                self.load_rules_for_usb_qube
            )

    @staticmethod
    def _enable_clicked(
        related_box: Union[Gtk.Box, VMFlowboxHandler], widget: Gtk.CheckButton
    ):
        related_box.set_visible(widget.get_active())

    def _verify_additional_vm(self, vm):
        if vm in self.enable_some_handler.selected_vms:
            return True
        response = ask_question(
            self.enable_check,
            _("U2F not enabled in qube"),
            _("U2F is not enabled in this qube. Do you want to enable it?"),
        )
        if response == Gtk.ResponseType.YES:
            self.enable_some_handler.add_selected_vm(vm)
            return True
        return False

    def _initialize_data(self):
        self.problem_fatal_box.set_visible(False)

        # guess at the current sys-usb
        self.rules, self.current_token = (
            self.policy_manager.get_rules_from_filename(
                self.policy_filename, self.default_policy
            )
        )

        if not self.usb_qubes:
            self.disable_u2f(
                "No USB qubes found. To use U2F Proxy, you have to"
                "connect your USB controller to a qube."
            )
            return

        usb_qube_candidates = set()
        for qube in self.usb_qubes:
            if qube.features.check_with_template(
                self.SUPPORTED_SERVICE_FEATURE
            ):
                usb_qube_candidates.add(qube)

        self.usb_qubes = usb_qube_candidates

        self.usb_qube_model = VMListModeler(
            combobox=self.usb_qube_combo,
            qapp=self.qapp,
            filter_function=lambda vm: vm in self.usb_qubes,
            style_changes=True,
        )

        if not usb_qube_candidates:
            self.disable_u2f(
                "The Qubes U2F Proxy service is not installed in the USB qube. "
                "If you wish to use this service, install the "
                "<tt>qubes-u2f</tt> package in the template on which "
                "the USB qube is based."
            )
            return

        policy_candidates = set()
        for rule in self.rules:
            try:
                policy_candidates.add(self.qapp.domains[rule.target])
            except KeyError:
                continue

        sys_usb = None

        if not policy_candidates:
            sys_usb = next(iter(self.usb_qubes))
        else:
            # just grab one
            sys_usb = policy_candidates.pop()

        while sys_usb not in usb_qube_candidates and policy_candidates:
            sys_usb = policy_candidates.pop()

        if not sys_usb:
            sys_usb = usb_qube_candidates.pop()

        self.usb_qube_model.select_value(sys_usb)
        self.usb_qube_model.update_initial()

        self.load_rules_for_usb_qube()

    def load_rules_for_usb_qube(self):
        """Reload rules for select usb qube"""
        if not self.usb_qube_model:
            return
        usb_qube = self.usb_qube_model.get_selected()
        self.allow_all_register = False
        self.initially_enabled_vms.clear()
        self.available_vms.clear()
        self.initial_register_vms.clear()
        self.initial_blanket_vms.clear()

        self.error_handler.clear_all_errors()

        for vm in self.qapp.domains:
            if vm.features.check_with_template(self.SUPPORTED_SERVICE_FEATURE):
                if vm == usb_qube:
                    continue
                self.available_vms.append(vm)
            if get_feature(vm, self.SERVICE_FEATURE):
                if vm == usb_qube:
                    continue
                self.initially_enabled_vms.append(vm)

        if not self.available_vms:
            self.disable_u2f(
                "No qubes with the U2F Proxy service found. If you wish to "
                "use this service, install the <tt>qubes-u2f</tt> package in "
                "the template on which the USB qube is based."
            )
            return

        self.enable_check.set_active(bool(self.initially_enabled_vms))
        for rule in self.rules:
            if rule.target not in [str(usb_qube), "@anyvm"]:
                self.error_handler.add_error(rule)
                continue
            if rule.service == self.REGISTER_POLICY:
                if rule.argument is not None:
                    self.error_handler.add_error(rule)
                    continue
                if rule.source == "@anyvm" and isinstance(rule.action, Allow):
                    self.allow_all_register = True
                elif rule.source != "@anyvm" and isinstance(rule.action, Allow):
                    try:
                        vm = self.qapp.domains[rule.source]
                        self.initial_register_vms.append(vm)
                    except KeyError:
                        self.error_handler.add_error(rule)
                        continue
            elif rule.service == self.AUTH_POLICY:
                if rule.argument is not None:
                    self.error_handler.add_error(rule)
                    continue
                if rule.source != "@anyvm" and isinstance(rule.action, Allow):
                    try:
                        vm = self.qapp.domains[rule.source]
                        self.initial_blanket_vms.append(vm)
                    except KeyError:
                        self.error_handler.add_error(rule)
                        continue
            elif rule.service != self.POLICY_REGISTER_POLICY:
                self.error_handler.add_error(rule)
                continue

        if self.allow_all_register:
            self.register_check.set_active(True)
            self.register_all_radio.set_active(True)
        else:
            if self.initial_register_vms:
                self.register_check.set_active(True)
                self.register_some_radio.set_active(True)
            else:
                self.register_check.set_active(False)

        self.blanket_check.set_active(bool(self.initial_blanket_vms))

    def disable_u2f(self, reason: str):
        self.problem_fatal_box.set_visible(True)
        self.problem_fatal_box.show_all()
        self.problem_fatal_label.set_markup(reason)
        self.enable_check.set_active(False)
        self.enable_check.set_sensitive(False)
        self.box.set_visible(False)
        self.usb_qube_combo.set_active(False)

    def save(self):
        """Save user changes in policy."""
        if not self.enable_check.get_sensitive():
            return
        if not self.get_unsaved():
            return

        if not self.enable_check.get_active():
            # disable all service:
            for vm in self.initially_enabled_vms:
                apply_feature_change(vm, self.SERVICE_FEATURE, None)

            self.policy_manager.save_rules(
                self.policy_filename,
                self.policy_manager.text_to_rules(self.deny_all_policy),
                self.current_token,
            )

            self._initialize_data()
            return

        enabled_vms = self.enable_some_handler.selected_vms
        if not enabled_vms:
            show_error(
                self.box.get_toplevel(),
                _("Incorrect configuration found"),
                _(
                    "U2F is enabled, but not qubes are selected to be "
                    "used with U2F. This is equivalent to disabling U2F "
                    "and will be treated as such."
                ),
            )

        for vm in self.available_vms:
            value = None if vm not in enabled_vms else True
            apply_feature_change(vm, self.SERVICE_FEATURE, value)

        rules = []

        if not self.usb_qube_model:
            return
        sys_usb = self.usb_qube_model.get_selected()
        self.usb_qube_model.update_initial()

        # register rules
        if not self.register_check.get_active():
            rules.append(
                self.policy_manager.new_rule(
                    service=self.REGISTER_POLICY,
                    source="@anyvm",
                    target="@anyvm",
                    action="deny",
                )
            )
            rules.append(
                self.policy_manager.new_rule(
                    service=self.POLICY_REGISTER_POLICY,
                    argument=f"+{self.AUTH_POLICY}",
                    source="@anyvm",
                    target="@anyvm",
                    action="deny",
                )
            )
        else:
            if self.register_all_radio.get_active():
                rules.append(
                    self.policy_manager.new_rule(
                        service=self.POLICY_REGISTER_POLICY,
                        argument=f"+{self.AUTH_POLICY}",
                        source=str(sys_usb),
                        target="@anyvm",
                        action="allow target=dom0",
                    )
                )
                rules.append(
                    self.policy_manager.new_rule(
                        service=self.REGISTER_POLICY,
                        source="@anyvm",
                        target=str(sys_usb),
                        action="allow",
                    )
                )
            else:
                for vm in self.register_some_handler.selected_vms:
                    rules.append(
                        self.policy_manager.new_rule(
                            service=self.REGISTER_POLICY,
                            source=str(vm),
                            target=str(sys_usb),
                            action="allow",
                        )
                    )
                rules.append(
                    self.policy_manager.new_rule(
                        service=self.POLICY_REGISTER_POLICY,
                        argument=f"+{self.AUTH_POLICY}",
                        source=str(sys_usb),
                        target="@anyvm",
                        action="allow target=dom0",
                    )
                )

        if self.blanket_check.get_active():
            for vm in self.blanket_handler.selected_vms:
                rules.append(
                    self.policy_manager.new_rule(
                        service=self.AUTH_POLICY,
                        source=str(vm),
                        target=str(sys_usb),
                        action="allow",
                    )
                )

        self.policy_manager.save_rules(
            self.policy_filename, rules, self.current_token
        )
        self._initialize_data()

    def reset(self):
        """Reset state to initial state."""
        self.enable_check.set_active(self.initial_enable_state)
        self.register_check.set_active(self.initial_register_state)
        self.blanket_check.set_active(self.initial_blanket_check_state)
        self.register_all_radio.set_active(self.initial_register_all_state)
        self.enable_some_handler.reset()
        self.register_some_handler.reset()
        self.blanket_handler.reset()
        if self.usb_qube_model:
            self.usb_qube_model.reset()

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.initial_enable_state != self.enable_check.get_active():
            if self.enable_check.get_active():
                return _("U2F enabled")
            return _("U2F disabled")
        if not self.enable_check.get_active():
            return ""

        unsaved = []

        if self.usb_qube_model and self.usb_qube_model.is_changed():
            unsaved.append(_("USB qube for U2F Proxy changed"))

        if self.enable_some_handler.selected_vms != self.initially_enabled_vms:
            unsaved.append(_("List of qubes with U2F enabled changed"))

        if self.initial_register_state != self.register_check.get_active():
            unsaved.append(_("U2F key registration settings changed"))
        elif (
            self.initial_register_all_state
            != self.register_all_radio.get_active()
        ):
            unsaved.append(_("U2F key registration settings changed"))
        elif (
            self.register_some_handler.selected_vms != self.initial_register_vms
        ):
            unsaved.append(_("U2F key registration settings changed"))

        if (
            self.initial_blanket_check_state != self.blanket_check.get_active()
            or self.blanket_handler.selected_vms != self.initial_blanket_vms
        ):
            unsaved.append(
                _("List of qubes with unrestricted U2F key access changed")
            )
        return "\n".join(unsaved)


class DevicesHandler(PageHandler):
    """Handler for all the disparate Updates functions."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        gtk_builder: Gtk.Builder,
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.main_window = gtk_builder.get_object("main_window")

        usb_qubes: Set[qubesadmin.vm.QubesVM] = set()

        for vm in self.qapp.domains:
            for assignment in vm.devices["pci"].get_attached_devices():
                cats = [infc.category for infc in assignment.device.interfaces]
                if DeviceCategory.PCI_USB in cats:
                    usb_qubes.add(vm)

        self.input_handler = InputDeviceHandler(
            qapp, policy_manager, gtk_builder, usb_qubes
        )

        self.u2f_handler = U2FPolicyHandler(
            self.qapp, self.policy_manager, gtk_builder, usb_qubes
        )

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = [
            self.input_handler.get_unsaved(),
            self.u2f_handler.get_unsaved(),
        ]
        return "\n".join([x for x in unsaved if x])

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        self.input_handler.reset()
        self.u2f_handler.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default."""
        self.input_handler.save()
        self.u2f_handler.save()
