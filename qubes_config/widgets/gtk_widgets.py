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
Various Gtk widgets for use in Qubes tools.
"""
import gi

import abc
import qubesadmin.vm
import itertools

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

from typing import Optional, Callable, Dict, Any, Union, List

from .gtk_utils import load_icon, is_theme_light

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

NONE_CATEGORY = {"None": _("(none)")}


class TokenName(Gtk.Box):
    """
    A Gtk.Box containing a (optionally changing) nicely formatted token/vm name.
    """

    def __init__(
        self,
        token_name: str,
        qapp: qubesadmin.Qubes,
        categories: Optional[Dict[str, str]] = None,
    ):
        """
        :param token_name: string for of the token
        :param qapp: Qubes object
        :param categories: dict of human-readable names for token strings
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.qapp = qapp
        self.categories = categories if categories else {}
        self.token_name = token_name
        self.set_spacing(5)
        self.set_token(token_name)

    def set_token(self, token_name):
        """Set appropriate token/style for a given string."""
        self.token_name = token_name
        for child in self.get_children():
            self.remove(child)
        try:
            vm = self.qapp.domains[token_name]
            qube_name = QubeName(vm)
            self.add(qube_name)
        except KeyError:
            nice_name = self.categories.get(token_name, token_name)
            label = Gtk.Label()
            label.set_text(nice_name)
            label.get_style_context().add_class("qube-type")
            label.show_all()
            self.pack_start(label, False, False, 0)


