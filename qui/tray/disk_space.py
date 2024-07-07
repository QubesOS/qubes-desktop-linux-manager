# pylint: disable=wrong-import-position,import-error
import sys
import subprocess
from typing import List

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, GObject, Gio, GLib  # isort:skip
from qubesadmin import Qubes
from qubesadmin.utils import size_to_human
from qubesadmin import exc
from qubesadmin.storage import Pool

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

# TODO: add configurable warning levels
WARN_LEVEL = 0.9
URGENT_WARN_LEVEL = 0.95


class VMUsage:
    def __init__(self, vm):
        self.vm = vm
        self.problem_volumes = {}

        self.check_usage()

    def check_usage(self):
        self.problem_volumes = {}
        volumes_to_check = ['private']
        if not hasattr(self.vm, 'template'):
            volumes_to_check.append('root')
        for volume_name in volumes_to_check:
            try:
                if volume_name in self.vm.volumes:
                    size = self.vm.volumes[volume_name].size
                    usage = self.vm.volumes[volume_name].usage
                    if size > 0 and usage / size > WARN_LEVEL:
                        self.problem_volumes[volume_name] = usage / size
            except exc.QubesDaemonAccessError:
                continue


class VMUsageData:
    def __init__(self, qubes_app):
        self.qubes_app = qubes_app
        self.problematic_vms = []

        self.__populate_vms()

    def __populate_vms(self):
        for vm in self.qubes_app.domains:
            try:
                if vm.is_running():
                    usage_data = VMUsage(vm)
                    if usage_data.problem_volumes:
                        self.problematic_vms.append(usage_data)
            except (exc.QubesPropertyAccessError,
                    exc.QubesVMNotFoundError) :
                continue

    def get_vms_widgets(self):
        for vm_usage in self.problematic_vms:
            yield self.__create_widgets(vm_usage)

    @staticmethod
    def __create_widgets(vm_usage):
        vm = vm_usage.vm

        # icon widget
        try:
            icon = getattr(vm, 'icon', vm.label.icon)
        except exc.QubesPropertyAccessError:
            icon = 'appvm-black'
        icon_vm = Gtk.IconTheme.get_default().load_icon(icon, 16, 0)
        icon_img = Gtk.Image.new_from_pixbuf(icon_vm)

        # description widget
        label_widget = Gtk.Label(xalign=0)

        label_contents = []

        for volume_name, usage in vm_usage.problem_volumes.items():
            # pylint: disable=consider-using-f-string
            label_contents.append(_('volume <b>{}</b> is {:.1%} full').format(
                volume_name, usage))

        label_text = f"<b>{vm.name}</b>: " + ", ".join(label_contents)
        label_widget.set_markup(label_text)

        return vm, icon_img, label_widget


class SettingsItem(Gtk.MenuItem):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.set_label(_('Open Qube Settings'))

        self.connect('activate', launch_preferences_dialog, self.vm.name)


def launch_preferences_dialog(_, vm):
    vm = str(vm).strip('\'')
    # pylint: disable=consider-using-with
    subprocess.Popen(['qubes-vm-settings', vm])


class NeverNotifyItem(Gtk.CheckMenuItem):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.set_label(_('Do not show notifications about this qube'))

        try:
            self.set_active(
                self.vm.features.get('disk-space-not-notify', False))
        except exc.QubesDaemonCommunicationError:
            self.set_active(False)
            self.set_sensitive(False)

        self.connect('toggled', self.toggle_state)

    def toggle_state(self, _item):
        try:
            if self.get_active():
                self.vm.features['disk-space-not-notify'] = 1
            else:
                del self.vm.features['disk-space-not-notify']
        except exc.QubesDaemonAccessError:
            self.set_sensitive(False)


class VMMenu(Gtk.Menu):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.add(NeverNotifyItem(self.vm))
        self.add(SettingsItem(self.vm))

        self.show_all()


