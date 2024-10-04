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
New Qube program.
"""
# pylint: disable=import-error
import subprocess
import sys
from typing import Optional, Dict, Any
import importlib.resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from .application_selector import ApplicationBoxHandler
from .template_handler import TemplateHandler, TemplateSelector
from .network_selector import NetworkSelector
from .advanced_handler import AdvancedHandler
from ..widgets.gtk_utils import load_icon, show_error, load_theme
from ..widgets.gtk_widgets import ProgressBarDialog, ImageListModeler,\
    ViewportHandler

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


logger = logging.getLogger('qubes-new-qube')
WHONIX_QUBE_NAME = 'sys-whonix'


class CreateNewQube(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, qapp):
        """
        :param qapp: qubesadmin.Qubes object
        """
        super().__init__(application_id='org.qubesos.newqube')
        self.qapp: qubesadmin.Qubes = qapp

        self.builder: Optional[Gtk.Builder] = None
        self.main_window: Optional[Gtk.Window] = None
        self.template_selector: Optional[TemplateSelector] = None

        self.progress_bar_dialog = ProgressBarDialog(
            self, _("Loading available applications..."))

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        self.register_signals()
        self.perform_setup()
        assert self.main_window
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
        """
        The function that performs actual widget realization and setup. Should
        be only called once, in the main instance of this application.
        """
        self.progress_bar_dialog.show()
        self.progress_bar_dialog.update_progress(0.1)

        self.builder = Gtk.Builder()
        glade_ref = (importlib.resources.files('qubes_config') /
                     'new_qube.glade')
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.main_window = self.builder.get_object('main_window')
        self.qube_name: Gtk.Entry = self.builder.get_object('qube_name')
        self.qube_label_combo: Gtk.ComboBox = \
            self.builder.get_object('qube_label')

        load_theme(widget=self.main_window,
                   package_name='qubes_config',
                   light_file_name='qubes-new-qube-light.css',
                   dark_file_name='qubes-new-qube-dark.css')

        self.progress_bar_dialog.update_progress(0.1)

        self.template_handler = TemplateHandler(self.builder, self.qapp)

        self.progress_bar_dialog.update_progress(0.1)

        self.qube_type_app: Gtk.RadioButton = \
            self.builder.get_object('qube_type_app')
        self.qube_type_template: Gtk.RadioButton = \
            self.builder.get_object('qube_type_template')
        self.qube_type_standalone: Gtk.RadioButton = \
            self.builder.get_object('qube_type_standalone')
        self.qube_type_disposable: Gtk.RadioButton = \
            self.builder.get_object('qube_type_disposable')

        self.tooltips = {
            'qube_type_app': self.builder.get_object('qube_type_app_q'),
            'qube_type_template':
                self.builder.get_object('qube_type_template_q'),
            'qube_type_standalone':
                self.builder.get_object('qube_type_standalone_q'),
            'qube_type_disposable':
                self.builder.get_object('qube_type_disposable_q')
        }

        self.qube_type_app.connect('toggled', self._type_selected)
        self.qube_type_template.connect('toggled', self._type_selected)
        self.qube_type_standalone.connect('toggled', self._type_selected)
        self.qube_type_disposable.connect('toggled', self._type_selected)

        label_dict = {}
        for label in self.qapp.labels:
            label_dict[str(label)] = {
                'icon': f'appvm-{label}',
                'object': str(label)
            }

        self.qube_label_modeler = ImageListModeler(
            combobox=self.qube_label_combo,
            value_list=label_dict
        )

        self.qube_name.connect('changed', self._name_changed)

        self.progress_bar_dialog.update_progress(0.1)

        self.network_selector = NetworkSelector(self.builder, self.qapp)

        self.progress_bar_dialog.update_progress(0.1)

        self.app_box_handler = ApplicationBoxHandler(
            self.builder, self.template_handler)

        self.progress_bar_dialog.update_progress(0.1)

        self.advanced_handler = AdvancedHandler(self.builder, self.qapp)

        self.progress_bar_dialog.update_progress(0.1)

        self.create_button: Gtk.Button = \
            self.builder.get_object('create_button')
        self.create_button.connect('clicked', self._do_create_qube)

        self.cancel_button: Gtk.Button = \
            self.builder.get_object('cancel_button')
        self.cancel_button.connect('clicked', self._quit)

        self.viewport_handler = ViewportHandler(
            self.main_window, [self.builder.get_object('main_scrolled_window')])

        self.main_window.connect('delete-event', self._quit)

        self.progress_bar_dialog.update_progress(1)
        self.progress_bar_dialog.hide()

    def _quit(self, *_args):
        self.quit()

    @staticmethod
    def register_signals():
        """Register necessary Gtk signals"""
        GObject.signal_new('template-changed',
                           Gtk.Window,
                           GObject.SignalFlags.RUN_LAST, None, (str,))

    def _name_changed(self, entry: Gtk.Entry):
        if not entry.get_text():
            self.create_button.set_sensitive(False)
        else:
            self.create_button.set_sensitive(True)

    def _type_selected(self, button: Gtk.RadioButton):
        button_name = button.get_name()
        if not button.get_active():
            self.tooltips[button_name].set_from_pixbuf(
                load_icon('qubes-question', 20, 20))
            return
        self.template_handler.change_vm_type(button_name)

        if button_name == 'qube_type_template':
            self.network_selector.network_none.set_active(True)
        else:
            self.network_selector.network_default.set_active(True)

        self.tooltips[button_name].set_from_pixbuf(load_icon(
                'qubes-question-light', 20, 20))

    def _do_create_qube(self, *_args):
        label = self.qube_label_modeler.get_selected()
        name = self.qube_name.get_text()

        if not label or not name:
            raise ValueError

        if self.qube_type_template.get_active():
            klass = 'TemplateVM'
        elif self.qube_type_standalone.get_active():
            klass = 'StandaloneVM'
        elif self.qube_type_disposable.get_active():
            klass = 'DispVM'
        else:
            klass = 'AppVM'

        properties: Dict[str, Any] = {'provides_network':
                          self.advanced_handler.get_provides_network()}
        selected_netvm = self.network_selector.get_selected_netvm()
        if not (klass == 'TemplateVM' and selected_netvm is None) \
                and selected_netvm != qubesadmin.DEFAULT:
            properties['netvm'] = selected_netvm
        if klass == 'StandaloneVM' and \
                not self.template_handler.get_selected_template():
            properties['virt_mode'] = 'hvm'
            properties['kernel'] = None

        if self.advanced_handler.get_init_ram():
            properties['memory'] = self.advanced_handler.get_init_ram()

        vm = None
        err = None

        try:
            vm = self._create_qube(
                vmclass=klass,
                name=name,
                label = label,
                template=self.template_handler.get_selected_template(),
                properties=properties,
                pool=self.advanced_handler.get_pool(),
            )
        except qubesadmin.exc.QubesException as qex:
            err  = str(qex)
        except Exception as ex:  # pylint: disable=broad-except
            err = repr(ex)

        if err or not vm:
            show_error(self.main_window, _("Could not create qube"),
                       _("An error occurred: {error}").format(error=err))
            return

        apps = self.app_box_handler.get_selected_apps()

        if apps:
            with subprocess.Popen([
                    'qvm-appmenus',
                    '--set-whitelist', '-',
                    '--update', vm.name],
                    stdin=subprocess.PIPE) as p:
                p.communicate('\n'.join(apps).encode())
                if p.returncode != 0:
                    show_error(
                        self.main_window,
                        _("Failed to select applications"),
                        _("An error occurred: {error}").format(error=err))
                    return
        msg = Gtk.MessageDialog(
            transient_for=self.main_window,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Qube created successfully!"))
        msg.run()

        if self.advanced_handler.get_launch_settings():
            subprocess.check_call(['qubes-vm-settings', str(vm)])
        if self.advanced_handler.get_install_system():
            subprocess.check_call(['qubes-vm-boot-from-device', str(vm)])

        self.quit()

    def _create_qube(self, vmclass, name, label, template,
                     properties, pool) -> qubesadmin.vm.QubesVM:
        if vmclass in ['StandaloneVM', 'TemplateVM'] and template is not None:
            args = {
                'ignore_volumes': ['private']
            }
            if pool:
                args['pool'] = pool

            vm = self.qapp.clone_vm(template, name, vmclass, **args)
            vm.label = label
            for k, v in properties.items():
                setattr(vm, k, v)
        else:
            args = {
                "name": name,
                "label": label,
                "template": template
            }
            if pool:
                args['pool'] = pool

            vm = self.qapp.add_new_vm(vmclass, **args)
            for k, v in properties.items():
                setattr(vm, k, v)

        return vm


def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    app = CreateNewQube(qapp)
    app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
