# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Marta Marczykowska-Górecka
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
"""Handler for the general settings page"""
# pylint: disable=unspecified-encoding
import re
from typing import Optional, Dict, Any, Callable, List
import abc
import logging
import itertools
from configparser import ConfigParser

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from qubesadmin.utils import parse_size

from ..widgets.gtk_widgets import VMListModeler, \
    TextModeler, TraitSelector, NONE_CATEGORY
from .page_handler import PageHandler
from ..widgets.utils import get_feature, get_boolean_feature, \
    apply_feature_change

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger('qubes-global-config')

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

class KernelVersion:  # pylint: disable=too-few-public-methods
    """Helper class to be used in sorting kernels. Cannot use
    distutils.version.LooseVersion, because it fails at handling
    versions that have no numbers in them, which is quite possible with
    custom kernels."""
    def __init__(self, string):
        self.string = string
        self.groups = re.compile(r'(\d+)').split(self.string)

    def __lt__(self, other):
        for (self_content, other_content) in itertools.zip_longest(
                self.groups, other.groups):
            if self_content == other_content:
                continue
            if self_content is None:
                return True
            if other_content is None:
                return False
            if self_content.isdigit() and other_content.isdigit():
                return int(self_content) < int(other_content)
            return self_content < other_content


class AbstractTraitHolder(abc.ABC):
    """Handler for all sorts of widgets reflecting system traits."""
    @abc.abstractmethod
    def get_model(self) -> TraitSelector:
        """Get the TraitSelector for current Trait."""

    @abc.abstractmethod
    def get_current_value(self):
        """Get current system value of the handled trait"""

    @abc.abstractmethod
    def update_current_value(self):
        """Set current value in the system to whatever is selected."""

    @abc.abstractmethod
    def get_readable_description(self) -> str:
        """Get a readable description."""

    def is_changed(self) -> bool:
        """Has the user selected something different from the initial value?"""
        return self.get_model().is_changed()

    def save(self):
        """Save changes: update system value and mark it as new initial value"""
        self.update_current_value()
        self.get_model().update_initial()

    def reset(self):
        """Reset selection to the initial value."""
        self.get_model().reset()

    def get_unsaved(self):
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.is_changed():
            return self.get_readable_description()
        return ""


class PropertyHandler(AbstractTraitHolder):
    """Handles comboboxes reflecting for object properties."""
    def __init__(self, qapp: qubesadmin.Qubes, trait_holder: Any,
                 trait_name: str, widget: Gtk.ComboBox,
                 vm_filter: Optional[Callable] = None,
                 readable_name: Optional[str] = None,
                 additional_options: Optional[Dict[str, str]] = None):
        self.qapp = qapp
        self.trait_holder = trait_holder
        self.trait_name = trait_name
        self.widget = widget
        self.readable_name = readable_name if readable_name else trait_name

        self.model = VMListModeler(
            combobox=self.widget,
            qapp=qapp,
            filter_function=vm_filter,
            current_value=self.get_current_value(),
            style_changes=True,
            additional_options=additional_options
        )

    def get_readable_description(self) -> str:
        return self.readable_name

    def get_current_value(self):
        return getattr(self.trait_holder, self.trait_name, None)

    def update_current_value(self):
        if self.model.is_changed():
            new_value = self.model.get_selected()
            setattr(self.trait_holder, self.trait_name, new_value)

    def get_model(self) -> TraitSelector:
        return self.model


class FeatureHandler(AbstractTraitHolder):
    """Handles comboboxes reflecting vm features."""
    def __init__(self, trait_holder: Any, trait_name: str,
                 widget: Gtk.ComboBoxText, options: Dict[str, Any],
                 readable_name: str, is_bool: bool = False):
        self.trait_holder = trait_holder
        self.trait_name = trait_name
        self.widget = widget
        self.is_bool = is_bool
        self.readable_name = readable_name

        self.model = TextModeler(
            combobox=self.widget,
            values=options, selected_value=self.get_current_value(),
            style_changes=True)

    def get_readable_description(self) -> str:
        return self.readable_name

    def get_current_value(self):
        if self.is_bool:
            return get_boolean_feature(self.trait_holder, self.trait_name)
        return get_feature(self.trait_holder, self.trait_name, None)

    def update_current_value(self):
        if self.model.is_changed():
            new_value = self.model.get_selected()
            apply_feature_change(self.trait_holder, self.trait_name, new_value)

    def get_model(self) -> TraitSelector:
        return self.model

