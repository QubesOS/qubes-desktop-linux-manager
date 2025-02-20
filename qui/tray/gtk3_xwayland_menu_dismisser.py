import os
import sys
from typing import Optional

# If gi.override.Gdk has been imported, the GDK
# backend has already been set and it is too late
# to override it.
assert (
    "gi.override.Gdk" not in sys.modules
), "must import this module before loading GDK"

# Modifying the environment while multiple threads
# are running leads to use-after-free in glibc, so
# ensure that only one thread is running.
assert (
    len(os.listdir("/proc/self/task")) == 1
), "multiple threads already running"

# Only the X11 backend is supported
os.environ["GDK_BACKEND"] = "x11"

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


is_xwayland = "WAYLAND_DISPLAY" in os.environ


class X11FullscreenWindowHack:
    """
    No-op implementation of the hack, for use on stock X11.
    """

    def clear_widget(self) -> None:
        pass

    def show_for_widget(self, _widget: Gtk.Widget, /) -> None:
        pass


class X11FullscreenWindowHackXWayland(X11FullscreenWindowHack):
    """
    GTK3 menus have a bug under Xwayland: if the user clicks on a native
    Wayland surface, the menu is not dismissed.  This class works around
    the problem by using a fullscreen transparent override-redirect
    window.  This is a horrible hack because if the application freezes,
    the user won't be able to click on any other applications.  That's
    no worse than under native X11, though.
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
        # The signal IDs of the map and unmap signals, so that this class
        # can stop listening to signals from the old menu when it is
        # replaced or unregistered.
        self._unmap_signal_id = self._map_signal_id = 0

    def clear_widget(self) -> None:
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
        gdk_window = window.get_window()
        gdk_window.set_override_redirect(True)
        window.get_root_window().set_cursor(
            Gdk.Cursor.new_for_display(
                display=gdk_window.get_display(),
                cursor_type=Gdk.CursorType.ARROW,
            )
        )

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


def get_fullscreen_window_hack() -> X11FullscreenWindowHack:
    if is_xwayland:
        return X11FullscreenWindowHackXWayland()
    return X11FullscreenWindowHack()
