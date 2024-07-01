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
"""Utility functions using Gtk"""
import contextlib
import importlib.resources
import os

import fcntl

from typing import Dict, Union, Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, GLib, Gdk

import gettext
t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

RESPONSES_OK = {
    _('_OK'): Gtk.ResponseType.OK
}

RESPONSES_YES_NO_CANCEL = {
    _("_Yes"): Gtk.ResponseType.YES,
    _("_No"): Gtk.ResponseType.NO,
    _("_Cancel"): Gtk.ResponseType.CANCEL
}

APPVIEWER_LOCK = "/var/run/qubes/appviewer.lock"
DATA = "/var/run/qubes/qubes-clipboard.bin"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"
XEVENT = "/var/run/qubes/qubes-clipboard.bin.xevent"


def load_icon_at_gtk_size(icon_name,
                          icon_size: Gtk.IconSize = Gtk.IconSize.LARGE_TOOLBAR):
    """Load icon from provided name, if available. If not, attempt to treat
    provided name as a path. If icon not found in any of the above ways,
    load a blank icon of specified size, provided as Gtk.IconSize.
    Returns GdkPixbuf.Pixbuf.
    """
    _size, width, height = Gtk.icon_size_lookup(icon_size)
    return load_icon(icon_name, width, height)


def load_icon(icon_name: str, width: int = 24, height: int = 24):
    """Load icon from provided name, if available. If not, attempt to treat
    provided name as a path. If icon not found in any of the above ways,
    load a blank icon of specified size.
    Returns GdkPixbuf.Pixbuf.
    width and height must be in pixels.
    """
    try:
        # icon_name is a path
        return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_name, width, height)
    except (GLib.Error, TypeError):
        try:
            # icon_name is a name
            image: GdkPixbuf.Pixbuf = Gtk.IconTheme.get_default().load_icon(
                icon_name, width, 0)
            return image
        except (TypeError, GLib.Error):
            # icon not found in any way
            pixbuf: GdkPixbuf.Pixbuf = GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, True, 8, width, height)
            pixbuf.fill(0x000)
            return pixbuf


def show_error(parent, title, text):
    """
    Helper function to display error messages.
    """
    return show_dialog_with_icon(parent=parent, title=title, text=text,
                                 buttons=RESPONSES_OK, icon_name="qubes-info")


def ask_question(parent, title: str, text: str):
    """
    Helper function to show question dialogs.
    """
    return show_dialog_with_icon(
        parent=parent,
        title=title,
        text=text,
        buttons=RESPONSES_YES_NO_CANCEL,
        icon_name="qubes-ask"
    )


def show_dialog_with_icon(
        parent: Optional[Gtk.Widget],
        title: str,
        text: Union[str, Gtk.Widget],
        buttons: Dict[str, Gtk.ResponseType],
        icon_name: str
) -> Gtk.ResponseType:
    """
    Helper function to show a dialog with icon given by name.
    """
    icon = Gtk.Image.new_from_pixbuf(load_icon(icon_name, 48, 48))
    dialog = show_dialog(parent, title, text, buttons, icon)
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.DELETE_EVENT:
        if Gtk.ResponseType.CANCEL in buttons.values():
        # treat exiting from the window as cancel if it's one of the
        # available responses, then no if it's one of the available responses
            return Gtk.ResponseType.CANCEL
        if Gtk.ResponseType.NO in buttons.values():
            return Gtk.ResponseType.NO
    return response