class QMemManHelper:
    """Helper class to handle the ugliness of managing qmemman config."""
    QMEMMAN_CONFIG_PATH = '/etc/qubes/qmemman.conf'
    MINMEM_NAME = 'vm-min-mem'
    DOM0_NAME = 'dom0-mem-boost'

    def __init__(self):
        self.qmemman_config = None

    def get_values(self) -> Dict[str, int]:
        """Returns a dict of 'vm-min-mem': value in MiB and
        'dom0-mem-boost': value in MiB """
        self.qmemman_config = ConfigParser()
        self.qmemman_config.read(self.QMEMMAN_CONFIG_PATH)

        result = {
            self.MINMEM_NAME: 200,
            self.DOM0_NAME: 350
        }

        if self.qmemman_config.has_section('global'):
            for key in result:
                str_value = self.qmemman_config.get('global', key)
                value = parse_size(str_value)
                result[key] = int(value / 1024 / 1024)

        return result

    def save_values(self, values_dict: Dict[str, int]):
        """Wants a dict of 'vm-min-mem': value in MiB and
        'dom0-mem-boost': value in MiB"""
        # qmemman settings
        text_dict = {key: str(int(value)) + 'MiB'
                     for key, value in values_dict.items()}

        assert len(text_dict) == 2 and \
               self.MINMEM_NAME in text_dict and self.DOM0_NAME in text_dict

        # reinitialize the ConfigParser object, because it is somewhat
        # unhappy to handle multiple consecutive writes and reads

        self.qmemman_config = ConfigParser()
        self.qmemman_config.read(self.QMEMMAN_CONFIG_PATH)

        if not self.qmemman_config.has_section('global'):
            # add the whole section
            self.qmemman_config.add_section('global')
            for key in text_dict:
                self.qmemman_config.set(
                    'global', key, text_dict[key])
            self.qmemman_config.set(
                'global', 'cache-margin-factor', str(1.3))

            with open(self.QMEMMAN_CONFIG_PATH, 'a') as qmemman_config_file:
                self.qmemman_config.write(qmemman_config_file)

        else:
            # If there already is a 'global' section, we don't use
            # SafeConfigParser.write() - it would get rid of
            # all the comments...
            lines_to_add = {key: f'{key} = {value}\n'
                            for key, value in text_dict.items()}

            config_lines = []
            with open(self.QMEMMAN_CONFIG_PATH, 'r') as qmemman_config_file:
                for line in qmemman_config_file:
                    for key in lines_to_add:
                        if line.strip().startswith(key):
                            config_lines.append(lines_to_add[key])
                            del lines_to_add[key]
                            break
                    else:
                        config_lines.append(line)

            for line in lines_to_add:
                config_lines.append(line)

            with open(self.QMEMMAN_CONFIG_PATH, 'w') as qmemman_config_file:
                qmemman_config_file.writelines(config_lines)


