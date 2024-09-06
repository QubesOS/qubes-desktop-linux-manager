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
import yaml
import subprocess
import logging

import qubesadmin.vm
from ..widgets.gtk_utils import show_error, load_icon, copy_to_global_clipboard
from .page_handler import PageHandler
from .policy_manager import PolicyManager

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

logger = logging.getLogger('qubes-global-config')

class ThisDeviceHandler(PageHandler):
    """Handler for the ThisDevice page."""
    INPUT_SERVICE = 'qubes.InputKeyboard'

    def __init__(self,
                 qapp: qubesadmin.Qubes,
                 gtk_builder: Gtk.Builder,
                 policy_manager: PolicyManager,
                 ):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.model_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_model_label')
        self.data_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_data_label')

        self.certified_box_yes: Gtk.Box = gtk_builder.get_object(
            'thisdevice_certified_box_yes')

        self.compat_hvm_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_hvm_image')
        self.compat_hvm_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_hvm_label')
        self.compat_iommu_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_iommu_image')
        self.compat_iommu_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_iommu_label')
        self.compat_hap_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_hap_image')
        self.compat_hap_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_hap_label')
        self.compat_tpm_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_tpm_image')
        self.compat_tpm_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_tpm_label')
        self.compat_remapping_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_remapping_image')
        self.compat_remapping_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_remapping_label')
        self.compat_usbk_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_usbk_image')
        self.compat_usbk_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_usbk_label')
        self.compat_pv_image: Gtk.Image = gtk_builder.get_object(
            'thisdevice_pv_image')
        self.compat_pv_label: Gtk.Label = gtk_builder.get_object(
            'thisdevice_pv_label')
        self.compat_pv_tooltip: Gtk.Image = gtk_builder.get_object(
            'thisdevice_pv_tooltip')

        self.copy_button: Gtk.Button = \
            gtk_builder.get_object('thisdevice_copy_button')
        self.copy_hcl_button: Gtk.Button = \
            gtk_builder.get_object('thisdevice_copy_hcl_button')

        label_text = ""
        self.hcl_yaml = {}

        try:
            self.hcl_check = subprocess.check_output(
                ['qubes-hcl-report', '-y']).decode()
        except subprocess.CalledProcessError as ex:
            label_text += _("Failed to load system data: {ex}\n").format(
                ex=str(ex))
            self.hcl_check = ""

        try:
            if self.hcl_check:
                self.hcl_yaml = yaml.safe_load(self.hcl_check)
            if not self.hcl_yaml:
                raise ValueError
            label_text = ""
        except (yaml.YAMLError, ValueError):
            self.hcl_yaml = {}
            label_text += _("Failed to load system data.\n")
            self.data_label.get_style_context().add_class('red_code')

        label_text += _("""<b>Brand:</b> {brand}
<b>Model:</b> {model}

<b>CPU:</b> {cpu}
<b>Chipset:</b> {chipset}
<b>Graphics:</b> {gpu}

<b>RAM:</b> {memory} Mb

<b>QubesOS version:</b> {qubes_ver}
<b>BIOS:</b> {bios}
<b>Kernel:</b> {kernel_ver}
<b>Xen:</b> {xen_ver}
""").format(brand=self._get_data('brand'),
           model=self._get_data('model'),
           cpu=self._get_data('cpu'),
           chipset=self._get_data('chipset'),
           gpu=self._get_data('gpu'),
           memory=self._get_data('memory'),
           qubes_ver=self._get_version('qubes'),
           bios=self._get_data('bios'),
           kernel_ver=self._get_version('kernel'),
           xen_ver=self._get_version('xen'))
        self.set_state(self.compat_hvm_image, self._get_data('hvm'))
        self.compat_hvm_label.set_markup(f"<b>HVM:</b> {self._get_data('hvm')}")

        self.set_state(self.compat_iommu_image, self._get_data('iommu'))
        self.compat_iommu_label.set_markup(
            f"<b>I/O MMU:</b> {self._get_data('iommu')}")

        self.set_state(self.compat_hap_image, self._get_data('slat'))
        self.compat_hap_label.set_markup(
            f"<b>HAP/SLAT:</b> {self._get_data('slat')}")

        self.set_state(self.compat_tpm_image,
                       'yes' if self._get_data('tpm') == '1.2' else 'maybe')
        if self._get_data('tpm') == '2.0':
            self.set_state(self.compat_tpm_image, 'maybe')
            self.compat_tpm_label.set_markup(
                _("<b>TPM version</b>: 2.0 (not yet supported)"))
        elif self._get_data('tpm') == '1.2':
            self.set_state(self.compat_tpm_image, 'yes')
            self.compat_tpm_label.set_markup(
                _("<b>TPM version</b>: 1.2"))
        else:
            self.set_state(self.compat_tpm_image, 'no')
            self.compat_tpm_label.set_markup(
                _("<b>TPM version</b>: device not found"))

        self.set_state(self.compat_remapping_image, self._get_data('remap'))
        self.compat_remapping_label.set_markup(
            f"<b>Remapping:</b> {self._get_data('remap')}")

        self.set_policy_state()

        pv_vms = [vm for vm in self.qapp.domains
                  if getattr(vm, 'virt_mode', None) == 'pv']

        self.set_state(self.compat_pv_image, 'no' if pv_vms else 'yes')
        self.compat_pv_label.set_markup(
            _("<b>PV qubes:</b> {num_pvs} found").format(num_pvs=len(pv_vms)))
        self.compat_pv_tooltip.set_tooltip_markup(
            _("<b>The following qubes have PV virtualization mode:</b>\n - ") +
            '\n - '.join([vm.name for vm in pv_vms]))
        self.compat_pv_tooltip.set_visible(bool(pv_vms))

        self.data_label.set_markup(label_text)

        self.certified_box_yes.set_visible(self.is_certified())

        self.copy_button.connect('clicked', self._copy_to_clipboard)
        self.copy_hcl_button.connect('clicked', self._copy_to_clipboard)

        self.data_label.get_toplevel().connect('page-changed',
                                               self._page_saved)

    def _get_data(self, name) -> str:
        data = self.hcl_yaml.get(name, _("unknown")).strip()
        return data if data else _('unknown')

    def _get_version(self, name) -> str:
        try:
            data = self.hcl_yaml['versions'][0].get(name, _("unknown")).strip()
        except (KeyError, AttributeError):
            return _("unknown")
        return data if data else _('unknown')

    def _copy_to_clipboard(self, widget: Gtk.Button):
        if widget.get_name() == 'copy_button':
            text = self.data_label.get_text()
        elif widget.get_name() == 'copy_hcl_button':
            text = self.hcl_check
        else:
            raise ValueError
        try:
            copy_to_global_clipboard(text)
        except Exception:  # pylint: disable=broad-except
            show_error(self.copy_button.get_toplevel(),
                       _("Failed to copy to Global Clipboard"),
                       _("An error occurred while trying to access"
                         " Global Clipboard"))

    @staticmethod
    def set_state(image_widget: Gtk.Image, value: str):
        """Set state of provided widget according to value;
        for 'yes', show a green checkmark, for 'maybe' yellow one,
        and for all others red X."""
        if value == 'yes':
            image_widget.set_from_pixbuf(load_icon('check_yes', 22, 22))
        elif value == 'maybe':
            image_widget.set_from_pixbuf(load_icon('check_maybe', 22, 22))
        else:
            image_widget.set_from_pixbuf(load_icon('check_no', 20, 20))

    def _get_policy_state(self) -> str:
        policy_files = sorted(
            self.policy_manager.get_all_policy_files(self.INPUT_SERVICE))

        for f in policy_files:
            if f.startswith('/etc/qubes-rpc'):
                return 'legacy'
            rules, _token = self.policy_manager.get_rules_from_filename(f, "")
            for rule in rules:
                if rule.service == self.INPUT_SERVICE:
                    if 'allow' in str(rule.action):
                        return 'allow'
        return 'deny'

    def is_certified(self) -> bool:
        """Is this device Qubes certified?"""
        return self._get_data("certified") == "yes"

    def _page_saved(self, _page: PageHandler, page_name: str):
        if page_name == 'usb':
            self.set_policy_state()

    def set_policy_state(self):
        """Refresh policy state, because it might have changed since
         we last were here"""
        policy_state = self._get_policy_state()
        label_text = _("<b>USB keyboards</b>: ")
        if policy_state == 'legacy':
            self.set_state(self.compat_usbk_image, "maybe")
            label_text += _("unknown (legacy policy found)")
        elif policy_state == 'allow':
            self.set_state(self.compat_usbk_image, "no")
            label_text += _("insecure policy")
        elif policy_state == 'deny':
            self.set_state(self.compat_usbk_image, "yes")
            label_text += _("secure policy")
        self.compat_usbk_label.set_markup(label_text)

    def reset(self):
        # does not apply
        pass

    def save(self):
        # does not apply
        pass

    def get_unsaved(self) -> str:
        return ""
