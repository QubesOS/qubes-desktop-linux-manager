#!/usr/bin/python3 --
import os
import sys
from typing import Optional

# Modifying the environment while multiple threads
# are running leads to use-after-free in glibc, so
# ensure that only one thread is running.
if len(os.listdir("/proc/self/task")) != 1:
    raise RuntimeError("threads already running")
# If gi.override.Gdk has been imported, the GDK
# backend has already been set and it is too late
# to override it.
if "gi.override.Gdk" in sys.modules:
    raise RuntimeError("must import this module before loading GDK")
# Only the X11 backend is supported
os.environ["GDK_BACKEND"] = "x11"

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


is_xwayland = "WAYLAND_DISPLAY" in os.environ


class DisgustingX11FullscreenWindowHack:
    """
    No-op implementation of the hack, for use on stock X11.
    """

    def clear_widget(self, /) -> None:
        pass

    def show_for_widget(self, _widget: Gtk.Widget, /) -> None:
        pass


class DisgustingX11FullscreenWindowHackXWayland(
    DisgustingX11FullscreenWindowHack
):
    """
    GTK3 menus have a horrible bug under Xwayland: if the user clicks on a
    native Wayland surface, the menu is not dismissed.  This class works around
    the problem by using evil X11 hacks, such as a fullscreen override-redirect
    window that is made transparent.
    """

    _window: Gtk.Window
    _widget: Optional[Gtk.Widget]
    _unmap_signal_id: int
    _map_signal_id: int

    def __init__(self) -> None:
        self._widget = None
        # Get the default GDK screen.
        screen = Gdk.Screen.get_default()
        # This is deprecated, but it gets the total width and height
        # of all screens, which is what we want.  It will go away in
        # GTK4, but this code will never be ported to GTK4.
        width = screen.get_width()
        height = screen.get_height()
        # Create a window that will fill the screen.
        window = self._window = Gtk.Window()
        # Move that window to the top left.
        # pylint: disable=no-member
        window.move(0, 0)
        # Make the window fill the whole screen.
        # pylint: disable=no-member
        window.resize(width, height)
        # Request that the window not be decorated by the window manager.
        window.set_decorated(False)
        # Connect a signal so that the window and menu can be
        # unmapped (no longer shown on screen) once clicked.
        window.connect("button-press-event", self.on_button_press)
        # When the window is created, mark it as override-redirect
        # (invisible to the window manager) and transparent.
        window.connect("realize", self._on_realize)
        self._unmap_signal_id = self._map_signal_id = 0

    def clear_widget(self, /) -> None:
        """
        Clears the connected widget.  Automatically called by
        show_for_widget().
        """
        widget = self._widget
        map_signal_id = self._map_signal_id
        unmap_signal_id = self._unmap_signal_id

        # Double-disconnect is C-level undefined behavior, so ensure
        # it cannot happen.  It is better to leak memory if an exception
        # is thrown here.  GObject.disconnect_by_func() is buggy
        # (https://gitlab.gnome.org/GNOME/pygobject/-/issues/106),
        # so avoid it.
        if widget is not None:
            if map_signal_id != 0:
                # Clear the signal ID to avoid double-disconnect
                # if this method is interrupted and then called again.
                self._map_signal_id = 0
                widget.disconnect(map_signal_id)
            if unmap_signal_id != 0:
                # Clear the signal ID to avoid double-disconnect
                # if this method is interrupted and then called again.
                self._unmap_signal_id = 0
                widget.disconnect(unmap_signal_id)
        self._widget = None

    def show_for_widget(self, widget: Gtk.Widget, /) -> None:
        # Clear any existing connections.
        self.clear_widget()
        # Store the new widget.
        self._widget = widget
        # Connect map and unmap signals.
        self._unmap_signal_id = widget.connect("unmap", self._hide)
        self._map_signal_id = widget.connect("map", self._show)

    @staticmethod
    def _on_realize(window: Gtk.Window, /) -> None:
        window.set_opacity(0)
        window.get_window().set_override_redirect(True)

    def _show(self, widget: Gtk.Widget, /) -> None:
        assert widget is self._widget, "signal not properly disconnected"
        # pylint: disable=no-member
        self._window.show_all()

    def _hide(self, widget: Gtk.Widget, /) -> None:
        assert widget is self._widget, "signal not properly disconnected"
        self._window.hide()

    # pylint: disable=line-too-long
    def on_button_press(
        self, window: Gtk.Window, _event: Gdk.EventButton, /
    ) -> None:
        # Hide the window and the widget.
        window.hide()
        self._widget.hide()


def get_fullscreen_window_hack() -> DisgustingX11FullscreenWindowHack:
    if is_xwayland:
        return DisgustingX11FullscreenWindowHackXWayland()
    return DisgustingX11FullscreenWindowHack()
