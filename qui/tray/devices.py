# pylint: disable=wrong-import-position,import-error
import asyncio
import sys
import time
import traceback

import gi
gi.require_version('Gdk', '3.0')  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
gi.require_version('AppIndicator3', '0.1')  # isort:skip
from gi.repository import Gdk, Gtk, Gio  # isort:skip

import qubesadmin
import qubesadmin.events
import qubesadmin.devices
import qubesadmin.exc
import qui.decorators

import gbulb
gbulb.install()

import gettext
t = gettext.translation("desktop-linux-manager", localedir="/usr/locales",
                        fallback=True)
_ = t.gettext

DEV_TYPES = ['block', 'usb', 'mic']


def wait_for_condition(func, seconds=1):
    """
    Waits up to `seconds` seconds for the given function to return truth.

    Executes the function every tenth of a second until it returns a
    truthy value.
    """
    delay = 0.1
    i = 0
    while i < seconds / delay:
        if func():
            break
        time.sleep(0.1)
        i += 1


class DomainMenuItem(Gtk.ImageMenuItem):
    """ A submenu item for the device menu. Displays attachment status.
     Allows attaching/detaching the device."""

    def __init__(self, device, vm, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.vm = vm

        self.device = device

        icon = self.vm.icon
        self.set_image(qui.decorators.create_icon(icon))
        self._hbox = qui.decorators.device_domain_hbox(self.vm, self.attached)
        self.add(self._hbox)

    @property
    def attached(self):
        return str(self.vm) in self.device.attachments


class DomainMenu(Gtk.Menu):
    def __init__(self, device, domains, qapp, gtk_app, **kwargs):
        super(DomainMenu, self).__init__(**kwargs)
        self.device = device
        self.domains = domains
        self.qapp = qapp
        self.gtk_app = gtk_app

        for vm in self.domains:
            if vm != device.backend_domain:
                menu_item = DomainMenuItem(self.device, vm)
                menu_item.connect('activate', self.toggle)
                self.append(menu_item)

    def toggle(self, menu_item):
        if menu_item.attached:
            self.detach_item()
        else:
            self.attach_item(menu_item)

    def attach_item(self, menu_item):
        detach_successful = self.detach_item()

        if not detach_successful:
            return

        try:
            assignment = qubesadmin.devices.DeviceAssignment(
                self.device.backend_domain, self.device.ident, persistent=False)

            vm_to_attach = self.qapp.domains[str(menu_item.vm)]
            vm_to_attach.devices[menu_item.device.devclass].attach(assignment)

            self.gtk_app.emit_notification(
                _("Attaching device"),
                _("Attaching {} to {}").format(self.device.description,
                                               menu_item.vm),
                Gio.NotificationPriority.NORMAL,
                notification_id=self.device.backend_domain + self.device.ident)
        except Exception as ex:  # pylint: disable=broad-except
            self.gtk_app.emit_notification(
                _("Error"),
                _("Attaching device {0} to {1} failed. "
                  "Error: {2} - {3}").format(
                    self.device.description, menu_item.vm, type(ex).__name__,
                    ex),
                Gio.NotificationPriority.HIGH,
                error=True,
                notification_id=self.device.backend_domain + self.device.ident)
            traceback.print_exc(file=sys.stderr)

    def detach_item(self):
        for vm in self.device.attachments:
            self.gtk_app.emit_notification(
                _("Detaching device"),
                _("Detaching {} from {}").format(self.device.description, vm),
                Gio.NotificationPriority.NORMAL,
                notification_id=self.device.backend_domain + self.device.ident)
            try:
                assignment = qubesadmin.devices.DeviceAssignment(
                    self.device.backend_domain, self.device.ident,
                    persistent=False)
                self.qapp.domains[vm].devices[self.device.devclass].detach(
                    assignment)

                def device_is_removed():
                    domain = self.qapp.domains[vm]
                    domain_devices = domain.devices[self.device.devclass]
                    return self.device not in domain_devices.attached()

                wait_for_condition(device_is_removed, 3)

            except qubesadmin.exc.QubesException as ex:
                self.gtk_app.emit_notification(
                    _("Error"),
                    _("Detaching device {0} from {1} failed. "
                      "Error: {2}").format(self.device.description, vm, ex),
                    Gio.NotificationPriority.HIGH,
                    error=True,
                    notification_id=(self.device.backend_domain +
                                     self.device.ident))
                return False
        return True


class DeviceItem(Gtk.ImageMenuItem):
    """ MenuItem showing the device data and a :class:`DomainMenu`. """

    def __init__(self, device, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.device = device

        self.hbox = qui.decorators.device_hbox(self.device)  # type: Gtk.Box

        self.set_image(qui.decorators.create_icon(self.device.vm_icon))

        self.add(self.hbox)


class Device:
    def __init__(self, dev):
        self.dev_name = str(dev)
        self.ident = dev.ident
        self.description = dev.description
        self.devclass = dev.devclass
        self.attachments = set()
        self.backend_domain = dev.backend_domain.name
        self.vm_icon = dev.backend_domain.label.icon

    def __str__(self):
        return self.dev_name

    def __eq__(self, other):
        return str(self) == str(other)


class VM:
    def __init__(self, vm):
        self.__hash = hash(vm)
        self.vm_name = vm.name
        self.icon = vm.label.icon

    def __str__(self):
        return self.vm_name

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return self.__hash


class DevicesTray(Gtk.Application):
    def __init__(self, app_name, qapp, dispatcher, update_queue):
        super(DevicesTray, self).__init__()
        self.name = app_name

        self.tray_menu = None

        self.devices = {}
        self.vms = set()

        self.dispatcher = dispatcher
        self.qapp = qapp
        self.update_queue = update_queue

        self.set_application_id(self.name)
        self.register()  # register Gtk Application

        self.initialize_vm_data()
        self.initialize_dev_data()

        for devclass in DEV_TYPES:
            self.dispatcher.add_handler('device-attach:' + devclass,
                                        self.device_attached)
            self.dispatcher.add_handler('device-detach:' + devclass,
                                        self.device_detached)
            self.dispatcher.add_handler('device-list-change:' + devclass,
                                        self.device_list_update)

        self.dispatcher.add_handler('domain-shutdown',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start', self.vm_start)
        self.dispatcher.add_handler('property-set:label', self.on_label_changed)

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name('media-removable')
        self.widget_icon.connect('button-press-event', self.show_menu)
        self.widget_icon.set_tooltip_markup(
            _('<b>Qubes Devices</b>\nView and manage devices.'))

    def device_list_update(self, vm, _event, **_kwargs):
        try:
            self.update_queue.put_nowait("update_request")
        except asyncio.QueueFull:
            # update requests are already pending, so drop this one
            pass

    def initialize_vm_data(self):
        for vm in self.qapp.domains:
            if vm.klass != 'AdminVM' and vm.is_running():
                self.vms.add(VM(vm))

    def initialize_dev_data(self):
        updated_devices = {}

        # list all devices
        for domain in self.qapp.domains:
            if not domain.is_running():
                continue

            for devclass in DEV_TYPES:
                for device in domain.devices[devclass]:
                    devname = str(device)
                    if devname not in updated_devices:
                        dev = Device(device)
                        updated_devices[devname] = dev

                for device in domain.devices[devclass].attached():
                    devname = str(device)
                    if devname not in updated_devices:
                        dev = Device(device)
                        updated_devices[devname] = dev
                    updated_devices[devname].attachments.add(domain.name)

        previous = set(self.devices.keys())
        current = set(updated_devices.keys())
        removals = previous - current
        for removal in removals:
            self.emit_notification(
                _("Device removed"),
                _("Device {} was removed").format(
                    self.devices[removal].description
                ),
                Gio.NotificationPriority.NORMAL,
                notification_id=(
                    self.devices[removal].backend_domain +
                    self.devices[removal].ident
                )
            )

        additions = current - previous
        for addition in additions:
            self.emit_notification(
                _("Device available"),
                _("Device {} is available").format(
                    updated_devices[addition].description),
                Gio.NotificationPriority.NORMAL,
                notification_id=(
                    updated_devices[addition].backend_domain +
                    updated_devices[addition].ident
                )
            )

        self.devices = updated_devices
        self.populate_menu()

    def device_attached(self, vm, _event, device, **_kwargs):
        if not vm.is_running() or device.devclass not in DEV_TYPES:
            return

        if str(device) not in self.devices:
            self.devices[str(device)] = Device(device)

        self.devices[str(device)].attachments.add(str(vm))

    def device_detached(self, vm, _event, device, **_kwargs):
        if not vm.is_running():
            return

        device = str(device)

        if device in self.devices:
            self.devices[device].attachments.discard(str(vm))

    def vm_start(self, vm, _event, **_kwargs):
        self.vms.add(VM(vm))
        for devclass in DEV_TYPES:
            for device in vm.devices[devclass].attached():
                dev = str(device)
                if dev in self.devices:
                    self.devices[dev].attachments.add(vm.name)

    def vm_shutdown(self, vm, _event, **_kwargs):
        self.vms.discard(vm)

        for dev in self.devices.values():
            dev.attachments.discard(str(vm))

    def on_label_changed(self, vm, _event, **_kwargs):
        if not vm:  # global properties changed
            return
        try:
            name = vm.name
        except qubesadmin.exc.QubesPropertyAccessError:
            return  # the VM was deleted before its status could be updated

        for domain in self.vms:
            if domain.name == name:
                domain.icon = vm.label.icon

        for device in self.devices:
            if device.backend_domain == name:
                device.vm_icon = vm.label.icon

    def populate_menu(self):
        if self.tray_menu is None:
            self.tray_menu = Gtk.Menu()
            self.tray_menu.menu_type_hint = Gdk.WindowTypeHint.POPUP_MENU

        for c in self.tray_menu.get_children():
            self.tray_menu.remove(c)

        # create menu items
        menu_items = []
        sorted_vms = sorted(self.vms)
        for dev in self.devices.values():
            domain_menu = DomainMenu(dev, sorted_vms, self.qapp, self)
            device_menu = DeviceItem(dev)
            device_menu.set_submenu(domain_menu)
            menu_items.append(device_menu)

        menu_items.sort(key=(lambda x: x.device.devclass + str(x.device)))

        for i, item in enumerate(menu_items):
            if i > 0 and item.device.devclass != \
                    menu_items[i-1].device.devclass:
                self.tray_menu.add(Gtk.SeparatorMenuItem())
            self.tray_menu.add(item)
        self.tray_menu.show_all()
        self.tray_menu.reposition()

    def show_menu(self, _unused, _event):
        self.populate_menu()
        self.tray_menu.popup_at_pointer()
        self.tray_menu.reposition()

    def emit_notification(self, title, message, priority, error=False,
                          notification_id=None):
        notification = Gio.Notification.new(title)
        notification.set_body(message)
        notification.set_priority(priority)
        if error:
            notification.set_icon(Gio.ThemedIcon.new('dialog-error'))
        self.send_notification(notification_id, notification)


async def updater(app: DevicesTray, queue: asyncio.Queue):
    while True:
        await queue.get()
        count = 1
        try:
            while queue.get_nowait():
                # pop extra update requests
                count += 1
        except asyncio.QueueEmpty:
            # queue emptied
            pass

        app.initialize_dev_data()
        while count > 0:
            queue.task_done()
            count -= 1


def main():
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)

    update_queue = asyncio.Queue()

    app = DevicesTray(
        'org.qubes.qui.tray.Devices', qapp, dispatcher, update_queue)

    loop = asyncio.get_event_loop()

    worker = loop.create_task(updater(app, update_queue))

    done, _unused = loop.run_until_complete(asyncio.ensure_future(
        dispatcher.listen_for_events()))

    worker.cancel()

    exit_code = 0
    for d in done:  # pylint: disable=invalid-name
        try:
            d.result()
        except Exception:  # pylint: disable=broad-except
            exc_type, exc_value = sys.exc_info()[:2]
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK)
            dialog.set_title(_("Houston, we have a problem..."))
            dialog.set_markup(_(
                "<b>Whoops. A critical error in Devices Widget has occurred.</b>"
                " This is most likely a bug in the widget. To restart the "
                "widget, run 'qui-devices' in dom0."))
            dialog.format_secondary_markup(
                "\n<b>{}</b>: {}\n{}".format(
                   exc_type.__name__, exc_value, traceback.format_exc(limit=10)
                ))
            dialog.run()
            exit_code = 1
    del app
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