class MemoryHandler(AbstractTraitHolder):
    """Handler for memory / QMemMan settings. Requires SpinButton widgets:
    'basics_min_memory' and 'basics_dom0_memory'"""
    def __init__(self, gtk_builder):
        self.min_memory_spin: Gtk.SpinButton = \
            gtk_builder.get_object('basics_min_memory')
        self.dom0_memory_spin: Gtk.SpinButton = \
            gtk_builder.get_object('basics_dom0_memory')

        self.min_memory_adjustment = Gtk.Adjustment()
        self.min_memory_adjustment.configure(0, 0, 999999, 1, 10, 0)
        self.dom0_memory_adjustment = Gtk.Adjustment()
        self.dom0_memory_adjustment.configure(0, 0, 999999, 1, 10, 0)

        self.min_memory_spin.configure(self.min_memory_adjustment, 0.1, 0)
        self.dom0_memory_spin.configure(self.dom0_memory_adjustment, 0.1, 0)

        self.mem_helper = QMemManHelper()
        self.initial_values = {}

        try:
            self.initial_values = self.mem_helper.get_values()
        except qubesadmin.exc.QubesException:
            self.min_memory_spin.set_sensitive(False)
            self.dom0_memory_spin.set_sensitive(False)

        self.min_memory_spin.set_value(
            self.initial_values.get(self.mem_helper.MINMEM_NAME, 0))
        self.dom0_memory_spin.set_value(
            self.initial_values.get(self.mem_helper.DOM0_NAME, 0))

    @staticmethod
    def get_readable_description() -> str:  # pylint: disable=arguments-differ
        """Get human-readable description of the widget"""
        # the pylint: disable above is because pylint does not understand
        # static methods
        return _("Qube memory settings")

    def save(self):
        """Save changes: update system value and mark it as new initial value"""
        if not self.is_changed():
            return

        values = {
            self.mem_helper.MINMEM_NAME: int(self.min_memory_spin.get_value()),
            self.mem_helper.DOM0_NAME: int(self.dom0_memory_spin.get_value())
        }

        self.mem_helper.save_values(values)

    def reset(self):
        """Reset selection to the initial value."""
        if not self.min_memory_spin.is_sensitive():
            return

        self.min_memory_spin.set_value(self.initial_values.get(
            self.mem_helper.MINMEM_NAME, 0))
        self.dom0_memory_spin.set_value(self.initial_values.get(
            self.mem_helper.DOM0_NAME, 0))

    def is_changed(self) -> bool:
        """Has the user selected something different from the initial value?"""
        if not self.min_memory_spin.is_sensitive() or \
                not self.dom0_memory_spin.is_sensitive():
            return False
        if self.min_memory_spin.get_value() != self.initial_values.get(
            self.mem_helper.MINMEM_NAME, 0):
            return True
        if self.dom0_memory_spin.get_value() != self.initial_values.get(
            self.mem_helper.DOM0_NAME, 0):
            return True
        return False

    def get_unsaved(self):
        """Get human-readable description of unsaved changes, or
        empty string if none were found."""
        if self.is_changed():
            return self.get_readable_description()
        return ""

    def get_model(self) -> TraitSelector:
        """This should never be called."""
        raise NotImplementedError

    def get_current_value(self):
        """This should never be called."""
        raise NotImplementedError

    def update_current_value(self):
        """This should never be called."""
        raise NotImplementedError


class KernelHolder(AbstractTraitHolder):
    """Trait holder for list of available Linux kernels"""
    def __init__(self, qapp: qubesadmin.Qubes, widget: Gtk.ComboBoxText):
        self.qapp = qapp
        self.widget = widget

        self.model = TextModeler(
            combobox=self.widget,
            values=self._get_kernel_options(),
            selected_value=self.get_current_value(),
            style_changes=True
        )

    def _get_kernel_options(self) -> Dict[str, str]:
        kernels = [kernel.vid for kernel in
                   self.qapp.pools['linux-kernel'].volumes]
        kernels = sorted(kernels, key=KernelVersion)
        kernels_dict = {kernel: kernel for kernel in kernels}
        kernels_dict['(none)'] = None
        return kernels_dict

    def get_readable_description(self) -> str:
        return _("Default kernel")

    def get_current_value(self):
        return self.qapp.default_kernel

    def update_current_value(self):
        if self.model.is_changed():
            self.qapp.default_kernel = self.model.get_selected()

    def get_model(self) -> TraitSelector:
        return self.model


