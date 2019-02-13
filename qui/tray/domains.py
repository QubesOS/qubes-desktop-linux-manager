#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position,import-error
''' A menu listing domains '''
import asyncio
import subprocess
import sys
import os
import traceback

import qubesadmin
import qubesadmin.events

from qubesadmin import exc

import qui.decorators
import gi  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gio, Gtk  # isort:skip

import gbulb
gbulb.install()



class PauseItem(Gtk.ImageMenuItem):
    ''' Shutdown menu Item. When activated pauses the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-playback-pause', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Pause')

        self.connect('activate', self.perform_pause)

    def perform_pause(self, *_args, **_kwargs):
        self.vm.pause()


class UnpauseItem(Gtk.ImageMenuItem):
    ''' Unpause menu Item. When activated unpauses the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-playback-start', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Unpause')

        self.connect('activate', self.perform_unpause)

    def perform_unpause(self, *_args, **_kwargs):
        self.vm.unpause()


class ShutdownItem(Gtk.ImageMenuItem):
    ''' Shutdown menu Item. When activated shutdowns the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-playback-stop', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Shutdown')

        self.connect('activate', self.perform_shutdown)

    def perform_shutdown(self, *_args, **_kwargs):
        self.vm.shutdown()


class KillItem(Gtk.ImageMenuItem):
    ''' Kill domain menu Item. When activated kills the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-record', 16, 0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Kill')

        self.connect('activate', self.perform_kill)

    def perform_kill(self, *_args, **_kwargs):
        self.vm.kill()


class PreferencesItem(Gtk.ImageMenuItem):
    ''' Preferences menu Item. When activated shows preferences dialog '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm
        icon = Gtk.IconTheme.get_default().load_icon('preferences-system', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Preferences')

        self.connect('activate', self.launch_preferences_dialog)

    def launch_preferences_dialog(self, _item):
        subprocess.Popen(['qubes-vm-settings', self.vm.name])


class LogItem(Gtk.ImageMenuItem):
    def __init__(self, name, path):
        super().__init__()
        self.path = path

        image = Gtk.Image.new_from_file(
            "/usr/share/icons/HighContrast/16x16/apps/logviewer.png")

        self.set_image(image)
        self.set_label(name)

        self.connect('activate', self.launch_log_viewer)

    def launch_log_viewer(self, *_args, **_kwargs):
        subprocess.Popen(['qubes-log-viewer', self.path])


class RunTerminalItem(Gtk.ImageMenuItem):
    ''' Run Terminal menu Item. When activated runs a terminal emulator. '''
    def __init__(self, vm):
        super().__init__()
        self.vm = vm
        icon = Gtk.IconTheme.get_default().load_icon('utilities-terminal', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Run Terminal')

        self.connect('activate', self.run_terminal)

    def run_terminal(self, _item):
        self.vm.run_service('qubes.StartApp+qubes-run-terminal')


class StartedMenu(Gtk.Menu):
    ''' The sub-menu for a started domain'''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.add(PreferencesItem(self.vm))
        self.add(PauseItem(self.vm))
        self.add(ShutdownItem(self.vm))
        self.add(RunTerminalItem(self.vm))


class PausedMenu(Gtk.Menu):
    ''' The sub-menu for a paused domain'''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.add(PreferencesItem(self.vm))
        self.add(UnpauseItem(self.vm))
        self.add(KillItem(self.vm))
        self.add(RunTerminalItem(self.vm))


class DebugMenu(Gtk.Menu):
    ''' Sub-menu providing multiple MenuItem for domain logs. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.add(PreferencesItem(self.vm))

        logs = [
            ("Console Log", "/var/log/xen/console/guest-" + vm.name + ".log"),
            ("QEMU Console Log",
             "/var/log/xen/console/guest-" + vm.name + "-dm.log"),
            ]

        for name, path in logs:
            if os.path.isfile(path):
                self.add(LogItem(name, path))

        self.add(KillItem(self.vm))


