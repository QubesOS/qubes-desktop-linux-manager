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
"""Handling application selection"""
# pylint: disable=import-error
import os
from typing import Optional, List
import logging

import qubesadmin.vm
from ..widgets.gtk_widgets import QubeName
from ..widgets.gtk_utils import load_icon

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


logger = logging.getLogger("qubes-new-qube")
WHONIX_QUBE_NAME = "sys-whonix"


class ApplicationData:
    """
    Class representing information about an available application.
    """

    def __init__(
        self,
        name: str,
        ident: str,
        comment: Optional[str] = None,
        template: Optional[qubesadmin.vm.QubesVM] = None,
    ):
        """
        :param name: application name
        :param ident: application id (as expected by qvm-appmenus)
        :param comment: optional comment
        :param template: optional qubes VM that is this app's template
        """
        self.name = name
        self.ident = ident
        self.template = template
        additional_description = ".desktop filename: " + str(self.ident)

        file_name_root = self.ident[: -len(".desktop")]
        self.icon_path = os.path.expanduser(
            f"~/.local/share/qubes-appmenus/{template}"
            f"/apps.tempicons/{file_name_root}.png"
        )

        if not comment:
            self.comment = additional_description
        else:
            self.comment = comment + "\n" + additional_description

    @classmethod
    def from_line(cls, line, template=None):
        """
        Create object from output line of qvm-appmenus, with optional template.
        """
        ident, name, comment = line.split("|", maxsplit=3)
        return cls(name=name, ident=ident, comment=comment, template=template)


class ApplicationRow(Gtk.ListBoxRow):
    """
    Row representing an app in current template.
    """

    def __init__(self, appdata: ApplicationData, **properties):
        """
        :param app_info: ApplicationInfo obj with data about related app file
        :param properties: additional Gtk.ListBoxRow properties
        """
        super().__init__(**properties)
        self.set_tooltip_text(appdata.comment)
        self.appdata = appdata
        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.label.set_yalign(0.5)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_max_width_chars(100)
        self.add(self.label)
        self.set_tooltip_text(self.appdata.comment)

        # this is a workaround for
        # https://gitlab.gnome.org/GNOME/gtk/-/issues/552
        self.set_selectable(False)
        self.set_activatable(True)


class OtherTemplateApplicationRow(Gtk.ListBoxRow):
    """
    Row representing an app in another template.
    """

    def __init__(self, appdata: ApplicationData, **properties):
        """
        :param app_info: ApplicationInfo obj with data about related app file
        :param properties: additional Gtk.ListBoxRow properties
        """
        super().__init__(**properties)
        self.set_tooltip_text(appdata.comment)
        self.appdata = appdata
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.box)
        self.appname_label = Gtk.Label()
        self.appname_label.set_text(self.appdata.name)
        self.appname_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.appname_label.set_max_width_chars(80)
        self.box.pack_start(self.appname_label, False, False, 0)

        self.middle_label = Gtk.Label()
        self.middle_label.set_text(_(" found in "))

        self.box.pack_start(self.middle_label, False, False, 0)
        self.end_label = QubeName(appdata.template)
        self.box.pack_start(self.end_label, False, False, 0)
        self.show_all()


class ApplicationButton(Gtk.FlowBoxChild):
    """
    Button representing a selected application.
    """

    def __init__(self, appdata: ApplicationData):
        """
        :param appdata: ApplicationData object
        """
        super().__init__()
        self.button = Gtk.Button(label=None)
        self.add(self.button)

        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.button.add(self.box)

        self.appdata = appdata

        self.icon = Gtk.Image()
        self.icon.set_from_pixbuf(load_icon(appdata.icon_path, 18, 18))

        self.box.pack_start(self.icon, False, False, 3)

        self.label = Gtk.Label()
        self.label.set_text(self.appdata.name)
        self.label.set_tooltip_text(self.appdata.comment)
        self.box.pack_start(self.label, False, False, 3)

        self.remove_icon = Gtk.Image()
        self.remove_icon.set_from_pixbuf(load_icon("qubes-delete", 14, 14))
        self.remove_icon.set_tooltip_text(
            _("Click to remove this application from selection")
        )
        self.box.pack_end(self.remove_icon, False, False, 3)

        self.connect("activate", self._remove_self)
        self.button.connect("clicked", self._activate_self)

        self.show_all()

    def _activate_self(self, *_args):
        self.activate()

    def _remove_self(self, *_args):
        self.get_parent().remove(self)

    def __str__(self):
        # pylint: disable=arguments-differ
        return self.appdata.name