class PoolWrapper:
    """Wrapper for pools, to manage various exceptions thrown by properties."""
    def __init__(self, pool: Pool):
        self.pool = pool
        self.has_error = False
        self.size = self._get_attribute('size', None)
        self.usage = self._get_attribute('usage', None)
        self.config = self._get_attribute('config', {})
        self.usage_details = self._get_attribute('usage_details', {})
        self.name = self._get_attribute('name', 'ERROR: pool name unknown')

        self.metadata_size = self.usage_details.get('metadata_size', None)
        self.metadata_usage = self.usage_details.get('metadata_usage', None)

        if self.size and self.usage:
            self.usage_perc = self.usage / self.size
        else:
            self.usage_perc = 0

        if self.metadata_size and self.metadata_usage:
            self.metadata_perc = self.metadata_usage / self.metadata_size
        else:
            self.metadata_perc = 0

    def _get_attribute(self, attribute_name, default):
        try:
            return getattr(self.pool, attribute_name, default)
        except exc.StoragePoolException:
            self.has_error = True
            return default


class PoolUsageData:
    def __init__(self, qubes_app):
        self.qubes_app = qubes_app

        self.pools: List[PoolWrapper] = []
        self.total_size = 0
        self.used_size = 0
        self.warning_message = []

        self.__populate_pools()

    def __populate_pools(self):
        try:
            pools = sorted(self.qubes_app.pools.values())
        except exc.QubesDaemonAccessError:
            pools = []
        for pool in pools:
            wrapped_pool = PoolWrapper(pool)
            self.pools.append(wrapped_pool)

            if wrapped_pool.has_error:
                continue

            if not wrapped_pool.size or not wrapped_pool.usage or \
                    'included_in' in wrapped_pool.config:
                continue
            self.total_size += wrapped_pool.size
            self.used_size += wrapped_pool.usage

            if wrapped_pool.usage_perc >= URGENT_WARN_LEVEL:
                self.warning_message.append(
                    _("\n{:.1%} space left in pool {}").format(
                        1-wrapped_pool.usage_perc, wrapped_pool.name))

            if wrapped_pool.metadata_perc >= URGENT_WARN_LEVEL:
                # pylint: disable=consider-using-f-string
                self.warning_message.append(_(
                    "\nMetadata space for pool {} is running out. "
                    "Current usage: {:.0%}").format(
                        wrapped_pool.name, wrapped_pool.metadata_perc))

    def get_pools_widgets(self):
        for p in self.pools:
            yield self.__create_box(p)

    def get_warning(self):
        return self.warning_message

    def get_usage(self):
        if self.total_size > 0:
            return self.used_size/self.total_size
        return 0

    @staticmethod
    def __create_box(pool: PoolWrapper):
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        percentage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        usage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        pool_name = Gtk.Label(xalign=0)

        if pool.has_error:
            # Pool with errors
            formatted_name = \
                f'<span color=\'red\'><b>{pool.name}</b></span>'
        elif pool.size and 'included_in' not in pool.config:
            # normal pool
            formatted_name = f'<b>{pool.name}</b>'
        else:
            # pool without data or included in another pool
            formatted_name = f'<span color=\'grey\'><i>{pool.name}</i></span>'

        pool_name.set_markup(formatted_name)
        pool_name.set_margin_left(20)

        name_box.pack_start(pool_name, True, True, 0)

        if not pool.size or 'included_in' in pool.config:
            return name_box, percentage_box, usage_box

        if pool.has_error:
            error_desc = Gtk.Label(xalign=0)
            error_desc.set_markup("Error accessing pool data")
            error_desc.set_margin_left(40)
            name_box.pack_start(error_desc, True, True, 0)
            return name_box, percentage_box, usage_box

        data_name = Gtk.Label(xalign=0)
        data_name.set_markup("data")
        data_name.set_margin_left(40)

        name_box.pack_start(data_name, True, True, 0)

        if pool.metadata_perc:
            metadata_name = Gtk.Label(xalign=0)
            metadata_name.set_markup("metadata")
            metadata_name.set_margin_left(40)

            name_box.pack_start(metadata_name, True, True, 0)

        percentage_use = Gtk.Label()
        percentage_use.set_markup(colored_percentage(pool.usage_perc))
        percentage_use.set_justify(Gtk.Justification.RIGHT)

        # empty label to guarantee proper alignment
        percentage_box.pack_start(Gtk.Label(), True, True, 0)
        percentage_box.pack_start(percentage_use, True, True, 0)

        if pool.metadata_perc:
            metadata_label = Gtk.Label()
            metadata_label.set_markup(colored_percentage(
                pool.metadata_perc))
            percentage_box.pack_start(metadata_label, True, True, 0)

        numeric_label = Gtk.Label()
        numeric_label.set_markup(
            '<span color=\'grey\'><i>'
            f'{size_to_human(pool.usage or 0)}/'
            f'{size_to_human(pool.size or 0)}</i></span>')
        numeric_label.set_justify(Gtk.Justification.RIGHT)

        # pack with empty labels to guarantee proper alignment
        usage_box.pack_start(Gtk.Label(), True, True, 0)
        usage_box.pack_start(numeric_label, True, True, 0)
        usage_box.pack_start(Gtk.Label(), True, True, 0)

        return name_box, percentage_box, usage_box


