#!/usr/bin/env python3
# -*- coding: utf-8 -*-
''' A menu listing domains '''

import signal
import subprocess
import sys
from enum import Enum

import dbus
import dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# pylint: disable=wrong-import-position
import qui.decorators

from qui.models.qubes import DomainManager

import gi  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import GObject, Gtk  # isort:skip

gi.require_version('AppIndicator3', '0.1')  # isort:skip
from gi.repository import AppIndicator3 as appindicator  # isort:skip

DOMAIN_MANAGER_INTERFACE = "org.qubes.DomainManager1"
DOMAIN_MANAGER_PATH = "/org/qubes/DomainManager1"
DBusSignalMatch = dbus.connection.SignalMatch


class STATE(Enum):
    FAILED = 1
    TRANSIENT = 2
    RUNNING = 3


def vm_label(decorator):
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    hbox.pack_start(decorator.icon(), False, True, 0)
    hbox.pack_start(decorator.name(), True, True, 0)
    hbox.pack_start(decorator.memory(), False, True, 0)
    return hbox


def sub_menu_hbox(name, image_name=None) -> Gtk.Widget:
    icon = Gtk.IconTheme.get_default().load_icon(image_name, 16, 0)
    image = Gtk.Image.new_from_pixbuf(icon)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    hbox.pack_start(image, False, False, 0)
    hbox.pack_start(Gtk.Label(name), True, False, 0)
    return hbox


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

        self.connect('activate', self.vm.Shutdown)


class KillItem(Gtk.ImageMenuItem):
    ''' Kill domain menu Item. When activated kills the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-record', 16, 0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Kill')

        self.connect('activate', self.vm.Kill)


class PreferencesItem(Gtk.ImageMenuItem):
    ''' TODO: Preferences menu Item. When activated shows preferences dialog '''

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
        subprocess.call(['qubes-vm-settings', self.vm['name']])


class LogItem(Gtk.ImageMenuItem):
    def __init__(self, vm, name, callback=None):
        super().__init__()
        image = Gtk.Image.new_from_file(
            "/usr/share/icons/HighContrast/16x16/apps/logviewer.png")

        decorator = qui.decorators.DomainDecorator(vm)
        self.set_image(image)
        self.set_label(name)
        if callback:
            self.connect('activate', callback)


class StartedMenu(Gtk.Menu):
    ''' The sub-menu for a started domain'''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        preferences = PreferencesItem(self.vm)
        shutdown_item = ShutdownItem(self.vm)

        self.add(preferences)
        self.add(shutdown_item)


class DebugMenu(Gtk.Menu):
    ''' Sub-menu providing multiple MenuItem for domain logs. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm
        console = LogItem(self.vm, "Console Log")
        guid = LogItem(self.vm, "GUI Daemon Log")
        qrexec = LogItem(self.vm, "Qrexec Log")
        kill = KillItem(self.vm)
        preferences = PreferencesItem(self.vm)

        self.add(console)
        self.add(qrexec)
        self.add(guid)
        self.add(preferences)
        self.add(kill)


class DomainMenuItem(Gtk.ImageMenuItem):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.decorator = qui.decorators.DomainDecorator(vm)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.name = self.decorator.name()
        hbox.pack_start(self.name, True, True, 0)

        state = self._state()

        if state not in [STATE.RUNNING, STATE.FAILED]:
            spinner = Gtk.Spinner()
            spinner.start()
            hbox.pack_start(spinner, False, True, 0)

        self.memory = self.decorator.memory()
        hbox.pack_start(self.memory, False, True, 0)
        vm.proxy.connect_to_signal('PropertiesChanged', self._update, dbus_interface='org.freedesktop.DBus.Properties')

        self.add(hbox)

        self._set_submenu(state)
        self._set_image(state)

    def _state(self):
        if self.vm['state'] == 'Started':
            return STATE.RUNNING
        elif self.vm['state'] == 'Failed':
            return STATE.FAILED

        return STATE.TRANSIENT

    def _set_image(self, state):
        if state == STATE.FAILED:
            failed_pixbuf = Gtk.IconTheme.get_default().load_icon(
                'media-record', 16, 0)
            failed_image = Gtk.Image.new_from_pixbuf(failed_pixbuf)
            self.set_image(failed_image)
        else:
            self.set_image(self.decorator.icon())

    def _set_submenu(self, state):
        if state == STATE.RUNNING:
            submenu = StartedMenu(self.vm)
        elif state == STATE.FAILED:
            submenu = DebugMenu(self.vm)
            remove = Gtk.MenuItem("Remove")
            remove.connect('activate', lambda: self.hide)
        else:
            submenu = DebugMenu(self.vm)
        self.set_submenu(submenu)


    def _update(self, _, changed_properties, invalidated=None):
        if 'memory_usage' in changed_properties:
            text = str(int(changed_properties['memory_usage']/1024)) + ' MB'
            self.memory.set_text(text)

        if 'label' in changed_properties:
            self.set_image(self.decorator.icon())

