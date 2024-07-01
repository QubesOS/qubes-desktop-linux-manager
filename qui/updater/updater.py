#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position,import-error
import argparse
import logging
import sys
import time

import importlib.resources
import gi  # isort:skip

from qubes_config.widgets.gtk_utils import load_icon_at_gtk_size, load_theme, \
    show_dialog_with_icon, RESPONSES_OK
from qui.updater.progress_page import ProgressPage
from qui.updater.updater_settings import Settings, OverriddenSettings
from qui.updater.summary_page import SummaryPage
from qui.updater.intro_page import IntroPage
import qui.updater.utils

gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Gdk, Gio  # isort:skip
from qubesadmin import Qubes
import qubesadmin.exc

# using locale.gettext is necessary for Gtk.Builder translation support to work
# in most cases, gettext is better, but it cannot handle Gtk.Builder/glade files
import locale
from locale import gettext as l

locale.bindtextdomain("desktop-linux-manager", "/usr/locales/")
locale.textdomain('desktop-linux-manager')


class ArgumentError(Exception):
    """Nonsense arguments"""


class QubesUpdater(Gtk.Application):
    # pylint: disable=too-many-instance-attributes

    LOGPATH = '/var/log/qubes/qui.updater.log'
    LOG_FORMAT = '%(asctime)s %(message)s'

    def __init__(self, qapp, cliargs):
        super().__init__(
            application_id="org.gnome.example",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.qapp = qapp
        self.primary = False
        self.do_nothing = False
        self.connect("activate", self.do_activate)
        self.cliargs = cliargs
        self.retcode = 0

        log_handler = logging.FileHandler(
            QubesUpdater.LOGPATH, encoding='utf-8')
        log_formatter = logging.Formatter(QubesUpdater.LOG_FORMAT)
        log_handler.setFormatter(log_formatter)

        self.log = logging.getLogger('vm-update.agent.PackageManager')
        self.log.addHandler(log_handler)
        self.log.setLevel(self.cliargs.log)

    def do_activate(self, *_args, **_kwargs):
        if not self.primary:
            self.log.debug("Primary activation")
            self.perform_setup()
            self.primary = True
            self.hold()
        else:
            self.log.debug("Secondary activation")
            if self.do_nothing:
                self._show_success_dialog()
                self.window_close()
            else:
                self.main_window.present()

    def perform_setup(self, *_args, **_kwargs):
        self.log.debug("Setup")
        # pylint: disable=attribute-defined-outside-init
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain("desktop-linux-manager")

        glade_ref = (importlib.resources.files('qui') /
                      'updater.glade')
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.main_window: Gtk.Window = self.builder.get_object("main_window")
        self.next_button: Gtk.Button = self.builder.get_object("button_next")
        self.next_button.connect("clicked", self.next_clicked)
        self.cancel_button: Gtk.Button = self.builder.get_object(
            "button_cancel")
        self.cancel_button.connect("clicked", self.cancel_clicked)

        self.EffectiveCssProvider = load_theme(widget=self.main_window,
                   package_name='qui',
                   light_file_name='qubes-updater-light.css',
                   dark_file_name='qubes-updater-dark.css')
        qui.updater.utils.SetEffectiveCssProvider(self.EffectiveCssProvider)

        self.header_label: Gtk.Label = self.builder.get_object("header_label")

        self.intro_page = IntroPage(self.builder, self.log, self.next_button)
        self.progress_page = ProgressPage(
            self.builder,
            self.log,
            self.header_label,
            self.next_button,
            self.cancel_button,
            callback=lambda: self.next_clicked(None)
                     if self.cliargs.non_interactive else lambda: None
        )
        self.summary_page = SummaryPage(
            self.builder,
            self.log,
            self.next_button,
            self.cancel_button,
            self.progress_page.back_by_row_selection
        )

        self.button_settings: Gtk.Button = self.builder.get_object(
            "button_settings")
        self.button_settings.connect("clicked", self.open_settings_window)
        settings_pixbuf = load_icon_at_gtk_size(
            'qubes-customize', Gtk.IconSize.LARGE_TOOLBAR)
        settings_image = Gtk.Image.new_from_pixbuf(settings_pixbuf)
        self.button_settings.set_image(settings_image)

        overridden_apply_to_sys = None
        overridden_apply_to_other = None
        if self.cliargs.apply_to_all:
            overridden_apply_to_sys = True
            overridden_apply_to_other = True
        elif self.cliargs.apply_to_sys:
            overridden_apply_to_sys = True
        elif self.cliargs.no_apply:
            overridden_apply_to_sys = False
            overridden_apply_to_other = False

        overrides = OverriddenSettings(
            apply_to_sys=overridden_apply_to_sys,
            apply_to_other=overridden_apply_to_other,
            max_concurrency=self.cliargs.max_concurrency,
            update_if_stale=self.cliargs.update_if_stale,
        )

        self.settings = Settings(
            self.main_window,
            self.qapp,
            self.log,
            refresh_callback=self.intro_page.refresh_update_list,
            overrides=overrides,
        )

        headers = [(3, "intro_name"), (3, "progress_name"), (3, "summary_name"),
                   (3, "restart_name"), (4, "available"), (5, "check"),
                   (6, "update"), (8, "summary_status")]

        def cell_data_func(_column, cell, model, it, data):
            # Get the object from the model
            obj = model.get_value(it, data)
            # Set the cell value to the name of the object
            cell.set_property("markup", str(obj))

        for col, name in headers:
            renderer: Gtk.CellRenderer = self.builder.get_object(
                name + "_renderer")
            column: Gtk.TreeViewColumn = self.builder.get_object(
                name + "_column")
            column.set_cell_data_func(renderer, cell_data_func, col)
            renderer.props.ypad = 10
            if not name.endswith("name") and name != "summary_status":
                # center
                renderer.props.xalign = 0.5

        self.main_window.connect("delete-event", self.window_close)
        self.main_window.connect("key-press-event", self.check_escape)

        self.intro_page.populate_vm_list(self.qapp, self.settings)

        if skip_intro_if_args(self.cliargs):
            self.log.info("Skipping intro page.")
            self.intro_page.select_rows_ignoring_conditions(
                cliargs=self.cliargs, dom0=self.qapp.domains['dom0'])
            if len(self.intro_page.get_vms_to_update()) == 0:
                self.do_nothing = True
                return
            self.next_clicked(None, skip_intro=True)
        else:
            # default update_if_stale -> do nothing
            if self.cliargs.update_if_available:
                self.intro_page.head_checkbox.state = (
                    self.intro_page.head_checkbox.SAFE)
                self.intro_page.select_rows()
            elif self.cliargs.force_update:
                self.intro_page.head_checkbox.state = (
                    self.intro_page.head_checkbox.ALL)
                self.intro_page.select_rows()
            self.log.info("Show intro page.")
        self.main_window.show_all()
        width = self.intro_page.vm_list.get_preferred_width().natural_width
        self.main_window.resize(width + 50, int(width * 1.2))
        self.main_window.set_position(Gtk.WindowPosition.CENTER_ALWAYS)

    def open_settings_window(self, _emitter):
        self.settings.show()

    def next_clicked(self, _emitter, skip_intro=False):
        self.log.debug("Next clicked")
        if self.intro_page.is_visible or skip_intro:
            vms_to_update = self.intro_page.get_vms_to_update()
            self.intro_page.active = False
            self.progress_page.show()
            self.progress_page.init_update(vms_to_update, self.settings)
        elif self.progress_page.is_visible:
            if not self.summary_page.is_populated:
                self.summary_page.populate_restart_list(
                    restart=True,
                    vm_updated=self.progress_page.vms_to_update,
                    settings=self.settings
                )
            updated, no_updates, failed, cancelled = (
                self.progress_page.get_update_summary())
            if updated == 0:
                # no updates
                self.retcode = 100
            if failed:
                self.retcode = 1
            if cancelled:
                self.retcode = 130
            if failed or cancelled or not self.cliargs.non_interactive:
                self.summary_page.show(updated, no_updates, failed + cancelled)
            else:
                # at this point retcode is in (0, 100)
                self._restart_phase(
                    show_only_error=self.cliargs.non_interactive)
                # at thi point retcode is in (0, 100)
                # or an error message have been already shown
                if self.cliargs.non_interactive and self.retcode in (0, 100):
                    self._show_success_dialog()
        elif self.summary_page.is_visible:
            self._restart_phase()

    def _restart_phase(self, show_only_error: bool = True):
        self.main_window.hide()
        self.log.debug("Hide main window")
        # ensuring that main_window will be hidden
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.summary_page.restart_selected_vms(show_only_error)
        if self.summary_page.status.is_error():
            self.retcode = self.summary_page.status.value
        self.exit_updater()

    def _show_success_dialog(self):
        """
        We should show the user a success confirmation.

        In the case of non-interactive mode or if there is nothing to do,
        we should show some feedback to the user.
        """
        non_default_select = any(
            (getattr(self.cliargs, arg)
             for arg in self.cliargs.non_default_select if arg != 'all'))
        msg = "Nothing to do."
        if (
                (  # at least all vms with available updates was updated
                (self.cliargs.all and not self.cliargs.skip)
                or not non_default_select
                )
                and self.retcode in (0, 100)
        ):
            msg = "Qubes OS is up to date."
        elif self.retcode == 0:
            msg = "All selected qubes have been updated."
        elif self.retcode == 100:
            msg = "There are no updates available for the selected Qubes."
        show_dialog_with_icon(
            None,
            l("Success"),
            l(msg),
            buttons=RESPONSES_OK,
            icon_name="qubes-check-yes"
        )

    def cancel_clicked(self, _emitter):
        self.log.debug("Cancel clicked")
        if self.summary_page.is_visible:
            self.progress_page.show()
        elif self.progress_page.is_visible:
            self.cancel_updates()
        else:
            self.exit_updater()

    def cancel_updates(self, *_args, **_kwargs):
        self.log.info("User initialize interruption")
        if self.progress_page.update_thread \
                and self.progress_page.update_thread.is_alive():
            self.progress_page.interrupt_update()
            self.log.info("Update interrupted")
            show_dialog_with_icon(self.main_window, l("Updating cancelled"), l(
                "Waiting for current qube to finish updating."
                " Updates for remaining qubes have been cancelled."),
                                  buttons=RESPONSES_OK, icon_name="qubes-info")

            self.log.debug("Waiting to finish ongoing updates")
            while self.progress_page.update_thread.is_alive():
                while Gtk.events_pending():
                    Gtk.main_iteration()
                time.sleep(0.1)

    def check_escape(self, _widget, event, _data=None):
        if event.keyval == Gdk.KEY_Escape:
            if self.intro_page.is_visible or self.summary_page.is_visible:
                self.window_close()

    def window_close(self, *_args, **_kwargs):
        self.log.debug("Close window")
        if self.progress_page.exit_triggered:
            self.cancel_updates()
        else:
            self.cancel_updates()
            self.exit_updater()

    def exit_updater(self, _emitter=None):
        if self.primary:
            self.log.debug("Exit")
            self.release()


def parse_args(args, app):
    parser = argparse.ArgumentParser()
    try:
        default_update_if_stale = int(app.domains["dom0"].features.get(
            "qubes-vm-update-update-if-stale", Settings.DEFAULT_UPDATE_IF_STALE)
        )
    except qubesadmin.exc.QubesDaemonAccessError:
        default_update_if_stale = Settings.DEFAULT_UPDATE_IF_STALE

    parser.add_argument('--log', action='store', default='WARNING',
                        help='Provide logging level. Values: DEBUG, INFO, '
                             'WARNING (default), ERROR, CRITICAL')

    parser.add_argument('--max-concurrency', action='store',
                        help='Maximum number of VMs configured simultaneously '
                             '(default: number of cpus)',
                        type=int)
    parser.add_argument(
        '--signal-no-updates', action='store_true',
        help='Return exit code 100 instread of 0 '
             'if there is no updates available.')

    restart = parser.add_mutually_exclusive_group()
    restart.add_argument(
        '--apply-to-sys', '--restart', '-r',
        action='store_true',
        help='Restart not updated ServiceVMs whose template has been updated.')
    restart.add_argument(
        '--apply-to-all', '-R', action='store_true',
        help='Restart not updated ServiceVMs and shutdown not updated AppVMs '
             'whose template has been updated.')
    restart.add_argument(
        '--no-apply', action='store_true',
        help='DEFAULT. Do not restart/shutdown any AppVMs.')

    update_state = parser.add_mutually_exclusive_group()
    update_state.add_argument(
        '--force-update', action='store_true',
        help='Attempt to update all targeted VMs '
             'even if no updates are available')
    update_state.add_argument(
        '--update-if-stale', action='store',
        help='DEFAULT. '
             'Attempt to update targeted VMs with known updates available '
             'or for which last update check was more than N days ago. '
             '(default: %(default)d)',
        type=int, default=default_update_if_stale)
    update_state.add_argument(
        '--update-if-available', action='store_true',
        help='Update targeted VMs with known updates available.')

    parser.add_argument(
        '--skip', action='store',
        help='Comma separated list of VMs to be skipped, '
             'works with all other options. '
             'If present, skip manual selection of qubes to update.',
        default="")
    parser.add_argument(
        '--targets', action='store',
        help='Comma separated list of updatable VMs to target. '
             'If present, skip manual selection of qubes to update.')
    parser.add_argument(
        '--templates', '-T', action='store_true',
        help='Target all updatable TemplateVMs. '
             'If present, skip manual selection of qubes to update.')
    parser.add_argument(
        '--standalones', '-S', action='store_true',
        help='Target all updatable StandaloneVMs. '
             'If present, skip manual selection of qubes to update.')
    parser.add_argument(
        '--all', action='store_true',
        help='DEFAULT. Target AdminVM, TemplateVMs and StandaloneVMs.'
             'Use explicitly with "--targets" to include both. '
             'If explicitly present, skip manual selection of qubes to update.')
    parser.add_argument(
        '--dom0', action='store_true', help='Target dom0. '
        'If present, skip manual selection of qubes to update.')

    parser.add_argument('--non-interactive', '-n', action='store_true',
                        help='Run the updater GUI in non-interactive mode. '
                             'Interaction will be required in the event '
                             'of an update error.')

    args = parser.parse_args(args)

    args.non_default_select = {
        'skip', 'targets', 'templates', 'standalones', 'all', 'dom0'}

    if args.update_if_stale < 0:
        raise ArgumentError("Wrong value for --update-if-stale")
    if args.update_if_stale == default_update_if_stale:
        args.update_if_stale = None

    return args


def skip_intro_if_args(args):
    auto_select = [getattr(args, arg) for arg in args.non_default_select
                   ] + [args.non_interactive]
    return any(auto_select)


def main(args=None):
    qapp = Qubes()
    cliargs = parse_args(args, qapp)
    app = QubesUpdater(qapp, cliargs)
    app.run()
    if app.retcode == 100 and not app.cliargs.signal_no_updates:
        app.retcode = 0
    sys.exit(app.retcode)


if __name__ == '__main__':
    main()
