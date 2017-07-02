# pylint: disable=missing-docstring
import signal
import sys

import qubesadmin
import qubesadmin.vm

import gi  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk  # isort:skip pylint:

gi.require_version('AppIndicator3', '0.1')  # isort:skip
from gi.repository import AppIndicator3 as appindicator  # isort:skip


class RadioNone(Gtk.RadioMenuItem):
    def __init__(self, active_vm=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(self.name('None'), True, True, 0)
        hbox.set_margin_right(10)
        self.add(hbox)
        active = active_vm is None
        self.set_active(active)

    @staticmethod
    def name(s):
        label = Gtk.Label(str(s), xalign=0)
        label.set_margin_left(32)
        return label


class IconMenuItem(Gtk.MenuItem):
    def __init__(self, label, icon, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(self.icon(icon), False, True, 0)
        hbox.pack_start(self.name(label), True, True, 0)
        hbox.set_margin_right(10)
        self.add(hbox)

    @staticmethod
    def name(s):
        label = Gtk.Label(str(s), xalign=0)
        set_margins(label)
        return label

    @staticmethod
    def icon(s):
        icon_vm = Gtk.IconTheme.get_default().load_icon(s, 22, 0)
        icon_img = Gtk.Image.new_from_pixbuf(icon_vm)
        set_margins(icon_img)
        return icon_img


class RadioIconMenuItem(Gtk.RadioMenuItem):
    def __init__(self, label, icon, active=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(self.icon(icon), False, True, 0)
        hbox.pack_start(self.name(label), True, True, 0)
        hbox.set_margin_right(10)
        self.add(hbox)
        self.set_active(active)

    @staticmethod
    def name(s):
        label = Gtk.Label(str(s), xalign=0)
        set_margins(label)
        return label

    @staticmethod
    def icon(s):
        icon_vm = Gtk.IconTheme.get_default().load_icon(s, 22, 0)
        icon_img = Gtk.Image.new_from_pixbuf(icon_vm)
        set_margins(icon_img)
        return icon_img


class RadioDomainItem(RadioIconMenuItem):
    def __init__(self, vm, active=False):
        label = str(vm)
        icon = vm.label.icon
        super(RadioDomainItem, self).__init__(label, icon, active)


def set_margins(widget):
    widget.set_margin_left(5)
    widget.set_margin_right(5)


class DomainMenu(Gtk.Menu):
    def __init__(self, app, active_vm=None, *args, **kwargs):
        super(DomainMenu, self).__init__(*args, **kwargs)
        self.app = app
        self.active_vm = active_vm
        self.known_domains = {}
        self.append(RadioNone(active_vm))

        for vm in [v for v in app.domains if not v.is_halted()]:
            if not isinstance(vm, qubesadmin.vm.AdminVM):
                self.add(vm)
                self.known_domains[vm.qid] = vm

    def add(self, vm, *args, **kwargs):
        if isinstance(vm, qubesadmin.vm.QubesVM):
            label = str(vm)
            icon = vm.label.icon
            b_act = (label == self.active_vm)
            row = RadioIconMenuItem(label, icon, b_act)
            super(DomainMenu, self).append(row, *args, **kwargs)
        else:
            super(DomainMenu, self).add(vm, *args, **kwargs)


class DeviceMenu(Gtk.Menu):
    def __init__(self, app, *args, **kwargs):
        super(DeviceMenu, self).__init__(*args, **kwargs)
        self.app = app
        self.add_icon_menu_item('Audio Input (None)', 'audio-input-microphone')
        self.add_icon_menu_item('sdd WDC_WD10EZEX-08M2NA0 (None)', 'drive-harddisk')
        self.add_icon_menu_item('sde SD_MMC (vault)', 'drive-removable-media', 'vault')

    def add_icon_menu_item(self, label, icon, active=None):
        audio_input  = IconMenuItem(label, icon)
        audio_input.set_submenu(DomainMenu(self.app, active))
        self.append(audio_input)
class DeviceData():
    ''' Wraps all the data needed to display information about a device '''

    def __init__(self, device, dev_type):
        self.backend_domain = device.backend_domain
        self.frontend_domain = None
        self.dev_type = dev_type
        self.vm_icon = self.backend_domain.label.icon
        self.name = "%s:%s" % (self.backend_domain.name, device.ident)
        self.dbus_path = os.path.join('/org/qubes/DomainManager1',
                                      str(self.backend_domain.qid), self.dev_type,
                                      device.ident)

        if self.dev_type == 'block':
            self.icon = 'drive-removable-media'
        else:
            self.icon = 'network-wired-symbolic'

        for vm in QUBES_APP.domains:
            try:
                if device in vm.devices[dev_type].attached():
                    self.frontend_domain = vm
            except qubesadmin.exc.QubesDaemonNoResponseError as exc:
                print(exc, file=sys.stderr)


class DevicesTray(Gtk.Application):
    def __init__(self, app_name='Devices Tray'):
        super(DevicesTray, self).__init__()
        self.name = app_name
        app = qubesadmin.Qubes()
        self.tray = appindicator.Indicator.new(
            'Devices Widget', "gtk-preferences",
            appindicator.IndicatorCategory.SYSTEM_SERVICES)
        self.tray.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.menu = DeviceMenu(app)
        self.menu.show_all()
        self.tray.set_menu(self.menu)

    def run(self):
        Gtk.main()


def create_icon(name):
    icon_dev = Gtk.IconTheme.get_default().load_icon(name, 22, 0)
    return Gtk.Image.new_from_pixbuf(icon_dev)


def main():
    app = DevicesTray()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.run()


if __name__ == '__main__':
    sys.exit(main())