class DomainTray(Gtk.Application):
    ''' A tray icon application listing all but halted domains. ” '''

    def __init__(self, app_name):
        super().__init__()
        self.name = app_name
        self.tray_menu = Gtk.Menu()
        self.ind = indicator(self.tray_menu)
        self.domain_manager = DomainManager()
        self.signal_matches = {
        }  # type: Dict[dbus.ObjectPath, List[DBusSignalMatch]]
        self.menu_items = {}  # type: Dict[dbus.ObjectPath, Gtk.MenuItem]

        self.signal_callbacks = {
            'Starting': self.update_domain_item,
            'Started': self.update_domain_item,
            'Failed': self.update_domain_item,
            'Halting': self.update_domain_item,
            'Halted': self.remove_menu,
            'Unknown': self.update_domain_item,
        }

    def remove_menu(self, _, vm_path):
        ''' Remove the menu item for the specified domain from the tray'''
        vm_widget = self.menu_items[vm_path]
        self.tray_menu.remove(vm_widget)
        del self.menu_items[vm_path]

    def update_domain_item(self, _, vm_path):
        ''' Add/Replace the menu item with the started menu for the specified vm in the tray'''
        if vm_path in self.menu_items:
            self.remove_menu(None, vm_path)

        vm = self.domain_manager.children[vm_path]
        domain_item = DomainMenuItem(vm)
        subprocess.call([
            'notify-send',
            "Domain %s is %s" % (vm['name'], str(vm['state']).lower())
        ])

        position=0
        for i in self.tray_menu:
            if i.vm['name']>vm['name']:
                break
            position += 1
            
        self.tray_menu.insert(domain_item,position)
        self.menu_items[vm_path] = domain_item
        self.tray_menu.show_all()

    def run(self):  # pylint: disable=arguments-differ
        for signal_name, handler_function in self.signal_callbacks.items():
            matcher = self.domain_manager.connect_to_signal(
                signal_name, handler_function)

            if signal_name not in self.signal_matches:
                self.signal_matches[signal_name] = list()

            self.signal_matches[signal_name] += [matcher]

        for vm_path, vm in self.domain_manager.children.items():
            if vm['name'] == 'dom0' or vm['state'] == 'Halted':
                continue
            else:
                self.update_domain_item(DOMAIN_MANAGER_INTERFACE, vm_path)

        self.connect('shutdown', self._disconnect_signals)
        Gtk.main()

    def _disconnect_signals(self, _):
        for matchers in self.signal_matches.values():
            for matcher in matchers:
                self.domain_manager.disconnect_signal(matcher)


def indicator(tray_menu: Gtk.Menu) -> appindicator.Indicator:
    '''Helper function to setup the indicator object'''
    ind = appindicator.Indicator.new(
        'Qubes Widget', "qubes-logo-icon",
        appindicator.IndicatorCategory.SYSTEM_SERVICES)
    ind.set_menu(tray_menu)
    ind.set_status(appindicator.IndicatorStatus.ACTIVE)
    return ind


def main():
    ''' main function '''
    app = DomainTray('org.qubes.ui.tray.Domains')
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