class DomainMenuItem(Gtk.ImageMenuItem):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.decorator = qui.decorators.DomainDecorator(vm)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.name = self.decorator.name()
        hbox.pack_start(self.name, True, True, 0)

        self.spinner = Gtk.Spinner()
        hbox.pack_start(self.spinner, False, True, 0)

        self.memory = self.decorator.memory()
        hbox.pack_start(self.memory, False, True, 0)

        self.add(hbox)

        self.update_state(self.vm.get_power_state())
        self._set_image()

    def _set_image(self):
        self.set_image(self.decorator.icon())

    def _set_submenu(self, state):
        if state == 'Running':
            submenu = StartedMenu(self.vm)
        elif state == 'Paused':
            submenu = PausedMenu(self.vm)
        else:
            submenu = DebugMenu(self.vm)
        # This is a workaround for a bug in Gtk which occurs when a
        # submenu is replaced while it is open.
        # see https://bugzilla.redhat.com/show_bug.cgi?id=1435911
        current_submenu = self.get_submenu()
        if current_submenu:
            current_submenu.grab_remove()
        self.set_submenu(submenu)

    def show_spinner(self):
        self.spinner.start()
        self.spinner.set_no_show_all(False)
        self.spinner.show()
        self.show_all()

    def hide_spinner(self):
        self.spinner.stop()
        self.spinner.set_no_show_all(True)
        self.spinner.hide()

    def update_state(self, state):
        if state in ['Running', 'Paused']:
            self.hide_spinner()
        else:
            self.show_spinner()
        colormap = {'Paused': 'grey', 'Crashed': 'red', 'Transient': 'red'}
        if state in colormap:
            self.name.set_markup('<span color=\'{}\'>{}</span>'.format(
                colormap[state], self.vm.name))
        else:
            self.name.set_label(self.vm.name)
        self._set_submenu(state)

    def update_stats(self, memory_kb, cpu_usage):
        text = '{0} MB, CPU:{1}%'.format(int(memory_kb)//1024, cpu_usage)
        self.memory.set_text(text)


class DomainTray(Gtk.Application):
    ''' A tray icon application listing all but halted domains. ” '''

    def __init__(self, app_name, qapp, dispatcher, stats_dispatcher):
        super().__init__()
        self.qapp = qapp
        self.dispatcher = dispatcher
        self.stats_dispatcher = stats_dispatcher

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name('qubes-logo-icon')
        self.widget_icon.connect('button-press-event', self.show_menu)
        self.widget_icon.set_tooltip_markup(
            '<b>Qubes Domains</b>\nView and manage running domains.')

        self.tray_menu = Gtk.Menu()

        self.menu_items = {}

        self.unpause_all_action = Gio.SimpleAction.new('do-unpause-all', None)
        self.unpause_all_action.connect('activate', self.do_unpause_all)
        self.add_action(self.unpause_all_action)
        self.pause_notification_out = False

        self.register_events()
        self.set_application_id(app_name)
        self.register()  # register Gtk Application

    def register_events(self):
        self.dispatcher.add_handler('domain-pre-start', self.update_domain_item)
        self.dispatcher.add_handler('domain-start', self.update_domain_item)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.remove_domain_item)
        self.dispatcher.add_handler('domain-paused', self.update_domain_item)
        self.dispatcher.add_handler('domain-unpaused', self.update_domain_item)
        self.dispatcher.add_handler('domain-stopped', self.update_domain_item)
        self.dispatcher.add_handler('domain-shutdown', self.remove_domain_item)

        self.dispatcher.add_handler('domain-pre-start', self.emit_notification)
        self.dispatcher.add_handler('domain-start', self.emit_notification)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.emit_notification)
        self.dispatcher.add_handler('domain-pre-shutdown',
                                    self.emit_notification)
        self.dispatcher.add_handler('domain-shutdown', self.emit_notification)

        self.dispatcher.add_handler('domain-start', self.check_pause_notify)
        self.dispatcher.add_handler('domain-paused', self.check_pause_notify)
        self.dispatcher.add_handler('domain-unpaused', self.check_pause_notify)
        self.dispatcher.add_handler('domain-stopped', self.check_pause_notify)
        self.dispatcher.add_handler('domain-shutdown', self.check_pause_notify)

        self.stats_dispatcher.add_handler('vm-stats', self.update_stats)

    def show_menu(self, _, event):
        menu = Gtk.Menu()
        for vm in sorted(self.menu_items):
            self.tray_menu.remove(self.menu_items[vm])
            menu.add(self.menu_items[vm])
        menu.show_all()
        self.tray_menu = menu

        self.tray_menu.popup(None,  # parent_menu_shell
                             None,  # parent_menu_item
                             None,  # func
                             None,  # data
                             event.button,  # button
                             Gtk.get_current_event_time())  # activate_time

    def emit_notification(self, vm, event, **kwargs):
        notification = Gio.Notification.new("Qube Status: {}". format(vm.name))
        notification.set_priority(Gio.NotificationPriority.NORMAL)

        if event == 'domain-start-failed':
            notification.set_body('Domain {} has failed to start: {}'.format(
                vm.name, kwargs['reason']))
            notification.set_priority(Gio.NotificationPriority.HIGH)
            notification.set_icon(
                Gio.ThemedIcon.new('dialog-warning'))
        elif event == 'domain-pre-start':
            notification.set_body('Domain {} is starting.'.format(vm.name))
        elif event == 'domain-start':
            notification.set_body('Domain {} has started.'.format(vm.name))
        elif event == 'domain-pre-shutdown':
            notification.set_body('Domain {} is halting.'.format(vm.name))
        elif event == 'domain-shutdown':
            notification.set_body('Domain {} has halted.'.format(vm.name))
        else:
            return
        self.send_notification(None, notification)

    def emit_paused_notification(self):
        if not self.pause_notification_out:
            notification = Gio.Notification.new("Your VMs have been paused!")
            notification.set_body(
                "All your VMs are currently paused. If this was an accident, "
                "simply click \"Unpause All\" to un-pause them. Otherwise, "
                "you can un-pause individual VMs via the Qubes Domains "
                "tray menu.")
            notification.set_icon(
                Gio.ThemedIcon.new('dialog-warning'))
            notification.add_button('Unpause All', 'app.do-unpause-all')
            notification.set_priority(Gio.NotificationPriority.HIGH)
            self.send_notification('vms-paused', notification)
            self.pause_notification_out = True

    def withdraw_paused_notification(self):
        if self.pause_notification_out:
            self.withdraw_notification('vms-paused')
            self.pause_notification_out = False

    def do_unpause_all(self, _vm, *_args, **_kwargs):
        for vm_name in self.menu_items:
            self.qapp.domains[vm_name].unpause()

    def check_pause_notify(self, _vm, _event, **_kwargs):
        if self.have_running_and_all_are_paused():
            self.emit_paused_notification()
        else:
            self.withdraw_paused_notification()

    def have_running_and_all_are_paused(self):
        found_paused = False
        for vm in self.qapp.domains:
            if vm.klass != 'AdminVM':
                if vm.is_running():
                    if vm.is_paused():
                        # a running that is paused
                        found_paused = True
                    else:
                        # found running that wasn't paused
                        return False
        return found_paused

    def add_domain_item(self, vm, _event, **_kwargs):
        # check if it already exists
        if vm in self.menu_items:
            return
        domain_item = DomainMenuItem(vm)
        position = 0
        for i in self.tray_menu:  # pylint: disable=not-an-iterable
            if i.vm.name > vm.name:
                break
            position += 1
        self.tray_menu.insert(domain_item, position)
        self.menu_items[vm] = domain_item

    def remove_domain_item(self, vm, _event, **_kwargs):
        ''' Remove the menu item for the specified domain from the tray'''
        if vm not in self.menu_items:
            return
        vm_widget = self.menu_items[vm]
        self.tray_menu.remove(vm_widget)
        del self.menu_items[vm]

    def update_domain_item(self, vm, event, **kwargs):
        ''' Update the menu item with the started menu for
        the specified vm in the tray'''
        try:
            if vm not in self.menu_items:
                self.add_domain_item(vm, None)
            self.menu_items[vm].update_state(vm.get_power_state())
        except exc.QubesPropertyAccessError:
            self.remove_domain_item(vm, event, **kwargs)

    def update_stats(self, vm, _event, **kwargs):
        if vm not in self.menu_items:
            return
        self.menu_items[vm].update_stats(kwargs['memory_kb'],
                kwargs['cpu_usage'])

    def initialize_menu(self):
        for vm in self.qapp.domains:
            if vm.is_running() and vm.klass != 'AdminVM':
                self.add_domain_item(vm, None)
        self.connect('shutdown', self._disconnect_signals)

    def run(self):  # pylint: disable=arguments-differ
        self.initialize_menu()

    def _disconnect_signals(self, _):
        self.dispatcher.remove_handler('domain-pre-start', self.add_domain_item)
        self.dispatcher.remove_handler('domain-start', self.update_domain_item)
        self.dispatcher.remove_handler('domain-start-failed',
                                       self.update_domain_item)
        self.dispatcher.remove_handler('domain-stopped',
                                       self.update_domain_item)
        self.dispatcher.remove_handler('domain-shutdown',
                                       self.remove_domain_item)

        self.dispatcher.remove_handler('domain-pre-start',
                                       self.emit_notification)
        self.dispatcher.remove_handler('domain-start', self.emit_notification)
        self.dispatcher.remove_handler('domain-start-failed',
                                       self.emit_notification)
        self.dispatcher.remove_handler('domain-stopped', self.emit_notification)
        self.dispatcher.remove_handler('domain-shutdown',
                                       self.emit_notification)