class QubeName(Gtk.Box):
    """
    A Gtk.Box containing qube icon plus name, colored in the label color and
    bolded.
    """

    def __init__(self, vm: Optional[qubesadmin.vm.QubesVM]):
        """
        :param vm: Qubes VM to be represented.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.vm = vm
        self.label = Gtk.Label()
        self.label.set_label(vm.name if vm else _("None"))

        self.set_spacing(5)

        if vm is not None:
            self._image = Gtk.Image()
            self._image.set_from_pixbuf(load_icon(vm.icon, 20, 20))
            self._image.set_halign(Gtk.Align.CENTER)
            self.pack_start(self._image, False, False, 0)

        self.pack_start(self.label, False, False, 0)

        self.get_style_context().add_class("qube-box-base")
        if vm:
            self.get_style_context().add_class(f"qube-box-{vm.label}")
        else:
            self.get_style_context().add_class("qube-box-black")

        self.show_all()


class TraitSelector(abc.ABC):
    """abstract class representing various widgets for selecting trait value."""

    @abc.abstractmethod
    def get_selected(self):
        """
        Get selected value
        """

    @abc.abstractmethod
    def is_changed(self) -> bool:
        """
        Has the value changed from initial value?
        """

    @abc.abstractmethod
    def reset(self):
        """Restore the initially selected value"""

    @abc.abstractmethod
    def update_initial(self):
        """Mark the currently selected value as initial value, for use
        for instance for is_changed"""


class TextModeler(TraitSelector):
    """
    Class to handle modeling a text combo box.
    """

    def __init__(
        self,
        combobox: Gtk.ComboBoxText,
        values: Dict[str, Any],
        selected_value: Optional[Any] = None,
        style_changes: bool = False,
    ):
        """
        :param combobox: target ComboBoxText object
        :param values: dictionary of displayed strings and corresponding values.
        :param selected_value: which of the corresponding values should be
        selected initially; if None and there is no None value available,
         the first option will be selected; if provided value is not in the
         available choices, it will be added.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value is different from initial value.
        """
        self._combo: Gtk.ComboBoxText = combobox
        self._values: Dict[str, Any] = values

        if selected_value and selected_value not in self._values.values():
            self._values[selected_value] = selected_value

        self._initial_text = None
        for text, value in self._values.items():
            # to ensure that the correct option id is selected, we use
            # explicit id for both text and id
            self._combo.append(text, text)
            if selected_value and selected_value == value:
                self._initial_text = text
            elif selected_value is None and value is None:
                self._initial_text = text

        if self._initial_text:
            self._combo.set_active_id(self._initial_text)
        else:
            self._combo.set_active(0)
            self._initial_text = self._combo.get_active_text()

        if style_changes:
            self._combo.connect("changed", self._on_changed)

    def get_selected(self):
        """Get currently selected value."""
        return self._values[self._combo.get_active_text()]

    def is_changed(self) -> bool:
        """Return True is selected value has changed from initial."""
        return self._initial_text != self._combo.get_active_text()

    def select_value(self, selected_value):
        """Select provided value."""
        for key, value in self._values.items():
            if value == selected_value:
                self._combo.set_active_id(key)

    def reset(self):
        """Select initial value."""
        self._combo.set_active_id(self._initial_text)

    def _on_changed(self, _widget):
        self._combo.get_style_context().remove_class("combo-changed")
        if self.is_changed():
            self._combo.get_style_context().add_class("combo-changed")

    def update_initial(self):
        self._initial_text = self._combo.get_active_text()
        self._on_changed(None)


class VMListModeler(TraitSelector):
    """
    Modeler for Gtk.ComboBox contain a list of qubes VMs.
    Based on boring-stuff's code in core-qrexec qrexec_policy_agent.py.
    """

    def __init__(
        self,
        combobox: Gtk.ComboBox,
        qapp: qubesadmin.Qubes,
        filter_function: Optional[
            Callable[[qubesadmin.vm.QubesVM], bool]
        ] = None,
        event_callback: Optional[Callable[[], None]] = None,
        default_value: Optional[Union[qubesadmin.vm.QubesVM, str]] = None,
        current_value: Optional[Union[qubesadmin.vm.QubesVM, str]] = None,
        style_changes: bool = False,
        additional_options: Optional[Dict[str, str]] = None,
    ):
        """
        :param combobox: target ComboBox object
        :param qapp: Qubes object, necessary to retrieve VM info
        :param filter_function: function used to filter VMs, must take as input
        QubesVM object and return bool; caution: remember not all properties
        are always available for all VMs, in particular dom0 can cause problems
        :param event_callback: function to be called whenever combobox value
        changes
        :param default_value: default VM (will get a (default) decoration
        next to its name), and, if current_value not specified, it will be
        selected as the initial value
        :param current_value: value to be selected; if None and there is
        a default value, it will be selected; if neither exist,
         first position will be selected. If this value is not available in the
         entries, it will be added as top entry.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value changes
        :param additional_options: Dictionary of token: readable name of
        addiitonal options to be added to the combobox
        """
        self.qapp = qapp
        self.combo = combobox
        self.entry_box = self.combo.get_child()
        self.change_function = event_callback
        self.style_changes = style_changes

        self._entries: Dict[str, Dict[str, Any]] = {}

        self._icons: Dict[str, Gtk.Image] = {}
        self._icon_size = 20

        self._create_entries(
            filter_function, default_value, additional_options, current_value
        )

        self._apply_model()

        self._initial_id = None

        if current_value:
            self.select_value(current_value)
        elif default_value:
            self.select_value(default_value)
        else:
            self.combo.set_active(0)

        self._initial_id = self.combo.get_active_id()

    def connect_change_callback(self, event_callback):
        """Add a function to be run after combobox value is changed."""
        self.change_function = event_callback

    def is_changed(self) -> bool:
        """Return True if the combobox selected value has changed from the
        initial value."""
        if self._initial_id is None:
            return False
        return self._initial_id != self.combo.get_active_id()

    def update_initial(self):
        """Inform the widget that information on 'initial' value should
        be updated to whatever the current value is. Useful if saving changes
        happened."""
        self._initial_id = self.combo.get_active_id()
        if self.style_changes:
            self.entry_box.get_style_context().remove_class("combo-changed")

    def reset(self):
        """Reset changes."""
        self.combo.set_active_id(self._initial_id)

    def _get_icon(self, name):
        if name not in self._icons:
            icon = load_icon(name, self._icon_size, self._icon_size)
            self._icons[name] = icon
        return self._icons[name]

    def _create_entries(
        self,
        filter_function: Optional[Callable[[qubesadmin.vm.QubesVM], bool]],
        default_value: Optional[Union[qubesadmin.vm.QubesVM, str]],
        additional_options: Optional[Dict[str, str]] = None,
        current_value: Optional[str] = None,
    ):

        if additional_options:
            for api_name, display_name in additional_options.items():
                if api_name == default_value:
                    display_name += _(" (default)")
                self._entries[display_name] = {
                    "api_name": api_name,
                    "icon": None,
                    "vm": None,
                }

        for domain in self.qapp.domains:
            if filter_function and not filter_function(domain):
                continue
            vm_name = domain.name
            icon = self._get_icon(domain.icon)
            display_name = vm_name

            if domain == default_value:
                display_name = display_name + _(" (default)")

            self._entries[display_name] = {
                "api_name": vm_name,
                "icon": icon,
                "vm": domain,
            }

        if current_value:
            found_current = False
            for value in self._entries.values():
                if value["api_name"] == current_value:
                    found_current = True
                    break
            if not found_current:
                self._entries[str(current_value)] = {
                    "api_name": str(current_value),
                    "icon": None,
                    "vm": None,
                }

    def _get_valid_qube_name(self):
        selected = self.combo.get_active_id()
        if selected in self._entries:
            return selected

        typed = self.entry_box.get_text()
        if typed in self._entries:
            return typed

        return None

    def _combo_change(self, _widget):
        name = self._get_valid_qube_name()

        if name:
            entry = self._entries[name]
            self.entry_box.set_icon_from_pixbuf(
                Gtk.EntryIconPosition.PRIMARY, entry["icon"]
            )
        else:
            self.entry_box.set_icon_from_pixbuf(
                Gtk.EntryIconPosition.PRIMARY, load_icon("gtk-find", 18, 18)
            )

        if self.change_function:
            self.change_function()

        if self.style_changes:
            self.entry_box.get_style_context().remove_class("combo-changed")
            if self.is_changed():
                self.entry_box.get_style_context().add_class("combo-changed")

    def _apply_model(self):
        assert isinstance(self.combo, Gtk.ComboBox)
        list_store = Gtk.ListStore(int, str, GdkPixbuf.Pixbuf, str, str, str)

        for entry_no, display_name in zip(
            itertools.count(), sorted(self._entries)
        ):
            entry = self._entries[display_name]
            list_store.append(
                [
                    entry_no,
                    display_name,
                    entry["icon"],
                    entry["api_name"],
                    "#f2f2f2" if entry["vm"] is None else None,  # background
                    "#000000" if entry["vm"] is None else None,  # foreground
                ]
            )

        self.combo.set_model(list_store)
        self.combo.set_id_column(1)

        icon_column = Gtk.CellRendererPixbuf()
        self.combo.pack_start(icon_column, False)
        self.combo.add_attribute(icon_column, "pixbuf", 2)
        self.combo.set_entry_text_column(1)

        entry_box = self.combo.get_child()

        area = Gtk.CellAreaBox()
        area.pack_start(icon_column, False, False, False)
        area.add_attribute(icon_column, "pixbuf", 2)

        completion = Gtk.EntryCompletion.new_with_area(area)
        completion.set_inline_selection(True)
        completion.set_inline_completion(True)
        completion.set_popup_completion(True)
        completion.set_popup_single_match(False)
        completion.set_model(list_store)
        completion.set_text_column(1)

        entry_box.set_completion(completion)

        # A Combo with an entry has a text column already
        text_column: Gtk.CellRenderer = self.combo.get_cells()[0]
        self.combo.reorder(text_column, 1)

        # use list_store's 4th and 5th columns as source for background and
        # foreground color
        self.combo.add_attribute(text_column, "background", 4)
        self.combo.add_attribute(text_column, "foreground", 5)

        self.combo.connect("changed", self._combo_change)
        self.entry_box.connect("changed", self._event_callback)

    def _event_callback(self, *_args):
        if self.change_function:
            self.change_function()

    def __str__(self):
        return self.entry_box.get_text()

    def get_selected(self) -> Optional[qubesadmin.vm.QubesVM]:
        """
        Get currently selected VM, if any
        :return: QubesVM object
        """
        selected = self._get_valid_qube_name()

        if selected in self._entries:
            # special treatment for None:
            if self._entries[selected]["api_name"] == "None":
                return None
            return (
                self._entries[selected]["vm"]
                or self._entries[selected]["api_name"]
            )
        return None

    def select_value(self, vm_name):
        """
        Select VM by name.
        :param vm_name: str
        :return: None
        """
        for display_name, entry in self._entries.items():
            if entry["api_name"] == vm_name:
                self.combo.set_active_id(display_name)

    def is_vm_available(self, vm: qubesadmin.vm.QubesVM) -> bool:
        """Check if given VM is available in the list."""
        for entry in self._entries.values():
            if entry["vm"] == vm:
                return True
        return False


class ImageListModeler(TraitSelector):
    """
    Modeler for Gtk.ComboBox contain a list of icons accompanied by names.
    """

    def __init__(
        self,
        combobox: Gtk.ComboBox,
        value_list: Dict[str, Dict[str, Any]],
        event_callback: Optional[Callable[[], None]] = None,
        selected_value: Optional[str] = None,
        style_changes: bool = False,
    ):
        """
        :param combobox: target ComboBox object
        :param value_list: entries to be stored, in the form of a dict
        where key is the visible name and there are two entries: icon,
        with a str name of the icon to be used, and object, with the
        corresponding value
        :param event_callback: function to be called whenever combobox value
        changes
        :param selected_value: visible str that should be initially selected.
        :param style_changes: if True, combo-changed style class will be
        applied when combobox value changes
        """
        self.combo = combobox
        self.entry_box = self.combo.get_child()
        self.change_function = event_callback
        self.style_changes = style_changes

        self.icon_size = 20

        self._entries: Dict[str, Dict[str, Any]] = value_list

        for entry in self._entries.values():
            entry["loaded_icon"] = load_icon(
                entry["icon"], self.icon_size, self.icon_size
            )

        self._apply_model()

        self._initial_id = None

        if selected_value:
            self.select_name(selected_value)
        else:
            self.combo.set_active(0)

        self._initial_id = self.combo.get_active_id()

    def connect_change_callback(self, event_callback):
        """Add a function to be run after combobox value is changed."""
        self.change_function = event_callback

    def is_changed(self) -> bool:
        """Return True if the combobox selected value has changed from the
        initial value."""
        if self._initial_id is None:
            return False
        return self._initial_id != self.combo.get_active_id()

    def update_initial(self):
        """Inform the widget that information on 'initial' value should
        be updated to whatever the current value is. Useful if saving changes
        happened."""
        self._initial_id = self.combo.get_active_id()
        if self.style_changes:
            self.entry_box.get_style_context().remove_class("combo-changed")

    def reset(self):
        """Reset changes."""
        self.combo.set_active_id(self._initial_id)

    def _combo_change(self, _widget):
        if self.change_function:
            self.change_function()

        if self.style_changes:
            self.entry_box.get_style_context().remove_class("combo-changed")
            if self.is_changed():
                self.entry_box.get_style_context().add_class("combo-changed")

    def _apply_model(self):
        assert isinstance(self.combo, Gtk.ComboBox)
        list_store = Gtk.ListStore(str, GdkPixbuf.Pixbuf)

        for entry_name, entry in self._entries.items():
            list_store.append(
                [
                    entry_name,  # 0: displayed name
                    entry["loaded_icon"],  # 1: icon
                ]
            )

        self.combo.set_model(list_store)
        self.combo.set_id_column(0)

        icon_column = Gtk.CellRendererPixbuf()
        self.combo.pack_start(icon_column, False)
        self.combo.add_attribute(icon_column, "pixbuf", 1)

        area = Gtk.CellAreaBox()
        area.pack_start(icon_column, False, False, False)
        area.add_attribute(icon_column, "pixbuf", 1)

        # A Combo with an entry has a text column already
        text_column: Gtk.CellRenderer = Gtk.CellRendererText()
        self.combo.pack_start(text_column, False)
        self.combo.add_attribute(text_column, "text", 0)

        self.combo.connect("changed", self._combo_change)

    def _event_callback(self, *_args):
        if self.change_function:
            self.change_function()

    def __str__(self):
        return self.entry_box.get_text()

    def get_selected(self) -> Optional[Any]:
        """
        Get currently selected object, if any
        :return: any object
        """
        selected = self.combo.get_active_id()
        if selected in self._entries:
            return self._entries[selected]["object"]
        return None

    def select_name(self, name):
        """
        Select option by displayed name.
        """
        self.combo.set_active_id(name)


class ImageTextButton(Gtk.Button):
    """Button with image and callback function. A simple helper
    to avoid boilerplate."""

    def __init__(
        self,
        icon_name: str,
        label: Optional[str],
        click_function: Optional[Callable[[Any], Any]] = None,
        style_classes: Optional[List[str]] = None,
    ):
        super().__init__()
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(load_icon(icon_name, 20, 20))
        self.box.pack_start(self.image, False, False, 10)
        if label:
            self.label = Gtk.Label()
            self.label.set_text(label)
            self.box.pack_start(self.label, False, False, 10)
        self.add(self.box)

        if style_classes:
            for cls in style_classes:
                self.get_style_context().add_class(cls)
        if click_function:
            self.connect("clicked", click_function)
        else:
            self.set_sensitive(False)

        self.show_all()


class ProgressBarDialog(Gtk.Window):
    """Simple window showing a progress bar."""

    def __init__(self, parent_application: Gtk.Application, loading_text: str):
        super().__init__()
        self.parent_application = parent_application

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.box)

        label = Gtk.Label()
        label.set_text(loading_text)
        self.box.pack_start(label, False, False, 10)
        self.box.get_style_context().add_class("modal_dialog")

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.get_style_context().add_class("loading")
        self.progress_bar.set_fraction(0)
        self.current_progress = 0

        self.box.pack_start(self.progress_bar, False, False, 10)

        self.update_progress(0)

        self.connect("delete-event", self._quit)

    def update_progress(self, value):
        """Update current progressbar progress"""
        self.current_progress += value
        self.current_progress = min(self.current_progress, 1)

        self.progress_bar.set_fraction(self.current_progress)

        while Gtk.events_pending():
            Gtk.main_iteration_do(True)

    def _quit(self, *_args):
        self.parent_application.quit()


class ExpanderHandler:
    """A class to handle showing/hiding something on click."""

    def __init__(
        self,
        event_button: Gtk.Button,
        data_container: Gtk.Container,
        icon: Gtk.Image,
        label: Optional[Gtk.Label] = None,
        text_shown: Optional[str] = None,
        text_hidden: Optional[str] = None,
        event_callback: Optional[Callable[[bool], None]] = None,
    ):
        """
        :param event_button: Gtk.Button that collects the click event
        :param data_container: the container with things to hide/show
        :param icon: icon that shows an expander icon
        :param label: optionally, a label that requires text changes
        :param text_shown: if label is provided, will be used as text when
        data is shown
        :param text_hidden: if label is provided, will be used as text when
        data is hidden
        :param event_callback: if provided, will be called after state is
        changed, with the new state provided as parameter (True - shown,
        False - hidden)
        """
        self.event_button = event_button
        self.data_container = data_container
        self.label = label
        self.icon = icon
        self.event_callback = event_callback

        self.event_button.connect("clicked", self._show_hide)

        self.text_shown = text_shown
        self.text_hidden = text_hidden

        # get variant
        suffix = "black" if is_theme_light(Gtk.Window()) else "white"
        self.icon_hidden = load_icon(f"qubes-expander-hidden-{suffix}", 18, 18)
        self.icon_shown = load_icon(f"qubes-expander-shown-{suffix}", 20, 20)

        self.set_state(False)

    def _show_hide(self, *_args):
        self.set_state(not self.data_container.get_visible())

    def set_state(self, state: bool):
        """Show data if state is true, hide it otherwise"""
        self.data_container.set_visible(state)

        if state:
            self.icon.set_from_pixbuf(self.icon_shown)
            if self.label:
                self.label.set_text(self.text_shown)
            for child in reversed(self.data_container.get_children()):
                if child.get_can_focus():
                    child.grab_focus()

        else:
            self.icon.set_from_pixbuf(self.icon_hidden)
            if self.label:
                self.label.set_text(self.text_hidden)

        if self.event_callback:
            self.event_callback(state)


class ViewportHandler:
    """A class that enables auto-scrolling to the focused widget."""

    def __init__(
        self,
        main_window: Gtk.Window,
        scrolled_windows: List[Gtk.ScrolledWindow],
    ):
        self.scrolled_windows = scrolled_windows
        self.main_window = main_window

        for window in scrolled_windows:
            child = window.get_child()
            adjustment = child.get_vadjustment()
            child.get_child().set_focus_vadjustment(adjustment)