class BasicSettingsHandler(PageHandler):
    """
    Handler for the Basic Settings page.
    """
    def __init__(self, gtk_builder: Gtk.Builder, qapp: qubesadmin.Qubes):
        """
        :param gtk_builder: gtk_builder object
        :param qapp: Qubes object
        """
        self.qapp = qapp
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.handlers: List[AbstractTraitHolder] = []

        self.clockvm_combo = gtk_builder.get_object('basics_clockvm_combo')
        self.deftemplate_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_deftemplate_combo')
        self.defnetvm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_defnetvm_combo')
        self.defdispvm_combo: Gtk.ComboBox = \
            gtk_builder.get_object('basics_defdispvm_combo')
        self.fullscreen_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_fullscreen_combo')
        self.utf_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_utf_windows_combo')
        self.tray_icon_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_tray_icon_combo')
        self.kernel_combo: Gtk.ComboBoxText = \
            gtk_builder.get_object('basics_kernel_combo')

        self.handlers.append(PropertyHandler(
            qapp=self.qapp, trait_holder=self.qapp, trait_name="clockvm",
            widget=self.clockvm_combo, vm_filter=self._clock_vm_filter,
            readable_name=_("Clock qube"), additional_options=NONE_CATEGORY))
        self.handlers.append(PropertyHandler(
            qapp=self.qapp, trait_holder=self.qapp,
            trait_name="default_template", widget=self.deftemplate_combo,
            vm_filter=self._default_template_filter,
            readable_name=_("Default template"),
            additional_options=NONE_CATEGORY))
        self.handlers.append(PropertyHandler(
            qapp=self.qapp, trait_holder=self.qapp, trait_name="default_netvm",
            widget=self.defnetvm_combo, vm_filter=self._default_netvm_filter,
            readable_name=_("Default net qube"),
            additional_options=NONE_CATEGORY))
        self.handlers.append(PropertyHandler(
            qapp=self.qapp, trait_holder=self.qapp, trait_name="default_dispvm",
            widget=self.defdispvm_combo, vm_filter=self._default_dispvm_filter,
            readable_name=_("Default disposable qube template"),
            additional_options=NONE_CATEGORY))
        self.handlers.append(FeatureHandler(
            trait_holder=self.vm, trait_name='gui-default-allow-fullscreen',
            widget=self.fullscreen_combo,
            options={_('default (disallow)'): None, _('allow'): True,
                     _('disallow'): False},
            readable_name=_("Allow fullscreen"), is_bool=True))
        self.handlers.append(FeatureHandler(
            trait_holder=self.vm, trait_name='gui-default-allow-utf8-titles',
            widget=self.utf_combo,
            options={_('default (disallow)'): None, _('allow'): True,
                     _('disallow'): False},
            readable_name=_("Allow utf8 window titles"), is_bool=True))
        self.handlers.append(FeatureHandler(
            trait_holder=self.vm, trait_name='gui-default-trayicon-mode',
            widget=self.tray_icon_combo,
            options={_('default (tinted icon)'): None,
             _('full background'): 'bg',
             _('thin border'): 'border1',
             _('thick border'): 'border2',
             _('tinted icon'): 'tint',
             _('tinted icon with modified white'): 'tint+whitehack',
             _('tinted icon with 50% saturation'): 'tint+saturation50'},
            readable_name="Tray icon mode", is_bool=False))
        self.handlers.append(KernelHolder(qapp=self.qapp,
                                          widget=self.kernel_combo))

        self.handlers.append(MemoryHandler(gtk_builder))

    @staticmethod
    def _clock_vm_filter(vm) -> bool:
        return vm.klass != 'TemplateVM'

    @staticmethod
    def _default_template_filter(vm) -> bool:
        return vm.klass == 'TemplateVM'

    @staticmethod
    def _default_netvm_filter(vm) -> bool:
        return getattr(vm, 'provides_network', False)

    @staticmethod
    def _default_dispvm_filter(vm) -> bool:
        return getattr(vm, 'template_for_dispvms', False)

    def save(self):
        for handler in self.handlers:
            handler.save()

    def reset(self):
        for handler in self.handlers:
            handler.reset()

    def get_unsaved(self) -> str:
        unsaved = []
        for handler in self.handlers:
            unsaved.append(handler.get_unsaved())
        return "\n".join([x for x in unsaved if x])
