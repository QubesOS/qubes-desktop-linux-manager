#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position,import-error
""" A widget that monitors update availability and notifies the user
 about new updates to templates and standalone VMs"""
import asyncio
import sys
import subprocess

import qubesadmin
import qubesadmin.events
import qui.utils
from qubesadmin import exc

import gi  # isort:skip

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk, Gio  # isort:skip

import gbulb

gbulb.install()

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


class TextItem(Gtk.MenuItem):
    def __init__(self, text):
        super().__init__()
        title_label = Gtk.Label()
        title_label.set_markup(text)
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_justify(Gtk.Justification.CENTER)
        self.set_margin_left(10)
        self.set_margin_right(10)
        self.set_margin_top(5)
        self.add(title_label)
        self.set_sensitive(False)
        self.show_all()


class RunItem(Gtk.MenuItem):
    def __init__(self, text, command):
        super().__init__()
        title_label = Gtk.Label()
        title_label.set_markup(text)
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_justify(Gtk.Justification.CENTER)
        self.set_margin_left(10)
        self.set_margin_right(10)
        self.set_margin_bottom(5)
        self.add(title_label)
        self.show_all()
        self.connect("activate", command)


class UpdatesTray(Gtk.Application):
    def __init__(self, app_name, qapp, dispatcher):
        super().__init__()
        self.name = app_name

        self.dispatcher = dispatcher
        self.qapp = qapp

        self.set_application_id(self.name)
        self.register()  # register Gtk Application

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name("qui-updates")
        self.widget_icon.set_visible(False)
        self.widget_icon.connect("button-press-event", self.show_menu)
        self.widget_icon.set_tooltip_markup(
            _("<b>Qubes Update</b>\nUpdates are available.")
        )

        self.vms_needing_update = set()
        self.obsolete_vms = set()

        self.tray_menu = Gtk.Menu()

    def run(self):  # pylint: disable=arguments-differ
        self.check_vms_needing_update()
        self.connect_events()

        self.update_indicator_state()

    def setup_menu(self):
        self.tray_menu.set_reserve_toggle_size(False)

        if self.vms_needing_update:
            self.tray_menu.append(TextItem(_("<b>Qube updates available!</b>")))
            self.tray_menu.append(
                RunItem(
                    _(
                        "Updates for {} qubes are available!\n"
                        "<b>Launch updater</b>"
                    ).format(len(self.vms_needing_update)),
                    self.launch_updater,
                )
            )

        if self.obsolete_vms:
            self.tray_menu.append(
                TextItem(_("<b>Some qubes are no longer supported!</b>"))
            )
            obsolete_text = (
                _(
                    "The following qubes are based on distributions "
                    "that are no longer supported:\n"
                )
                + ", ".join([str(vm) for vm in self.obsolete_vms])
                + _("\n<b>Install new templates with Template Manager</b>")
            )
            self.tray_menu.append(
                RunItem(obsolete_text, self.launch_template_manager)
            )

        self.tray_menu.show_all()

    def show_menu(self, _unused, _event):
        self.tray_menu = Gtk.Menu()

        self.setup_menu()

        self.tray_menu.popup_at_pointer(None)  # use current event

    @staticmethod
    def launch_updater(*_args, **_kwargs):
        # pylint: disable=consider-using-with
        subprocess.Popen(["qubes-update-gui"])

    @staticmethod
    def launch_template_manager(*_args, **_kwargs):
        # pylint: disable=consider-using-with
        subprocess.Popen(["qvm-template-gui"])

    def check_vms_needing_update(self):
        self.vms_needing_update.clear()
        self.obsolete_vms.clear()
        for vm in self.qapp.domains:
            updated: bool = qui.utils.check_update(vm)
            supported: bool = qui.utils.check_support(vm)
            if not updated:
                self.vms_needing_update.add(vm)
            if not supported:
                self.obsolete_vms.add(vm.name)

    def connect_events(self):
        self.dispatcher.add_handler(
            "domain-feature-set:updates-available", self.feature_change
        )
        self.dispatcher.add_handler(
            "domain-feature-delete:updates-available", self.feature_change
        )
        self.dispatcher.add_handler(
            "domain-feature-set:skip-update", self.feature_change
        )
        self.dispatcher.add_handler(
            "domain-feature-delete:skip-update", self.feature_change
        )
        self.dispatcher.add_handler("domain-add", self.domain_added)
        self.dispatcher.add_handler("domain-delete", self.domain_removed)
        self.dispatcher.add_handler(
            "domain-feature-set:os-eol", self.feature_change
        )

    def domain_added(self, _submitter, _event, vm, *_args, **_kwargs):
        try:
            vm = self.qapp.domains[vm]
        except exc.QubesDaemonCommunicationError:
            return
        except exc.QubesException:
            # a disposableVM crashed on start
            return
        updated: bool = qui.utils.check_update(vm)
        supported: bool = qui.utils.check_support(vm)
        if not updated:
            self.vms_needing_update.add(vm.name)
            self.update_indicator_state()
        if not supported:
            self.obsolete_vms.add(vm)
            self.update_indicator_state()

    def domain_removed(self, _submitter, _event, vm, *_args, **_kwargs):
        if vm in self.vms_needing_update:
            self.vms_needing_update.remove(vm)
            self.update_indicator_state()
        if vm in self.obsolete_vms:
            self.obsolete_vms.remove(vm)
            self.update_indicator_state()

    def feature_change(self, vm, event, feature, **_kwargs):
        # pylint: disable=unused-argument
        updated: bool = qui.utils.check_update(vm)
        supported: bool = qui.utils.check_support(vm)

        if not updated and vm not in self.vms_needing_update:
            self.vms_needing_update.add(vm)
            notification = Gio.Notification.new(
                _("New updates are available for {}.").format(vm.name)
            )
            notification.set_priority(Gio.NotificationPriority.NORMAL)
            self.send_notification(None, notification)
        elif updated and vm in self.vms_needing_update:
            self.vms_needing_update.remove(vm)

        if not supported and vm not in self.obsolete_vms:
            self.obsolete_vms.add(vm.name)
        elif supported and vm in self.obsolete_vms:
            self.obsolete_vms.remove(vm.name)

        self.update_indicator_state()

    def update_indicator_state(self):
        if self.vms_needing_update or self.obsolete_vms:
            self.widget_icon.set_visible(True)
        else:
            self.widget_icon.set_visible(False)


def main():
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    app = UpdatesTray("org.qubes.qui.tray.Updates", qapp, dispatcher)
    app.run()

    loop = asyncio.get_event_loop()

    return qui.utils.run_asyncio_and_show_errors(
        loop,
        [asyncio.ensure_future(dispatcher.listen_for_events())],
        "Qubes Update Widget",
    )


if __name__ == "__main__":
    sys.exit(main())