def colored_percentage(value):
    if value < WARN_LEVEL:
        color = 'green'
    elif value < URGENT_WARN_LEVEL:
        color = 'orange'
    else:
        color = 'red'

    # pylint: disable=consider-using-f-string
    result = '<span color=\'{}\'>{:.1%}</span>'.format(color, value)

    return result


def emit_notification(gtk_app, title, text, vm=None):
    notification = Gio.Notification.new(title)
    notification.set_priority(Gio.NotificationPriority.HIGH)
    notification.set_body(text)
    notification.set_icon(Gio.ThemedIcon.new('dialog-warning'))

    if vm:
        notification.add_button(_('Open qube settings'),
                                f"app.prefs::{vm.name}")

    gtk_app.send_notification(None, notification)


class DiskSpace(Gtk.Application):
    def __init__(self, **properties):
        super().__init__(**properties)

        self.pool_warned = False
        self.vms_warned = set()

        self.qubes_app = Qubes()

        self.set_application_id("org.qubes.qui.tray.DiskSpace")
        self.register()

        # for some reaslon pylint doesn't see GLib.VariantType.new
        # pylint: disable=no-member
        prefs_action = Gio.SimpleAction.new("prefs", GLib.VariantType.new("s"))
        prefs_action.connect("activate", launch_preferences_dialog)
        self.add_action(prefs_action)

        self.icon = Gtk.StatusIcon()
        self.icon.connect('button-press-event', self.make_menu)
        self.refresh_icon()

        GObject.timeout_add_seconds(120, self.refresh_icon)

        Gtk.main()

    def refresh_icon(self):
        pool_data = PoolUsageData(self.qubes_app)
        vm_data = VMUsageData(self.qubes_app)
        pool_warning = pool_data.get_warning()
        vm_warning = vm_data.problematic_vms

        # set icon
        self.set_icon_state(pool_warning=pool_warning,
                            vm_warning=vm_warning)

        # emit notification
        if pool_warning:
            if not self.pool_warned:
                emit_notification(
                    self,
                    _("Disk usage warning!"),
                    _("You are running out of disk space.") + ''.join(
                        pool_warning))
                self.pool_warned = True
        else:
            self.pool_warned = False

        if vm_warning:
            currently_problematic_vms = [x.vm for x in vm_warning]

            self.vms_warned = {vm for vm in self.vms_warned if vm in
                               currently_problematic_vms}
            for vm in currently_problematic_vms:
                if not vm.features.get('disk-space-not-notify', False) and vm\
                        not in self.vms_warned:
                    emit_notification(
                        self,
                        _("Qube usage warning"),
                        _("Qube {} is running out of storage space.").format(
                            vm.name),
                        vm=vm)
                    self.vms_warned.add(vm)
        else:
            self.vms_warned = set()

        return True  # needed for Gtk to correctly loop the function

    def set_icon_state(self, pool_warning=None, vm_warning=None):
        if pool_warning or vm_warning:
            self.icon.set_from_icon_name("dialog-warning")
            text = _("<b>Qubes Disk Space Monitor</b>\n\nWARNING!")
            if pool_warning:
                text += _('\nYou are running out of disk space.\n') + \
                        ''.join(pool_warning)
            if vm_warning:
                text += _('\nThe following qubes are running out of space: ') \
                        + ', '.join([x.vm.name for x in vm_warning])
            self.icon.set_tooltip_markup(text)
        else:
            self.icon.set_from_icon_name("drive-harddisk")
            self.icon.set_tooltip_markup(
                _('<b>Qubes Disk Space Monitor</b>\nView free disk space.'))

    def make_menu(self, _unused, _event):
        pool_data = PoolUsageData(self.qubes_app)
        vm_data = VMUsageData(self.qubes_app)

        menu = Gtk.Menu()

        menu.append(self.make_top_box(pool_data))

        menu.append(self.make_title_item('Volumes'))

        grid = Gtk.Grid()
        col_no = 0
        for (label1, label2, label3) in pool_data.get_pools_widgets():
            grid.attach(label1, 0, col_no, 1, 1)
            grid.attach(label2, 1, col_no, 1, 1)
            grid.attach(label3, 2, col_no, 1, 1)
            col_no += 1

        grid.set_column_spacing(20)
        grid_menu_item = Gtk.MenuItem()
        grid_menu_item.add(grid)
        grid_menu_item.set_sensitive(False)
        menu.append(grid_menu_item)

        if vm_data.problematic_vms:
            menu.append(self.make_title_item(_('Qubes warnings')))

            for (vm, label1, label2) in vm_data.get_vms_widgets():
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                hbox.pack_start(label1, False, False, 0)
                hbox.pack_start(label2, False, False, 5)

                vm_menu_item = Gtk.MenuItem()
                vm_menu_item.add(hbox)

                vm_menu_item.set_submenu(VMMenu(vm))

                menu.append(vm_menu_item)

        menu.set_reserve_toggle_size(False)

        menu.show_all()
        menu.popup_at_pointer(None)  # use current event

    @staticmethod
    def make_title_item(text):
        label = Gtk.Label(xalign=0)
        label.set_markup(_("<b>{}</b>").format(text))
        menu_item = Gtk.MenuItem()
        menu_item.add(label)
        menu_item.set_sensitive(False)
        return menu_item

    @staticmethod
    def make_top_box(pool_data):
        grid = Gtk.Grid()

        name_label = Gtk.Label(xalign=0)
        name_label.set_markup(_("<b>Total disk usage</b>"))

        percentage_value = Gtk.Label()
        percentage_value.set_markup(colored_percentage(pool_data.get_usage()))
        percentage_value.set_margin_top(10)

        progress_bar = Gtk.LevelBar()
        progress_bar.set_min_value(0)
        progress_bar.set_max_value(100)
        progress_bar.set_value(pool_data.get_usage()*100)
        progress_bar.set_vexpand(True)
        progress_bar.set_hexpand(True)
        progress_bar.set_margin_left(20)
        progress_bar.set_margin_right(10)
        progress_bar.set_margin_top(10)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(progress_bar, 0, 1, 1, 1)
        grid.attach(percentage_value, 1, 1, 1, 1)

        progress_bar_item = Gtk.MenuItem()
        progress_bar_item.add(grid)

        progress_bar_item.set_sensitive(False)

        return progress_bar_item


def main():
    app = DiskSpace()
    app.run()


if __name__ == '__main__':
    sys.exit(main())