class AddButton(Gtk.FlowBoxChild):
    """
    Button to open 'select apps' window.
    """

    def __init__(self):
        super().__init__()
        self.button = Gtk.Button()
        self.button.set_label("+")
        self.add(self.button)

        self.button.connect("clicked", self._activate_self)

    def _activate_self(self, *_args):
        self.activate()


class ApplicationBoxHandler:
    """
    Class to handle popup application box.
    """

    def __init__(self, gtk_builder: Gtk.Builder, template_selector):
        """
        :param gtk_builder: Gtk.Builder to get relevant objects
        :param template_selector: TemplateHandler object
        """
        self.template_selector = template_selector
        self.flowbox: Gtk.Flowbox = gtk_builder.get_object("applications")
        self.apps_window = gtk_builder.get_object("applications_popup")
        self.apps_list: Gtk.ListBox = gtk_builder.get_object("apps_list")
        self.label_apps: Gtk.Label = gtk_builder.get_object("label_apps")
        self.label_apps_explain: Gtk.Label = gtk_builder.get_object(
            "label_apps_explain"
        )
        self.apps_close: Gtk.Button = gtk_builder.get_object("apps_close")
        self.apps_search: Gtk.SearchEntry = gtk_builder.get_object(
            "apps_search"
        )
        self.apps_list_placeholder: Gtk.Label = gtk_builder.get_object(
            "apps_list_placeholder"
        )
        self.apps_list_other: Gtk.ListBox = gtk_builder.get_object(
            "apps_list_other_templates"
        )
        self.label_other_templates: Gtk.Label = gtk_builder.get_object(
            "label_other_templates"
        )
        self.load_all_button: Gtk.Button = gtk_builder.get_object(
            "apps_list_load_all"
        )

        self.change_template_msg: Gtk.Dialog = gtk_builder.get_object(
            "msg_change_template"
        )
        self.change_template_ok: Gtk.Button = gtk_builder.get_object(
            "change_template_ok"
        )
        self.change_template_cancel: Gtk.Button = gtk_builder.get_object(
            "change_template_cancel"
        )
        self.change_template_box: Gtk.Box = gtk_builder.get_object(
            "change_template_box"
        )
        self.target_template_name_widget: Optional[Gtk.Widget] = None

        self.change_template_cancel.connect(
            "clicked", self._hide_template_change
        )
        self.change_template_ok.connect("clicked", self._do_template_change)
        self.change_template_msg.connect(
            "key_press_event", self._keypress_change_template
        )

        self.apps_window.connect("key_press_event", self._keypress_event)
        self.apps_list.connect("row-activated", self._row_activated)

        self.fill_app_list(default=True)
        self._fill_flow_list()
        self.apps_close.connect("clicked", self._hide_window)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_search.connect("search-changed", self._do_search)
        self.template_selector.main_window.connect(
            "template-changed", self.template_change_registered
        )

        self.apps_list.set_filter_func(self._filter_func_app_list)
        self.apps_list.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_sort_func(self._sort_func_app_list)
        self.apps_list_other.set_filter_func(self._filter_func_other_list)
        self.load_all_button.connect("clicked", self._load_all_apps)

        self.flowbox.set_sort_func(self._sort_flowbox)

        self.apps_window.connect("delete-event", self._hide_window)
        self._fill_others_list()

    @staticmethod
    def _cmp(a, b):
        """Helper comparison function, made to comply with Gtk specs"""
        if a == b:
            return 0
        if a < b:
            return -1
        return 1

    def _sort_func_app_list(self, x: ApplicationRow, y: ApplicationRow):
        # negation because True > False, and we want the selected rows to be
        # at the top
        selection_comparison = self._cmp(
            not x.is_selected(), not y.is_selected()
        )
        if selection_comparison == 0:
            return self._cmp(x.appdata.name, y.appdata.name)
        return selection_comparison

    def _sort_flowbox(self, x, y):
        if isinstance(x, AddButton):
            return 1
        if isinstance(y, AddButton):
            return -1
        return self._cmp(str(x), str(y))

    def _filter_func_app_list(self, x: ApplicationRow):
        search_text = self.apps_search.get_text()
        if search_text:
            return search_text.lower() in x.appdata.name.lower()
        return True

    def _filter_func_other_list(self, x: ApplicationRow):
        if not self.apps_list_placeholder.get_mapped():
            return False
        if not self.template_selector.is_given_template_available(
            x.appdata.template
        ):
            return False
        return self._filter_func_app_list(x)

    def _load_all_apps(self, *_args):
        self.load_all_button.set_label("Loading applications...")

        while Gtk.events_pending():
            Gtk.main_iteration()

        self.template_selector.load_all_available_apps()
        self._fill_others_list()
        self.apps_list_other.invalidate_filter()

        while Gtk.events_pending():
            Gtk.main_iteration()

        self.apps_list_other.set_visible(True)
        self.load_all_button.set_label("No matching applications found")
        self.load_all_button.set_sensitive(False)

    @staticmethod
    def _row_activated(listbox: Gtk.ListBox, row: ApplicationRow):
        if not row.is_selected():
            row.set_selectable(True)
            listbox.select_row(row)
        else:
            row.set_selectable(False)

    def _do_search(self, *_args):
        self.apps_list.invalidate_filter()
        if self.apps_list_placeholder.get_mapped():
            self.apps_list_other.invalidate_filter()
            self.apps_list_other.set_visible(True)
            self.label_other_templates.set_visible(True)
        else:
            self.apps_list_other.set_visible(False)
            self.label_other_templates.set_visible(False)

    def template_change_registered(self, *_args):
        """
        Fired after template change is noticed.
        """
        self.fill_app_list(default=True)
        self._fill_flow_list()

    def fill_app_list(self, default=False):
        """Fill application list with apps matching current template."""
        for child in self.apps_list.get_children():
            self.apps_list.remove(child)

        template_vm = self.template_selector.get_selected_template()
        self.label_apps.set_visible(template_vm is not None)
        self.label_apps_explain.set_visible(template_vm is not None)
        if not template_vm:
            return

        available_applications = self.template_selector.get_available_apps(
            template_vm
        )
        selected = []
        if default:
            selected = self.template_selector.get_default_apps(template_vm)
        else:
            for button in self.flowbox.get_children():
                if isinstance(button, ApplicationButton):
                    selected.append(button.appdata.ident)

        for app in available_applications:
            row = ApplicationRow(app)
            self.apps_list.add(row)
            if app.ident in selected:
                row.activate()
            row.show_all()
        self.apps_list.invalidate_sort()
        self.apps_list_other.invalidate_sort()

    def _fill_others_list(self):
        # and the other apps
        for app in self.template_selector.get_available_apps():
            row = OtherTemplateApplicationRow(app)
            self.apps_list_other.add(row)
        self.apps_list_other.set_visible(False)
        self.apps_list_other.connect("row-activated", self._ask_template_change)

    def _hide_template_change(self, *_args):
        self.change_template_msg.hide()

    def _do_template_change(self, *_args):
        if self.target_template_name_widget:
            self.template_selector.select_template(
                self.target_template_name_widget.vm
            )
        self._hide_template_change()
        self._hide_window()

    def _ask_template_change(self, _widget, row, *_args):
        if self.target_template_name_widget:
            self.change_template_box.remove(self.target_template_name_widget)

        self.target_template_name_widget = QubeName(row.appdata.template)
        self.change_template_box.pack_start(
            self.target_template_name_widget, False, False, 0
        )

        self.change_template_msg.show()

    def _keypress_change_template(self, _widget, event, *_args):
        if event.keyval == Gdk.KEY_Escape:
            self._hide_template_change()
            return True
        if event.keyval == Gdk.KEY_ISO_Enter:
            self._do_template_change()
            return True
        return False

    def _fill_flow_list(self):
        template_vm = self.template_selector.get_selected_template()
        if template_vm is None:
            self.flowbox.set_visible(False)
            return
        self.flowbox.set_visible(True)
        for child in self.flowbox:
            self.flowbox.remove(child)

        for child in self.apps_list.get_children():
            if child.is_selected():
                button = ApplicationButton(child.appdata)
                self.flowbox.add(button)
        plus_button = AddButton()
        plus_button.connect("activate", self._choose_apps)
        # need interaction with Template object
        self.flowbox.add(plus_button)
        self.flowbox.show_all()

    def _choose_apps(self, *_args, **_kwargs):
        self.fill_app_list()
        self.apps_window.show()

    def _keypress_event(self, _widget, event, *_args):
        if event.keyval == Gdk.KEY_Escape:
            self._hide_window()
            return True
        return False

    def _hide_window(self, *_args):
        self._fill_flow_list()
        self.apps_window.hide()
        return True  # when connected to delete-event, this tells Gtk to
        # not attempt to destroy the window

    def get_selected_apps(self) -> List[str]:
        """
        Get list of currently selected apps' idents
        """
        apps: List[str] = []
        if not self.flowbox.get_visible():
            return apps
        for child in self.flowbox.get_children():
            if isinstance(child, ApplicationButton):
                apps.append(child.appdata.ident)

        return apps