def main():
    ''' main function '''
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    stats_dispatcher = qubesadmin.events.EventsDispatcher(
        qapp, api_method='admin.vm.Stats')
    app = DomainTray(
        'org.qubes.qui.tray.Domains', qapp, dispatcher, stats_dispatcher)
    app.run()

    loop = asyncio.get_event_loop()
    tasks = [
        asyncio.ensure_future(dispatcher.listen_for_events()),
        asyncio.ensure_future(stats_dispatcher.listen_for_events()),
    ]

    done, _ = loop.run_until_complete(asyncio.wait(
            tasks, return_when=asyncio.FIRST_EXCEPTION))

    for d in done:  # pylint: disable=invalid-name
        try:
            d.result()
        except Exception as _ex:  # pylint: disable=broad-except
            exc_type, exc_value = sys.exc_info()[:2]
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK)
            dialog.set_title("Houston, we have a problem...")
            dialog.set_markup(
                "<b>Whoops. A critical error in Domains Widget has occured.</b>"
                " This is most likely a bug in the widget. To restart the "
                "widget, run 'qui-domains' in dom0.")
            dialog.format_secondary_markup(
                "\n<b>{}</b>: {}\n{}".format(
                   exc_type.__name__, exc_value, traceback.format_exc(limit=10)
                ))
            dialog.run()


if __name__ == '__main__':
    sys.exit(main())
