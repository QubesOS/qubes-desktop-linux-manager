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
"""Tests for gtk utils"""
from unittest.mock import patch, call

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk, Gdk

from ..widgets.gtk_utils import (
    load_icon,
    load_icon_at_gtk_size,
    ask_question,
    show_error,
    is_theme_light,
)


def test_load_icon():
    """Test loading icon methods; tests if they don't error out and
    return a pixbuf of correct size"""
    # load from existing file
    icon_from_file = load_icon_at_gtk_size("../icons/question_icon.svg")
    # load from an existing icon
    icon_from_name = load_icon("xterm")
    # load from missing name
    icon_from_error = load_icon("qwertyuiop")

    assert (24, 24) == (icon_from_file.get_height(), icon_from_file.get_width())
    assert (24, 24) == (icon_from_name.get_height(), icon_from_name.get_width())
    assert (24, 24) == (
        icon_from_error.get_height(),
        icon_from_error.get_width(),
    )

    assert isinstance(icon_from_file, GdkPixbuf.Pixbuf)
    assert isinstance(icon_from_name, GdkPixbuf.Pixbuf)
    assert isinstance(icon_from_error, GdkPixbuf.Pixbuf)


def test_ask_question():
    """Simple test to see if the function does something
    and if the function correctly executes run and destroy (instead of,
    e.g., just show)"""
    window = Gtk.Window()

    with patch("gi.repository.Gtk.Dialog") as mock_dialog:
        ask_question(window, "Text", "Text")
        assert call.new().run() in mock_dialog.mock_calls
        assert call.new().destroy() in mock_dialog.mock_calls

    with patch("gi.repository.Gtk.Dialog") as mock_dialog:
        show_error(window, "Text", "Text")
        assert call.new().run() in mock_dialog.mock_calls
        assert call.new().destroy() in mock_dialog.mock_calls


def test_get_theme():
    """test getting light/dark theme"""
    # first test dark theme
    screen = Gdk.Screen.get_default()
    provider = Gtk.CssProvider()
    provider.load_from_data(
        b"""
label {
    background: black;
    color: red;
}
"""
    )
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    label = Gtk.Label()

    assert not is_theme_light(label)

    # and a simple light theme

    screen = Gdk.Screen.get_default()
    provider = Gtk.CssProvider()
    provider.load_from_data(
        b"""
label {
    background: white;
    color: blue;
}"""
    )
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    label = Gtk.Label()

    assert is_theme_light(label)
