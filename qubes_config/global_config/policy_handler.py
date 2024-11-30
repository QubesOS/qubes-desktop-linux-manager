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
# pylint: disable=import-error
"""
RPC Policy-related functionality.
"""
from copy import deepcopy
from typing import Optional, List, Type, Set, Callable

from qrexec.policy.parser import Rule
from qrexec.exc import PolicySyntaxError

from ..widgets.gtk_widgets import VMListModeler, ExpanderHandler
from ..widgets.gtk_utils import show_error, ask_question, show_dialog_with_icon
from .page_handler import PageHandler
from .policy_rules import AbstractRuleWrapper, AbstractVerbDescription
from .policy_manager import PolicyManager
from .rule_list_widgets import (
    RuleListBoxRow,
    FilteredListBoxRow,
    ErrorRuleRow,
    LIMITED_CATEGORIES,
)
from .conflict_handler import ConflictFileHandler

import gi

import qubesadmin
import qubesadmin.vm
from ..widgets.utils import compare_rule_lists

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class PolicyHandler(PageHandler):
    """Handler for a single page with Policy settings."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
        prefix: str,
        policy_manager: PolicyManager,
        default_policy: str,
        service_name: str,
        policy_file_name: str,
        verb_description: AbstractVerbDescription,
        rule_class: Type[AbstractRuleWrapper],
        include_admin_vm: bool = False,
    ):
        """
        :param qapp: Qubes object
        :param gtk_builder: gtk_builder; to avoid inelegant design, this should
        not be stored in this function
        :param prefix: prefix for widgets used by this class
        :param policy_manager: PolicyManager object
        :param default_policy: string representing default policy file
        :param service_name: name of the service being handled by this page
        :param policy_file_name: name of the config's policy file for this
        service
        :param verb_description: AbstractVerbDescription object
        :param rule_class: class to be used for Rules, must inherit from
         AbstractRuleWrapper
        :param include_admin_vm: should adminvms be allowed as
        target/source of policy?
        """

        self.qapp = qapp
        self.policy_manager = policy_manager
        self.default_policy = default_policy
        self.service_name = service_name
        self.policy_file_name = policy_file_name
        self.verb_description = verb_description
        self.rule_class = rule_class
        self.include_adminvm = include_admin_vm

        # main widgets
        self.main_list_box: Gtk.ListBox = gtk_builder.get_object(
            f"{prefix}_main_list"
        )
        self.exception_list_box: Gtk.ListBox = gtk_builder.get_object(
            f"{prefix}_exception_list"
        )

        # add new rule button
        self.add_button: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_add_rule_button"
        )

        # enable/disable custom policy
        self.enable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f"{prefix}_enable_radio"
        )
        self.disable_radio: Gtk.RadioButton = gtk_builder.get_object(
            f"{prefix}_disable_radio"
        )

        # connect events
        self.add_button.connect("clicked", self.add_new_rule)

        self.exception_list_box.connect("row-activated", self._rule_clicked)
        self.main_list_box.connect("row-activated", self._rule_clicked)
        self.exception_list_box.connect(
            "rules-changed", self._populate_raw_rules
        )
        self.main_list_box.connect("rules-changed", self._populate_raw_rules)

        self.enable_radio.connect("toggled", self._custom_toggled)
        self.disable_radio.connect("toggled", self._custom_toggled)

        self.exception_list_box.set_sort_func(self.rule_sorting_function)
        self.main_list_box.set_sort_func(self.rule_sorting_function)

        self.conflict_handler = ConflictFileHandler(
            gtk_builder=gtk_builder,
            prefix=prefix,
            service_names=[self.service_name],
            own_file_name=self.policy_file_name,
            policy_manager=self.policy_manager,
        )

        self.error_handler = ErrorHandler(gtk_builder, prefix)

        self.raw_handler = RawPolicyTextHandler(
            gtk_builder=gtk_builder,
            prefix=prefix,
            policy_manager=self.policy_manager,
            error_handler=self.error_handler,
            callback_on_save_raw=self.populate_rule_lists,
            callback_on_open_raw=self.close_all_edits,
        )

        # fill data
        self.initial_rules: List[Rule] = []
        self.current_token: Optional[str] = None
        self.initialize_data()

        self.main_list_box.connect("map", self.on_switch)

    def _populate_raw_rules(self, *_args):
        self.raw_handler.fill_raw(self.current_rules)

    def add_new_rule(self, *_args):
        """Add a new rule."""
        self.close_all_edits()
        deny_all_rule = self.policy_manager.new_rule(
            service=self.service_name,
            source="@anyvm",
            target="@anyvm",
            action="deny",
        )
        new_row = RuleListBoxRow(
            self,
            self.rule_class(deny_all_rule),
            self.qapp,
            self.verb_description,
            is_new_row=True,
            enable_adminvm=self.include_adminvm,
        )
        self.exception_list_box.add(new_row)
        new_row.activate()

    @property
    def current_rules(self) -> List[Rule]:
        """
        Get the currently selected set of AbstractRuleWrapper rules.
        """
        if self.disable_radio.get_active():
            return self.policy_manager.text_to_rules(self.default_policy)
        return [
            row.rule.raw_rule for row in self.current_rows if not row.is_new_row
        ]

    @property
    def current_rows(self) -> List[RuleListBoxRow]:
        """
        Get the current list of all RuleListBoxRows
        """
        return (
            self.exception_list_box.get_children()
            + self.main_list_box.get_children()
        )

    def initialize_data(self):
        rules, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, self.default_policy
        )

        # fill data
        self.populate_rule_lists(rules)
        self.raw_handler.fill_raw(rules)

        self.initial_rules = deepcopy(self.current_rules)

    def populate_rule_lists(self, rules: List[Rule]):
        """Populate rule lists with the provided set of Rule objects."""
        for child in self.main_list_box.get_children():
            self.main_list_box.remove(child)
        for child in self.exception_list_box.get_children():
            self.exception_list_box.remove(child)

        self.error_handler.clear_all_errors()

        for rule in rules:
            try:
                wrapped_rule = self.rule_class(rule)
                if wrapped_rule.is_rule_fundamental():
                    self.main_list_box.add(
                        RuleListBoxRow(
                            self,
                            wrapped_rule,
                            self.qapp,
                            self.verb_description,
                            enable_delete=False,
                            enable_vm_edit=False,
                            enable_adminvm=self.include_adminvm,
                        )
                    )
                    continue
                fundamental = (
                    self.include_adminvm
                    and rule.source == "@adminvm"
                    and rule.target == "@anyvm"
                )
                self.exception_list_box.add(
                    RuleListBoxRow(
                        self,
                        rule=wrapped_rule,
                        qapp=self.qapp,
                        verb_description=self.verb_description,
                        enable_delete=not fundamental,
                        enable_vm_edit=not fundamental,
                        enable_adminvm=self.include_adminvm,
                    )
                )
            except Exception:  # pylint: disable=broad-except
                self.error_handler.add_error(rule)

        if not self.main_list_box.get_children():
            deny_all_rule = self.policy_manager.new_rule(
                service=self.service_name,
                source="@anyvm",
                target="@anyvm",
                action="deny",
            )
            self.main_list_box.add(
                RuleListBoxRow(
                    self,
                    self.rule_class(deny_all_rule),
                    self.qapp,
                    self.verb_description,
                    enable_delete=False,
                    enable_vm_edit=False,
                    enable_adminvm=self.include_adminvm,
                )
            )

        self.check_custom_rules(rules)

    def set_custom_editable(self, state: bool):
        """If true, set widgets to accept editing custom rules."""
        self.add_button.set_sensitive(state)
        self.main_list_box.set_sensitive(state)
        self.exception_list_box.set_sensitive(state)

    @staticmethod
    def cmp_token(token_1, token_2):
        """Helper method to compare VMTokens in a format Gtk likes."""
        # @anyvm goes at the end, then other generic tokens,
        # otherwise compare lexically
        if token_1 == token_2:
            return 0
        if token_1 == "@anyvm":
            return 1
        if token_2 == "@anyvm":
            return -1
        is_token_1_keyword = token_1.startswith("@")
        is_token_2_keyword = token_2.startswith("@")
        if is_token_1_keyword == is_token_2_keyword:
            if token_1 < token_2:
                return -1
            return 1
        if is_token_1_keyword:
            return 1
        return -1

    def rule_sorting_function(
        self, row_1: RuleListBoxRow, row_2: RuleListBoxRow
    ):
        """Sorting function for exceptions."""
        source_cmp = self.cmp_token(row_1.rule.source, row_2.rule.source)
        if source_cmp != 0:
            return source_cmp
        return self.cmp_token(row_1.rule.target, row_2.rule.target)

    def check_custom_rules(self, rules: List[Rule]):
        """
        Check if the provided set of rules is the same as the default set,
        set radio buttons accordingly.
        """
        if self.policy_manager.compare_rules_to_text(
            rules, self.default_policy
        ):
            self.disable_radio.set_active(True)
        else:
            self.enable_radio.set_active(True)
        self._custom_toggled()

    def _custom_toggled(self, _widget=None):
        self.close_all_edits()
        self.set_custom_editable(self.enable_radio.get_active())
        self.raw_handler.fill_raw(self.current_rules)

    def _rule_clicked(self, _list_box, row: RuleListBoxRow, *_args):
        if row.editing:
            # if the current row was clicked, nothing should happen
            return
        self.close_all_edits()
        row.set_edit_mode(True)

    @staticmethod
    def verify_rule_against_rows(
        other_rows: List[RuleListBoxRow],
        row: RuleListBoxRow,
        new_source: str,
        new_target: str,
        new_action: str,
    ) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        for other_row in other_rows:
            if other_row == row:
                continue
            if other_row.rule.is_rule_conflicting(
                new_source, new_target, new_action
            ):
                return str(other_row)
        return None

    def verify_new_rule(
        self,
        row: RuleListBoxRow,
        new_source: str,
        new_target: str,
        new_action: str,
    ) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        return self.verify_rule_against_rows(
            self.current_rows, row, new_source, new_target, new_action
        )

    @staticmethod
    def close_rows_in_list(row_list: List[RuleListBoxRow]):
        """Close all edited rows in provided ListBox"""
        for row in row_list:
            if row.editing:
                if not row.is_changed():
                    row.set_edit_mode(False)
                    continue
                response = show_dialog_with_icon(
                    parent=row.get_toplevel(),
                    title=_("Unsaved changes"),
                    text=_(
                        "A rule is currently being edited. \n"
                        "Do you want to save changes to the following"
                        "rule?\n"
                    )
                    + str(row),
                    buttons={
                        _("_Save changes"): Gtk.ResponseType.YES,
                        _("_Discard changes"): Gtk.ResponseType.NO,
                    },
                    icon_name="qubes-ask",
                )

                if response == Gtk.ResponseType.YES:
                    if not row.validate_and_save():
                        row.revert()
                else:
                    row.revert()

    def close_all_edits(self, *_args):
        """Close all edited rows."""
        self.close_rows_in_list(self.current_rows)

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        rules = deepcopy(self.initial_rules)
        self.populate_rule_lists(rules)
        self.raw_handler.fill_raw(rules)

    def save(self):
        """Save current rules, whatever they are - custom or default."""
        rules = self.current_rules
        self.policy_manager.save_rules(
            self.policy_file_name, rules, self.current_token
        )
        _r, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, self.default_policy
        )

        self.initial_rules = deepcopy(rules)

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        self.close_all_edits()
        changed = []
        if self.raw_handler.get_unsaved():
            changed.append(_("Raw policy text"))

        if not compare_rule_lists(self.initial_rules, self.current_rules):
            changed.append(_("Policy rules"))
        return "\n".join(changed)

    def on_switch(self, *_args):
        if self.error_handler.get_errors():
            rule_text = "\n".join(
                str(rule) for rule in self.error_handler.get_errors()
            )
            show_error(
                parent=self.main_list_box.get_toplevel(),
                title=_("Unknown rule found in police file"),
                text=_("The following rules could not be parsed:\n")
                + rule_text
                + _(
                    "\nThis has probably happened due to "
                    "manual editing of the policy file. The "
                    "rule will be discarded."
                ),
            )


class RawPolicyTextHandler:
    """Class that handles raw text widgets"""

    def __init__(
        self,
        gtk_builder: Gtk.Builder,
        prefix: str,
        policy_manager: PolicyManager,
        error_handler: "ErrorHandler",
        callback_on_save_raw: Optional[Callable[[List[Rule]], None]],
        callback_on_open_raw: Optional[Callable],
    ):
        """
        :param gtk_builder: Gtk.Builder
        :param prefix: prefix for widgets
        :param policy_manager: PolicyManager
        :param error_handler: ErrorHandler
        :param callback_on_save_raw: callback to be executed
        when save_raw is clicked; must take a List[Rule] as a parameter
        :param callback_on_open_raw: called when raw edit is open/closed
        """
        self.policy_manager = policy_manager
        self.error_handler = error_handler
        self.callback_on_save_raw = callback_on_save_raw

        self.raw_event_button: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_raw_event"
        )
        self.raw_box: Gtk.Box = gtk_builder.get_object(f"{prefix}_raw_box")
        self.raw_expander_icon: Gtk.Image = gtk_builder.get_object(
            f"{prefix}_raw_expander"
        )
        self.raw_text: Gtk.TextView = gtk_builder.get_object(
            f"{prefix}_raw_text"
        )
        self.raw_save: Gtk.Button = gtk_builder.get_object(f"{prefix}_raw_save")
        self.raw_cancel: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_raw_cancel"
        )
        self.text_buffer: Gtk.TextBuffer = self.raw_text.get_buffer()

        self.raw_save.connect("clicked", self._save_raw)
        self.raw_cancel.connect("clicked", self._cancel_raw)

        self.expander_handler = ExpanderHandler(
            event_button=self.raw_event_button,
            data_container=self.raw_box,
            icon=self.raw_expander_icon,
            event_callback=callback_on_open_raw,
        )

        self.last_known_rules: List[Rule] = []

    def _save_raw(self, _widget):
        try:
            rules: List[Rule] = self.policy_manager.text_to_rules(
                self.text_buffer.get_text(
                    self.text_buffer.get_start_iter(),
                    self.text_buffer.get_end_iter(),
                    False,
                )
            )
            if self.callback_on_save_raw:
                self.callback_on_save_raw(rules)

            if self.error_handler.get_errors():
                rule_text = "\n".join(
                    str(rule) for rule in self.error_handler.get_errors()
                )
                raise PolicySyntaxError(None, None, rule_text)

            self.expander_handler.set_state(False)
        except PolicySyntaxError as ex:
            error_message = str(ex).split(":", 3)[2]
            show_error(
                parent=self.raw_box.get_toplevel(),
                title=_("Error parsing rules"),
                text=_("The following rules could not be parsed:\n")
                + error_message
                + "\n",
            )

    def _cancel_raw(self, _widget):
        self.fill_raw(self.last_known_rules)
        self.expander_handler.set_state(False)

    def fill_raw(self, rules: List[Rule]):
        """Fill raw text window with provided rules"""
        self.last_known_rules = rules
        self.text_buffer.set_text(self.policy_manager.rules_to_text(rules))
        self.text_buffer.set_modified(False)

    def get_unsaved(self) -> bool:
        """Return True if the raw rule text was changed."""
        return self.text_buffer.get_modified()


class VMSubsetPolicyHandler(PolicyHandler):
    """
    Handler for a list of policy rules where targets are limited to a subset
    of VMs, that is, SplitGPG. Currently makes SplitGPG assumptions, such
    as networked qube is dangerous.
    """

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
        prefix: str,
        policy_manager: PolicyManager,
        default_policy: str,
        service_name: str,
        policy_file_name: str,
        main_verb_description: AbstractVerbDescription,
        main_rule_class: Type[AbstractRuleWrapper],
        exception_verb_description: AbstractVerbDescription,
        exception_rule_class: Type[AbstractRuleWrapper],
    ):
        """
        :param qapp: Qubes object
        :param gtk_builder: gtk_builder; to avoid inelegant design, this should
        not be stored in this function
        :param prefix: prefix for widgets used by this class
        :param policy_manager: PolicyManager object
        :param default_policy: string representing default policy file
        :param service_name: name of the service being handled by this page
        :param policy_file_name: name of the config's policy file for this
        service
        :param main_verb_description: AbstractVerbDescription object for the
        main rules
        :param main_rule_class: class to be used for main Rules, must inherit
        from AbstractRuleWrapper
        :param exception_verb_description: AbstractVerbDescription object for
        the exception rules
        :param exception_rule_class: class to be used for exception Rules, must
         inherit from AbstractRuleWrapper
        """
        self.select_qubes: Set[str] = set()
        self.main_verb_description = main_verb_description
        self.main_rule_class = main_rule_class
        self.exception_verb_description = exception_verb_description
        self.exception_rule_class = exception_rule_class

        # main widgets
        self.add_select_box: Gtk.Box = gtk_builder.get_object(
            f"{prefix}_add_select_box"
        )
        self.add_select_button: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_add_select_button"
        )
        self.add_select_confirm: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_add_select_confirm"
        )
        self.add_select_cancel: Gtk.Button = gtk_builder.get_object(
            f"{prefix}_add_select_cancel"
        )
        self.select_qube_combo: Gtk.ComboBox = gtk_builder.get_object(
            f"{prefix}_select_qube_combo"
        )

        super().__init__(
            qapp,
            gtk_builder,
            prefix,
            policy_manager,
            default_policy,
            service_name,
            policy_file_name,
            exception_verb_description,
            exception_rule_class,
        )

        # populate combo
        self.select_qube_model = VMListModeler(
            combobox=self.select_qube_combo, qapp=self.qapp
        )

        # connect events
        self.add_select_button.connect("clicked", self._add_select_qube)
        self.add_select_confirm.connect("clicked", self._add_select_confirm)
        self.add_select_cancel.connect("clicked", self._add_select_cancel)

        self.main_list_box.connect("rules-changed", self._select_qubes_changed)

    def _select_qubes_changed(self, *_args):
        self.close_all_edits()
        self.select_qubes = {
            row.rule.target for row in self.main_list_box.get_children()
        }
        self.populate_rule_lists(self.current_rules, drop_obsolete=True)

    def _add_main_rule(self, rule):
        self.main_list_box.add(
            RuleListBoxRow(
                parent_handler=self,
                rule=self.main_rule_class(rule),
                qapp=self.qapp,
                verb_description=self.main_verb_description,
                enable_delete=True,
                enable_vm_edit=False,
                initial_verb="",
                custom_deletion_warning=_(
                    "Are you sure you want to delete this "
                    "rule? All related exceptions will also "
                    "be deleted."
                ),
                enable_adminvm=self.include_adminvm,
            )
        )

    def _add_exception_rule(self, rule):
        row = FilteredListBoxRow(
            parent_handler=self,
            rule=self.exception_rule_class(rule),
            qapp=self.qapp,
            initial_verb=_("will"),
            verb_description=self.exception_verb_description,
            filter_target=lambda x: str(x) in self.select_qubes,
            source_categories=LIMITED_CATEGORIES,
        )
        self.exception_list_box.add(row)
        return row

    @staticmethod
    def _has_partial_duplicate(rule: Rule, rules: List[Rule]) -> bool:
        # do not add a rule if it has target other than default and
        # there exists a rule with @default and that target as target
        # or default target
        for other_rule in rules:
            if (
                other_rule.source == rule.source
                and other_rule.target == "@default"
                and (
                    getattr(other_rule.action, "target", None) == rule.target
                    or getattr(other_rule.action, "default_target", None)
                    == rule.target
                )
            ):
                return True
        return False

    def populate_rule_lists(
        self, rules: List[Rule], drop_obsolete: bool = False
    ):
        """
        Populate the rule lists.
        :param rules: List of Rule objects
        :param drop_obsolete: should rules with target qubes that are not
        in key qube list be silently discarded?
        :return:
        """
        for child in (
            self.main_list_box.get_children()
            + self.exception_list_box.get_children()
        ):
            child.get_parent().remove(child)
        # rules with source = '@anyvm' go to main list and their
        # qubes are key qubes
        self.error_handler.clear_all_errors()

        # we have to first populate select qubes, then the rest of them

        for rule in reversed(rules):
            try:
                if rule.source == "@anyvm":
                    if rule.target.type == "keyword":
                        # we do not support this
                        self.error_handler.add_error(rule)
                        continue
                    self._add_main_rule(rule)
            except Exception:  # pylint: disable=broad-except
                self.error_handler.add_error(rule)
                continue

        self.select_qubes = {
            row.rule.target for row in self.main_list_box.get_children()
        }

        for rule in reversed(rules):
            try:
                if rule.target != "@default":
                    if self._has_partial_duplicate(rule, rules):
                        continue
                if rule.source != "@anyvm":
                    wrapped_exception_rule = self.exception_rule_class(rule)
                    if wrapped_exception_rule.target not in self.select_qubes:
                        if not drop_obsolete:
                            self.error_handler.add_error(rule)
                        continue
                    self._add_exception_rule(rule)
            except Exception:  # pylint: disable=broad-except
                self.error_handler.add_error(rule)
                continue
        self.add_button.set_sensitive(bool(self.main_list_box.get_children()))

        self.check_custom_rules(rules)

    def set_custom_editable(self, state: bool):
        super().set_custom_editable(state)
        self.add_select_button.set_sensitive(state)

    def _add_select_qube(self, *_args):
        self.close_all_edits()
        self.add_select_box.set_visible(True)

    def _add_select_confirm(self, *_args):
        new_qube = self.select_qube_model.get_selected()
        if not new_qube or not isinstance(new_qube, qubesadmin.vm.QubesVM):
            show_error(
                self.main_list_box,
                _("Invalid selection"),
                _(
                    "Invalid object was selected. {new_qube} is not a "
                    "valid Qubes qube."
                ).format(new_qube=new_qube),
            )
            return
        if new_qube.is_networked():
            response = ask_question(
                self.main_list_box,
                _("Add new key qube"),
                _(
                    "Are you sure you want to add {new_qube} as a key qube? It "
                    "has network access, which may lead to decreased "
                    "security."
                ).format(new_qube=new_qube),
            )
            if response == Gtk.ResponseType.NO:
                self._add_select_cancel()
                return
        new_qube = str(self.select_qube_model.get_selected())
        new_rule = self.policy_manager.new_rule(
            service=self.service_name,
            source="@anyvm",
            target=new_qube,
            action="ask",
        )
        self._add_main_rule(new_rule)
        self.add_select_box.set_visible(False)
        self.main_list_box.emit("rules-changed", None)

    def _add_select_cancel(self, *_args):
        self.add_select_box.set_visible(False)

    def add_new_rule(self, *_args):
        """Add a new rule."""
        self.close_all_edits()
        for qube in self.select_qubes:
            rule = self.policy_manager.new_rule(
                service=self.service_name,
                source=str(qube),
                target=str(qube),
                action="deny",
            )
            new_row = self._add_exception_rule(rule)
            new_row.is_new_row = True
            new_row.activate()
            break

    def close_all_edits(self, *_args):
        """Close all edited rows"""
        super().close_all_edits()
        if self.add_select_box.get_visible():
            self._add_select_cancel()

    @property
    def current_rules(self) -> List[Rule]:
        """
        Due to possible existing manual rules, every rule with @default
        is saved as two rules: a normal one and a one with target/default_target
        put in the default space"""
        if self.disable_radio.get_active():
            return self.policy_manager.text_to_rules(self.default_policy)
        rules: List[Rule] = []
        for row in self.exception_list_box.get_children():
            new_rule: Rule = row.rule.raw_rule
            if str(new_rule) in [str(rule) for rule in rules]:
                # do not save duplicates
                continue
            rules.append(new_rule)

            if new_rule.target == "@default":
                if getattr(new_rule.action, "default_target", None):
                    new_target = new_rule.action.default_target
                elif getattr(new_rule.action, "target", None):
                    new_target = new_rule.action.target
                else:
                    continue
                another_rule = self.policy_manager.new_rule(
                    service=self.service_name,
                    source=new_rule.source,
                    target=new_target,
                    action=type(new_rule.action).__name__.lower(),
                )
                if str(another_rule) in [str(rule) for rule in rules]:
                    # do not save duplicates
                    continue
                rules.append(another_rule)
        rules.extend(
            [row.rule.raw_rule for row in self.main_list_box.get_children()]
        )
        return rules


class ErrorHandler:
    """A helper class to manage boxes with error lists."""

    def __init__(self, gtk_builder, prefix: str):
        """
        :param gtk_builder: Gtk.Builder
        :param prefix: prefix for the following objects:
        - prefix_error_box that contains all error widgets
        - prefix_error_list, a ListBox that contains erroneous rules
        """
        self.error_box: Gtk.Box = gtk_builder.get_object(f"{prefix}_error_box")
        self.error_list: Gtk.ListBox = gtk_builder.get_object(
            f"{prefix}_error_list"
        )

        self._errors: List[Rule] = []

    def clear_all_errors(self):
        for child in self.error_list.get_children():
            self.error_list.remove(child)
        self._errors.clear()
        self.error_box.set_visible(False)

    def add_error(self, rule: Rule):
        self._errors.append(rule)
        self.error_box.set_visible(True)
        self.error_box.show_all()
        self.error_list.add(ErrorRuleRow(rule))
        self.error_list.show_all()

    def get_errors(self):
        return self._errors
