# coding=utf-8
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022  Piotr Bartman <prbartman@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
import dataclasses
from typing import Optional, Union, Callable

import importlib.resources
import gi

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, GObject

from qubes_config.global_config.vm_flowbox import VMFlowboxHandler
from qubes_config.widgets.utils import (
    get_boolean_feature,
    apply_feature_change,
    get_feature,
)


GObject.signal_new(
    "child-removed",
    Gtk.FlowBox,
    GObject.SignalFlags.RUN_LAST,
    GObject.TYPE_PYOBJECT,
    (GObject.TYPE_PYOBJECT,),
)


@dataclasses.dataclass(frozen=True)
class OverriddenSettings:
    apply_to_sys: Optional[bool] = None
    apply_to_other: Optional[bool] = None
    max_concurrency: Optional[int] = None
    update_if_stale: Optional[int] = None


class Settings:
    DEFAULT_CONCURRENCY = 4
    MAX_CONCURRENCY = 16
    DEFAULT_UPDATE_IF_STALE = 7
    MAX_UPDATE_IF_STALE = 99
    DEFAULT_RESTART_SERVICEVMS = True
    DEFAULT_RESTART_OTHER_VMS = False
    DEFAULT_HIDE_SKIPPED = True
    DEFAULT_HIDE_UPDATED = False

    def __init__(
        self,
        main_window,
        qapp,
        log,
        refresh_callback: Callable,
        overrides: OverriddenSettings = OverriddenSettings(),
    ):
        self.qapp = qapp
        self.log = log
        self.refresh_callback = refresh_callback
        self.overrides = overrides
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.builder = Gtk.Builder()
        self.builder.set_translation_domain("desktop-linux-manager")

        glade_ref = importlib.resources.files("qui") / "updater_settings.glade"
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.settings_window: Gtk.Window = self.builder.get_object(
            "main_window"
        )

        self.settings_window.set_transient_for(main_window)
        self.settings_window.connect("delete-event", self.close_without_saving)

        self.cancel_button: Gtk.Button = self.builder.get_object(
            "button_settings_cancel"
        )
        self.cancel_button.connect(
            "clicked", lambda _: self.settings_window.close()
        )

        self.save_button: Gtk.Button = self.builder.get_object(
            "button_settings_save"
        )
        self.save_button.connect("clicked", self.save_and_close)

        self.days_without_update_button: Gtk.SpinButton = (
            self.builder.get_object("days_without_update")
        )
        adj = Gtk.Adjustment(
            Settings.DEFAULT_UPDATE_IF_STALE,
            1,
            Settings.MAX_UPDATE_IF_STALE,
            1,
            1,
            1,
        )
        self.days_without_update_button.configure(adj, 1, 0)

        self.restart_servicevms_checkbox: Gtk.CheckButton = (
            self.builder.get_object("restart_servicevms")
        )
        self.restart_servicevms_checkbox.connect(
            "toggled", self._show_restart_exceptions
        )

        self.restart_other_checkbox: Gtk.CheckButton = self.builder.get_object(
            "restart_other"
        )
        self.restart_other_checkbox.connect(
            "toggled", self._show_restart_exceptions
        )

        self.hide_skipped_checkbox: Gtk.CheckButton = self.builder.get_object(
            "hide_skipped"
        )

        self.hide_updated_checkbox: Gtk.CheckButton = self.builder.get_object(
            "hide_updated"
        )

        self.available_vms = [
            vm
            for vm in self.qapp.domains
            if vm.klass == "DispVM"
            and not vm.auto_cleanup
            or vm.klass == "AppVM"
        ]
        self.excluded_vms = [
            vm
            for vm in self.available_vms
            if not get_boolean_feature(vm, "restart-after-update", True)
        ]
        self.exceptions = VMFlowboxHandler(
            self.builder,
            self.qapp,
            "restart_exceptions",
            self.excluded_vms,
            lambda vm: vm in self.available_vms,
        )
        self.restart_exceptions_page: Gtk.Box = self.builder.get_object(
            "restart_exceptions_page"
        )

        self.limit_concurrency_checkbox: Gtk.CheckButton = (
            self.builder.get_object("limit_concurrency")
        )
        self.limit_concurrency_checkbox.connect(
            "toggled", self._limit_concurrency_toggled
        )
        self.max_concurrency_button: Gtk.SpinButton = self.builder.get_object(
            "max_concurrency"
        )
        adj = Gtk.Adjustment(
            Settings.DEFAULT_CONCURRENCY,
            1,
            Settings.MAX_CONCURRENCY + 1,
            1,
            1,
            1,
        )
        self.max_concurrency_button.configure(adj, 1, 0)

        self._init_update_if_stale: Optional[int] = None
        self._init_restart_servicevms: Optional[bool] = None
        self._init_restart_other_vms: Optional[bool] = None
        self._init_limit_concurrency: Optional[bool] = None
        self._init_max_concurrency: Optional[int] = None
        self._init_hide_skipped: Optional[bool] = None
        self._init_hide_updated: Optional[bool] = None

    @property
    def update_if_stale(self) -> int:
        """Return the current (set by this window or manually) option value."""
        if self.overrides.update_if_stale is not None:
            return self.overrides.update_if_stale
        return int(
            get_feature(
                self.vm,
                "qubes-vm-update-update-if-stale",
                Settings.DEFAULT_UPDATE_IF_STALE,
            )
        )

    @property
    def restart_service_vms(self) -> bool:
        """Return the current (set by this window or manually) option value."""
        if self.overrides.apply_to_sys is not None:
            return self.overrides.apply_to_sys

        result = get_boolean_feature(
            self.vm, "qubes-vm-update-restart-servicevms", None
        )
        # TODO
        #  If not set, try to use a deprecated flag instead of
        #  the default value. This is only for backward compatibility
        #  and should be removed in future (e.g. Qubes 5.0 or later)
        if result is None:
            result = get_boolean_feature(
                self.vm,
                "qubes-vm-update-restart-system",
                Settings.DEFAULT_RESTART_SERVICEVMS,
            )

        return result

    @property
    def restart_other_vms(self) -> bool:
        """Return the current (set by this window or manually) option value."""
        if self.overrides.apply_to_other is not None:
            return self.overrides.apply_to_other
        return get_boolean_feature(
            self.vm,
            "qubes-vm-update-restart-other",
            Settings.DEFAULT_RESTART_OTHER_VMS,
        )

    @property
    def hide_skipped(self) -> bool:
        return get_boolean_feature(
            self.vm,
            "qubes-vm-update-hide-skipped",
            Settings.DEFAULT_HIDE_SKIPPED,
        )

    @property
    def hide_updated(self) -> bool:
        return get_boolean_feature(
            self.vm,
            "qubes-vm-update-hide-updated",
            Settings.DEFAULT_HIDE_UPDATED,
        )

    @property
    def max_concurrency(self) -> Optional[int]:
        """Return the current (set by this window or manually) option value."""
        if self.overrides.max_concurrency is not None:
            return self.overrides.max_concurrency
        result = get_feature(self.vm, "qubes-vm-update-max-concurrency", None)
        if result is None:
            return result
        return int(result)

    def load_settings(self):
        self._init_update_if_stale = self.update_if_stale
        self.days_without_update_button.set_value(self._init_update_if_stale)
        self.days_without_update_button.set_sensitive(
            not self.overrides.update_if_stale
        )

        self._init_restart_servicevms = self.restart_service_vms
        self._init_restart_other_vms = self.restart_other_vms
        self.restart_servicevms_checkbox.set_sensitive(
            not self.overrides.apply_to_sys
        )
        self.restart_servicevms_checkbox.set_active(
            self._init_restart_servicevms
        )
        self.restart_other_checkbox.set_active(self._init_restart_other_vms)
        self.restart_other_checkbox.set_sensitive(
            not self.overrides.apply_to_other
        )

        self._init_max_concurrency = self.max_concurrency
        self._init_limit_concurrency = self._init_max_concurrency is not None
        self.limit_concurrency_checkbox.set_active(self._init_limit_concurrency)
        self.limit_concurrency_checkbox.set_sensitive(
            not self.overrides.max_concurrency
        )
        if self._init_limit_concurrency:
            self.max_concurrency_button.set_value(self._init_max_concurrency)

        self._init_hide_skipped = self.hide_skipped
        self._init_hide_updated = self.hide_updated
        self.hide_skipped_checkbox.set_active(self._init_hide_skipped)
        self.hide_updated_checkbox.set_active(self._init_hide_updated)

    def _show_restart_exceptions(self, _emitter=None):
        if self.restart_other_checkbox.get_active():
            self.restart_exceptions_page.show_all()
            self.exceptions.reset()
        else:
            self.restart_exceptions_page.hide()

    def _limit_concurrency_toggled(self, _emitter=None):
        self.max_concurrency_button.set_sensitive(
            self.limit_concurrency_checkbox.get_active()
            and not self.overrides.max_concurrency
        )

    def show(self):
        """Show a hidden window."""
        self.load_settings()
        self.settings_window.show_all()
        self._show_restart_exceptions()
        self._limit_concurrency_toggled()

    def close_without_saving(self, _emitter, _):
        """Close without saving any changes."""
        self.settings_window.hide()
        return True

    def save_and_close(self, _emitter):
        """Save all changes and close."""
        self._save_option(
            name="update-if-stale",
            value=int(self.days_without_update_button.get_value()),
            init=self._init_update_if_stale,
            default=Settings.DEFAULT_UPDATE_IF_STALE,
        )

        self._save_option(
            name="restart-servicevms",
            value=self.restart_servicevms_checkbox.get_active(),
            init=self._init_restart_servicevms,
            default=Settings.DEFAULT_RESTART_SERVICEVMS,
        )
        # TODO
        #  Make sure that the deprecated flag is unset.
        #  Should be removed in future (e.g. Qubes 5.0 or later)
        apply_feature_change(self.vm, "qubes-vm-update-restart-system", None)

        self._save_option(
            name="restart-other",
            value=self.restart_other_checkbox.get_active(),
            init=self._init_restart_other_vms,
            default=Settings.DEFAULT_RESTART_OTHER_VMS,
        )

        self._save_option(
            name="hide-skipped",
            value=self.hide_skipped_checkbox.get_active(),
            init=self._init_hide_skipped,
            default=Settings.DEFAULT_HIDE_SKIPPED,
        )

        self._save_option(
            name="hide-updated",
            value=self.hide_updated_checkbox.get_active(),
            init=self._init_hide_updated,
            default=Settings.DEFAULT_HIDE_UPDATED,
        )

        limit_concurrency = self.limit_concurrency_checkbox.get_active()
        if self._init_limit_concurrency or limit_concurrency:
            if limit_concurrency:
                max_concurrency = int(self.max_concurrency_button.get_value())
            else:
                max_concurrency = None
            if self._init_max_concurrency != max_concurrency:
                apply_feature_change(
                    self.vm, "qubes-vm-update-max-concurrency", max_concurrency
                )

        if self.exceptions.is_changed():
            for vm in self.exceptions.added_vms:
                apply_feature_change(vm, "restart-after-update", False)
            for vm in self.exceptions.removed_vms:
                apply_feature_change(vm, "restart-after-update", None)
            self.exceptions.save()

        self.refresh_callback(self.update_if_stale)
        self.settings_window.close()

    def _save_option(
        self,
        name: str,
        value: Union[int, bool],
        init: Union[int, bool],
        default: Union[int, bool],
    ):
        if value != init:
            if value == default:
                value = None
            apply_feature_change(self.vm, f"qubes-vm-update-{name}", value)
