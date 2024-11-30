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
Updates page handler
"""
import subprocess
from html import escape
from typing import Optional, List, Dict

from qrexec.policy.parser import Rule
from qrexec.client import call as qrexec_call

from ..widgets.gtk_widgets import VMListModeler, NONE_CATEGORY
from ..widgets.utils import get_boolean_feature, apply_feature_change
from .page_handler import PageHandler
from .policy_rules import RuleTargeted, SimpleVerbDescription
from .policy_handler import PolicyHandler
from .policy_manager import PolicyManager
from .rule_list_widgets import NoActionListBoxRow
from .conflict_handler import ConflictFileHandler
from .vm_flowbox import VMFlowboxHandler
from .policy_exceptions_handler import PolicyExceptionsHandler

import gi

import qubesadmin
import qubesadmin.vm
import qubesadmin.exc

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class RepoHandler:
    """Handler for repository settings."""

    def __init__(self, gtk_builder: Gtk.Builder):
        self.dom0_stable_radio: Gtk.RadioButton = gtk_builder.get_object(
            "updates_dom0_stable_radio"
        )
        self.dom0_testing_sec_radio: Gtk.RadioButton = gtk_builder.get_object(
            "updates_dom0_testing_sec_radio"
        )
        self.dom0_testing_radio: Gtk.RadioButton = gtk_builder.get_object(
            "updates_dom0_testing_radio"
        )

        self.template_official: Gtk.CheckButton = gtk_builder.get_object(
            "updates_template_official"
        )
        self.template_official_testing: Gtk.CheckButton = (
            gtk_builder.get_object("updates_template_official_testing")
        )
        self.template_community: Gtk.CheckButton = gtk_builder.get_object(
            "updates_template_community"
        )
        self.template_community_testing: Gtk.CheckButton = (
            gtk_builder.get_object("updates_template_community_testing")
        )

        self.problems_repo_box: Gtk.Box = gtk_builder.get_object(
            "updates_problem_repo"
        )
        self.problems_label: Gtk.Label = gtk_builder.get_object(
            "updates_problem_label"
        )

        # the code below relies on dicts in Python 3.6+ keeping the
        # order of items
        self.repo_to_widget_mapping = [
            {
                "qubes-dom0-current": self.dom0_stable_radio,
                "qubes-dom0-security-testing": self.dom0_testing_sec_radio,
                "qubes-dom0-current-testing": self.dom0_testing_radio,
            },
            {
                "qubes-templates-itl": self.template_official,
                "qubes-templates-itl-testing": self.template_official_testing,
            },
            {
                "qubes-templates-community": self.template_community,
                "qubes-templates-community-testing": self.template_community_testing,
            },
        ]
        self.initial_state: Dict[str, bool] = {}

        self.template_community.connect("toggled", self._community_toggled)

        self.repos: Dict[str, Dict] = {}
        self._load_data()
        self._load_state()
        self._community_toggled()

    def _community_toggled(self, _widget=None):
        if not self.template_community.get_active():
            self.template_community_testing.set_active(False)
            self.template_community_testing.set_sensitive(False)
        else:
            self.template_community_testing.set_sensitive(True)

    def _load_data(self):
        # pylint: disable=superfluous-parens
        try:
            for row in self._run_qrexec_repo("qubes.repos.List").split("\n"):
                lst = row.split("\0")
                repo_name = lst[0]
                self.repos[repo_name] = {}
                self.repos[repo_name]["prettyname"] = lst[1]
                self.repos[repo_name]["enabled"] = lst[2] == "enabled"
        except (RuntimeError, IndexError) as ex:
            # disable all repo-related stuff
            self.dom0_stable_radio.set_sensitive(False)
            self.dom0_testing_sec_radio.set_sensitive(False)
            self.dom0_testing_radio.set_sensitive(False)
            self.template_official_testing.set_sensitive(False)
            self.template_community.set_sensitive(False)
            self.template_community_testing.set_sensitive(False)
            self.repos = {}
            self.problems_repo_box.set_visible(True)
            self.problems_label.set_text(
                self.problems_label.get_text()
                + _(" Encountered error: ")
                + str(ex)
            )

    def _load_state(self):
        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                if repo not in self.repos:
                    continue
                if self.repos[repo]["enabled"]:
                    widget.set_active(self.repos[repo]["enabled"])

        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                self.initial_state[repo] = widget.get_active()

    @staticmethod
    def _run_qrexec_repo(service, arg=""):
        try:
            return qrexec_call("dom0", service, arg)
        except subprocess.CalledProcessError as ex:
            raise RuntimeError("qrexec call failed: " + str(ex.stderr)) from ex
        except Exception as ex:
            raise RuntimeError("qrexec call failed: " + str(ex)) from ex

    def _set_repository(self, repository, state):
        action = "Enable" if state else "Disable"
        result = self._run_qrexec_repo(f"qubes.repos.{action}", repository)
        if result != "ok\n":
            raise RuntimeError(
                'qrexec call stdout did not contain "ok"' " as expected"
            )

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if not self.repos:
            return ""

        dom0_changed = False
        itl_changed = False
        community_changed = False

        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                if self.initial_state[repo] != widget.get_active():
                    if "dom0" in repo:
                        dom0_changed = True
                    elif "community" in repo:
                        community_changed = True
                    elif "itl" in repo:
                        itl_changed = True
        unsaved = []
        if dom0_changed:
            unsaved.append(_("dom0 update source"))
        if itl_changed:
            unsaved.append(_("Official template update source"))
        if community_changed:
            unsaved.append(_("Community template update source"))

        return "\n".join(unsaved)

    def save(self):
        """Save all changes."""
        if not self.repos:
            return
        for repo_dict in self.repo_to_widget_mapping:
            found = False
            for repo, widget in repo_dict.items():
                try:
                    if widget.get_active():
                        found = True
                        self._set_repository(repo, True)
                    else:
                        self._set_repository(repo, not found)
                except RuntimeError as ex:
                    raise qubesadmin.exc.QubesException(
                        "Failed to set repository data: " f"{escape(str(ex))}"
                    ) from ex
        self._load_data()
        self._load_state()

    def reset(self):
        """Reset any user changes."""
        for repo_dict in self.repo_to_widget_mapping:
            for repo, widget in repo_dict.items():
                widget.set_active(self.initial_state[repo])


class UpdateCheckerHandler:
    """Handler for checking for updates settings."""

    FEATURE_NAME = "service.qubes-update-check"

    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        self.qapp = qapp

        # check for updates dom0 checkbutton
        self.dom0_update_check: Gtk.CheckButton = gtk_builder.get_object(
            "updates_dom0_update_check"
        )

        self.enable_radio: Gtk.RadioButton = gtk_builder.get_object(
            "updates_enable_radio"
        )
        self.disable_radio: Gtk.RadioButton = gtk_builder.get_object(
            "updates_disable_radio"
        )

        # check for if there are exceptions for check upd
        self.exceptions_check: Gtk.CheckButton = gtk_builder.get_object(
            "updates_exceptions_check"
        )

        self.exception_label: Gtk.Label = gtk_builder.get_object(
            "updates_check_exception_label"
        )

        self.initial_dom0 = get_boolean_feature(
            self.qapp.domains["dom0"], self.FEATURE_NAME, True
        )
        self.dom0_update_check.set_active(self.initial_dom0)

        self.initial_default = get_boolean_feature(
            self.qapp.domains["dom0"], "config.default.qubes-update-check", True
        )

        self.initial_exceptions: List[qubesadmin.vm.QubesVM] = []

        for vm in self.qapp.domains:
            if vm.klass == "AdminVM":
                continue
            if (
                get_boolean_feature(vm, self.FEATURE_NAME, True)
                != self.initial_default
            ):
                self.initial_exceptions.append(vm)

        if self.initial_default:
            self.enable_radio.set_active(True)
        else:
            self.disable_radio.set_active(True)

        self.exceptions_check.set_active(bool(self.initial_exceptions))

        self.flowbox_handler = VMFlowboxHandler(
            gtk_builder,
            qapp,
            "updates_exception",
            initial_vms=self.initial_exceptions,
            filter_function=lambda vm: vm.klass != "AdminVM",
        )

        self._set_label()
        self.enable_radio.connect("toggled", self._enable_disable_toggled)

        self.flowbox_handler.set_visible(self.exceptions_check.get_active())

        self.exceptions_check.connect(
            "toggled", self._enable_exceptions_clicked
        )

    def _set_label(self):
        if self.enable_radio.get_active():
            self.exception_label.set_markup(
                _(
                    "Except the following qubes, for which checking for updates"
                    " will be <b>disabled</b>"
                )
            )
        else:
            self.exception_label.set_markup(
                _(
                    "Except the following qubes, for which checking for updates"
                    " will be <b>enabled</b>"
                )
            )

    def _enable_disable_toggled(self, *_args):
        self._set_label()
        self.flowbox_handler.clear()
        self.exceptions_check.set_active(False)

    def _enable_exceptions_clicked(self, _widget=None):
        self.flowbox_handler.set_visible(self.exceptions_check.get_active())

    def get_unsaved(self) -> str:
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        unsaved = []
        if self.initial_dom0 != self.dom0_update_check.get_active():
            unsaved.append(_('dom0 "check for updates" setting'))
        if self.initial_default != self.enable_radio.get_active():
            unsaved.append(_('Default "check for updates" setting'))
        if (
            self.exceptions_check.get_active() != bool(self.initial_exceptions)
            or self.flowbox_handler.is_changed()
        ):
            unsaved.append(
                _("Qubes selected for unusual 'check for updates'" " behaviors")
            )
        return "\n".join(unsaved)

    def save(self):
        """Save any changes."""
        # FUTURE: this is fairly slow
        if self.initial_dom0 != self.dom0_update_check.get_active():
            apply_feature_change(
                self.qapp.domains["dom0"],
                self.FEATURE_NAME,
                self.dom0_update_check.get_active(),
            )
            self.initial_dom0 = self.dom0_update_check.get_active()

        default_state = self.enable_radio.get_active()
        changed_default = False

        if self.initial_default != default_state:
            apply_feature_change(
                self.qapp.domains["dom0"],
                "config.default.qubes-update-check",
                default_state,
            )
            changed_default = True
            self.initial_default = default_state

        exceptions = self.flowbox_handler.selected_vms
        if changed_default or self.flowbox_handler.is_changed():
            for vm in self.qapp.domains:
                if vm.klass == "AdminVM":
                    continue
                vm_desired_state = (
                    default_state if vm not in exceptions else not default_state
                )
                vm_value = get_boolean_feature(vm, self.FEATURE_NAME, True)
                if vm_value != vm_desired_state:
                    # if we want False, we need to explicitly set it, else
                    # we just need to erase the feature
                    apply_feature_change(
                        vm,
                        self.FEATURE_NAME,
                        None if vm_desired_state else False,
                    )

        self.flowbox_handler.save()

    def reset(self):
        """Reset changes and go back to initial state."""
        self.dom0_update_check.set_active(self.initial_dom0)
        self.enable_radio.set_active(self.initial_default)
        self.exceptions_check.set_active(bool(self.initial_exceptions))
        self.flowbox_handler.reset()


class UpdateProxy:
    """Handler for the rules connected to UpdateProxy policy."""

    def __init__(
        self,
        gtk_builder: Gtk.Builder,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        policy_file_name: str,
        service_name: str,
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.policy_file_name = policy_file_name
        self.service_name = service_name

        self.has_whonix = self._check_for_whonix()

        self.default_updatevm = self.qapp.domains.get("sys-net", None)
        self.default_whonix_updatevm = self.qapp.domains.get("sys-whonix", None)

        self.first_eligible_vm = None

        for vm in self.qapp.domains:
            if vm.klass != "AdminVM" and not vm.is_networked():
                self.first_eligible_vm = vm
                break

        self.def_updatevm_combo: Gtk.ComboBox = gtk_builder.get_object(
            "updates_def_updatevm_combo"
        )
        self.whonix_updatevm_combo: Gtk.ComboBox = gtk_builder.get_object(
            "updates_whonix_updatevm_combo"
        )
        self.whonix_updatevm_box: Gtk.Box = gtk_builder.get_object(
            "updates_whonix_updatevm_box"
        )

        self.rules: List[Rule] = []
        self.current_token: Optional[str] = None

        self.exception_list_handler = PolicyExceptionsHandler(
            gtk_builder=gtk_builder,
            prefix="updates_updatevm",
            policy_manager=self.policy_manager,
            row_func=self._get_row,
            new_rule=self._new_rule,
            exclude_rule=self._rule_filter,
            enable_raw=False,
        )

        self.updatevm_model = VMListModeler(
            combobox=self.def_updatevm_combo,
            qapp=self.qapp,
            filter_function=self._updatevm_filter,
            current_value=None,
            additional_options={"None": _("(none)")},
        )
        self.whonix_updatevm_model = VMListModeler(
            combobox=self.whonix_updatevm_combo,
            qapp=self.qapp,
            filter_function=self._whonixupdatevm_filter,
            current_value=None,
            additional_options={"None": _("(none)")},
        )

        self.load_rules()

        self.whonix_updatevm_box.set_visible(self.has_whonix)

    def _check_for_whonix(self) -> bool:
        for vm in self.qapp.domains:
            if "whonix-updatevm" in vm.tags or "anon-gateway" in vm.tags:
                return True
        return False

    @staticmethod
    def _updatevm_filter(vm):
        return getattr(vm, "provides_network", False)

    @staticmethod
    def _whonixupdatevm_filter(vm):
        return "anon-gateway" in vm.tags

    @staticmethod
    def _rule_filter(rule):
        if rule.source == "@type:TemplateVM":
            return True
        if rule.source == "@tag:whonix-updatevm":
            return True
        return False

    @staticmethod
    def _needs_updatevm_filter(vm):
        if vm.klass in ("AdminVM", "AppVM"):
            return False
        if getattr(vm, "template", None):
            return False
        return bool(
            vm.features.check_with_template(
                "service.updates-proxy-setup", vm.klass == "TemplateVM"
            )
        )

    def load_rules(self):
        """Load rules into widgets."""
        self.rules, self.current_token = (
            self.policy_manager.get_rules_from_filename(
                self.policy_file_name, ""
            )
        )
        def_updatevm = self.default_updatevm
        def_whonix_updatevm = None

        if self.has_whonix:
            def_whonix_updatevm = self.default_whonix_updatevm

        for rule in reversed(self.rules):
            if rule.source == "@type:TemplateVM":
                def_updatevm = rule.action.target
            elif rule.source == "@tag:whonix-updatevm":
                def_whonix_updatevm = rule.action.target

        if def_updatevm:
            self.updatevm_model.select_value(str(def_updatevm))
            self.updatevm_model.update_initial()

        if self.has_whonix:
            self.whonix_updatevm_model.select_value(str(def_whonix_updatevm))
            self.whonix_updatevm_model.update_initial()

        self.exception_list_handler.initialize_with_rules(self.rules)

    def _get_row(self, rule: Rule, new: bool = False):
        return NoActionListBoxRow(
            parent_handler=self,
            rule=RuleTargeted(rule),
            qapp=self.qapp,
            verb_description=SimpleVerbDescription({}),
            initial_verb="uses",
            filter_target=self._updatevm_filter,
            filter_source=self._needs_updatevm_filter,
            is_new_row=new,
        )

    def _new_rule(self) -> Rule:
        return self.policy_manager.new_rule(
            service=self.service_name,
            source=str(self.first_eligible_vm),
            target="@default",
            action=f"allow target={self.default_updatevm}",
        )

    def verify_new_rule(
        self,
        row: NoActionListBoxRow,
        new_source: str,
        new_target: str,
        new_action: str,
    ) -> Optional[str]:
        """
        Verify correctness of a rule with new_source, new_target and new_action
        if it was to be associated with provided row. Return None if rule would
        be correct, and string description of error otherwise.
        """
        simple_verify = PolicyHandler.verify_rule_against_rows(
            self.exception_list_handler.current_rows,
            row,
            new_source,
            new_target,
            new_action,
        )
        if simple_verify:
            return simple_verify
        new_target_vm = self.qapp.domains[new_target]
        new_source_vm = self.qapp.domains[new_source]
        if (
            "whonix-updatevm" in new_source_vm.tags
            and "anon-gateway" not in new_target_vm.tags
        ):
            return _("Whonix qubes can only use Whonix update proxies!")
        return None

    @property
    def current_exception_rules(self):
        """Current rules from the Exception list."""
        rules = []
        for row in self.exception_list_handler.current_rows:
            rules.append(row.rule)
        return rules

    def is_changed(self) -> bool:
        """Check if state has changed."""
        if self.updatevm_model.is_changed():
            return True
        if self.whonix_updatevm_model.is_changed():
            return True
        if [
            rule.raw_rule for rule in self.current_exception_rules
        ] != self.rules[:-2]:
            return True
        return False

    def reset(self):
        """Reset to initial state."""
        self.load_rules()

    def save(self):
        """Save currently chosen settings."""
        if not self.is_changed():
            return
        rules = self.current_exception_rules
        raw_rules = [rule.raw_rule for rule in rules]

        new_update_proxies = set()
        for rule in rules:
            new_update_proxies.add(self.qapp.domains[rule.target])

        if self.has_whonix:
            raw_rules.append(
                self.policy_manager.new_rule(
                    service=self.service_name,
                    source="@tag:whonix-updatevm",
                    target="@default",
                    action="allow "
                    f"target={self.whonix_updatevm_model.get_selected()}",
                )
            )
            new_update_proxies.add(self.whonix_updatevm_model.get_selected())

        if self.updatevm_model.get_selected():
            raw_rules.append(
                self.policy_manager.new_rule(
                    service=self.service_name,
                    source="@type:TemplateVM",
                    target="@default",
                    action="allow "
                    f"target={self.updatevm_model.get_selected()}",
                )
            )
            new_update_proxies.add(self.updatevm_model.get_selected())

        self.policy_manager.save_rules(
            self.policy_file_name, raw_rules, self.current_token
        )
        _r, self.current_token = self.policy_manager.get_rules_from_filename(
            self.policy_file_name, ""
        )
        self.rules = self.current_exception_rules

        for vm in self.qapp.domains:
            if "service.qubes-updates-proxy" in vm.features:
                apply_feature_change(
                    vm,
                    "service.qubes-updates-proxy",
                    True if vm in new_update_proxies else None,
                )
            elif vm in new_update_proxies:
                apply_feature_change(vm, "service.qubes-updates-proxy", True)

    def close_all_edits(self):
        """Close all edited rows."""
        self.exception_list_handler.close_all_edits()


class UpdatesHandler(PageHandler):
    """Handler for all the disparate Updates functions."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        policy_manager: PolicyManager,
        gtk_builder: Gtk.Builder,
    ):
        """
        :param qapp: Qubes object
        :param policy_manager: PolicyManager object
        """

        self.qapp = qapp
        self.policy_manager = policy_manager
        self.service_name = "qubes.UpdatesProxy"
        self.policy_file_name = "50-config-updates"

        self.dom0_updatevm_combo: Gtk.ComboBox = gtk_builder.get_object(
            "updates_dom0_updatevm_combo"
        )

        self.dom0_updatevm_model = VMListModeler(
            combobox=self.dom0_updatevm_combo,
            qapp=self.qapp,
            filter_function=(
                lambda vm: vm.klass != "TemplateVM"
                and vm.klass != "AdminVM"
                and vm.is_networked()
            ),
            current_value=self.qapp.updatevm,
            additional_options=NONE_CATEGORY,
            style_changes=True,
        )

        # repo handler
        self.repo_handler = RepoHandler(gtk_builder=gtk_builder)
        self.update_checker = UpdateCheckerHandler(
            gtk_builder=gtk_builder, qapp=self.qapp
        )
        self.update_proxy = UpdateProxy(
            gtk_builder=gtk_builder,
            qapp=self.qapp,
            policy_manager=policy_manager,
            policy_file_name=self.policy_file_name,
            service_name=self.service_name,
        )

        self.conflict_handler = ConflictFileHandler(
            gtk_builder=gtk_builder,
            prefix="updates",
            service_names=[self.service_name],
            own_file_name=self.policy_file_name,
            policy_manager=self.policy_manager,
        )

    def close_all_edits(self):
        """Close all edited rows"""
        self.update_proxy.close_all_edits()

    def get_unsaved(self) -> str:
        """Get list of unsaved changes."""
        self.close_all_edits()

        unsaved = [
            self.repo_handler.get_unsaved(),
            self.update_checker.get_unsaved(),
        ]

        if self.dom0_updatevm_model.is_changed():
            unsaved.append(_("dom0 Update Proxy"))
        if self.update_proxy.is_changed():
            unsaved.append(_("Update proxy settings"))
        unsaved = [x for x in unsaved if x]
        return "\n".join(unsaved)

    def reset(self):
        """Reset state to initial or last saved state, whichever is newer."""
        self.dom0_updatevm_model.reset()
        self.repo_handler.reset()
        self.update_checker.reset()
        self.update_proxy.reset()

    def save(self):
        """Save current rules, whatever they are - custom or default.
        Return True if successful, False otherwise"""

        for handler in [
            self.repo_handler,
            self.update_checker,
            self.update_proxy,
        ]:
            handler.save()  # type: ignore

        if self.dom0_updatevm_model.is_changed():
            self.qapp.updatevm = self.dom0_updatevm_model.get_selected()