def show_dialog(
        parent: Gtk.Widget,
        title: str,
        text: Union[str, Gtk.Widget],
        buttons: Dict[str, Gtk.ResponseType],
        widget: Gtk.Widget
) -> Gtk.ResponseType:
    """
    Show a dialog.
    :param parent: parent widget, preferably the top level window
    :param title: title of the prompt
    :param text: prompt text (can use pango markup)
    :param
    :param buttons: dict of button-text: response type to use
    :param widget: widget to be show on the right side of
    the question
    :return: which button was pressed
    """
    dialog: Gtk.Dialog = Gtk.Dialog.new()
    dialog.set_modal(True)
    if parent:
        dialog.set_transient_for(parent.get_toplevel())

    for key, value in buttons.items():
        button: Gtk.Button = dialog.add_button(key, value)
        button.set_use_underline(True)
        button.get_style_context().add_class('flat_button')
        if value in [Gtk.ResponseType.YES, Gtk.ResponseType.OK]:
            button.get_style_context().add_class('button_save')
        else:
            button.get_style_context().add_class('button_cancel')

    dialog.set_title(title)

    content_area: Gtk.Box = dialog.get_content_area()
    content_area.get_style_context().add_class('modal_dialog')

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    box.get_style_context().add_class('modal_contents')
    content_area.pack_start(box, False, False, 0)

    box.pack_start(widget, False, False, 0)

    if isinstance(text, str):
        label: Gtk.Label = Gtk.Label()
        label.set_markup(text)
        label.set_line_wrap_mode(Gtk.WrapMode.WORD)
        label.set_max_width_chars(200)
        label.set_xalign(0)

        box.pack_start(label, False, False, 40)
    else:
        box.pack_start(text, False, False, 40)

    dialog.show_all()
    return dialog


def load_theme(widget: Gtk.Widget, light_theme_path: Optional[str] = None,
               dark_theme_path: Optional[str] = None,
               package_name: Optional[str] = None,
               light_file_name: Optional[str] = None,
               dark_file_name: Optional[str] = None) -> Gtk.CssProvider:
    """
    Load a dark or light theme to current screen, based on widget's
    current (system) defaults.
    :param widget: Gtk.Widget, preferably main window
    :param light_theme_path: path to file with light theme css
    :param dark_theme_path: path to file with dark theme css
    Alternatively, you can provide:
    :param package_name: name of the package
    :param light_file_name: name of the css file with light theme
    :param dark_file_name: name of the css file with dark theme
    Returns used CSS provider; it can be safely discarded if unused.
    """
    if not light_theme_path and light_file_name:
        assert package_name
        css_path = importlib.resources.files(package_name) / light_file_name
        with importlib.resources.as_file(css_path) as resource_path:
            light_theme_path = str(resource_path)
    if not dark_theme_path and dark_file_name:
        assert package_name
        css_path = importlib.resources.files(package_name) / dark_file_name
        with importlib.resources.as_file(css_path) as resource_path:
            dark_theme_path = str(resource_path)

    path = light_theme_path if is_theme_light(widget) else dark_theme_path

    screen = Gdk.Screen.get_default()
    provider = Gtk.CssProvider()
    provider.load_from_path(path)
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return provider


def is_theme_light(widget):
    """Check if current theme is light or dark"""
    style_context: Gtk.StyleContext = widget.get_style_context()
    background_color: Gdk.RGBA = style_context.get_background_color(
        Gtk.StateType.NORMAL)
    text_color: Gdk.RGBA = style_context.get_color(
        Gtk.StateType.NORMAL)
    background_intensity = background_color.red + \
                           background_color.blue + background_color.green
    text_intensity = text_color.red + text_color.blue + text_color.green

    return text_intensity < background_intensity


@contextlib.contextmanager
def appviewer_lock():
    """Used for purposes of copying to Qubes Global Clipboard"""
    fd = os.open(APPVIEWER_LOCK, os.O_RDWR | os.O_CREAT, 0o0666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def copy_to_global_clipboard(text: str):
    """Copy provided text to global clipboard"""
    with appviewer_lock():
        with open(DATA, "w", encoding='utf-8') as contents:
            contents.write(text)
        with open(FROM, "w", encoding='ascii') as source:
            source.write("dom0")
        with open(XEVENT, "w", encoding='ascii') as timestamp:
            timestamp.write(str(Gtk.get_current_event_time()))
