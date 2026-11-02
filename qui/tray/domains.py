#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position,import-error,superfluous-parens
"""A menu listing domains"""

# Must be imported before creating threads
from .gtk3_xwayland_menu_dismisser import (
    get_fullscreen_window_hack,
)  # isort:skip

import asyncio
import math
import os
import sys
import time
import traceback
import abc

import gi  # isort:skip
import qubesadmin
import qubesadmin.events
from qubesadmin import exc

import qui.decorators
import qui.utils

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gdk, Gio, Gtk, GLib, GdkPixbuf  # isort:skip

try:
    from gi.events import GLibEventLoopPolicy

    asyncio.set_event_loop_policy(GLibEventLoopPolicy())
except ImportError:
    import gbulb

    gbulb.install()

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext


def vm_has_gui(vm):
    """Return whether GUI applications can be started in *vm*."""
    return bool(
        getattr(vm, "guivm", None) and vm.features.check_with_template("gui", True)
    )


class IconCache:
    def __init__(self):
        self.icon_files = {
            "pause": "qubes-vm-pause",
            "terminal": "qubes-terminal",
            "preferences": "qubes-vm-settings",
            "kill": "qubes-vm-kill",
            "shutdown": "qubes-vm-shutdown",
            "unpause": "qubes-vm-unpause",
            "files": "qubes-files",
            "restart": "qubes-vm-restart",
            "debug": "bug-play",
            "logs": "scroll-text",
        }
        self.icons = {}

    def get_icon(self, icon_name):
        if icon_name in self.icons:
            icon = self.icons[icon_name]
        else:
            try:
                icon = Gtk.IconTheme.get_default().load_icon(
                    self.icon_files[icon_name], 16, Gtk.IconLookupFlags.FORCE_SIZE
                )
                self.icons[icon_name] = icon
            except (TypeError, GLib.Error):
                icon = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 16, 16)
                icon.fill(0)
                self.icons[icon_name] = icon
        return icon


def show_error(title, text):
    dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK)
    dialog.set_title(title)
    dialog.set_markup(text)
    dialog.connect("response", lambda *x: dialog.destroy())
    GLib.idle_add(dialog.show)


class ABCGtkMenuItemMeta(abc.ABCMeta, type(Gtk.MenuItem)):
    pass


class ActionMenuItem(Gtk.MenuItem, metaclass=ABCGtkMenuItemMeta):
    def __init__(self, label, img=None, icon_cache=None, icon_name=None):
        super().__init__()

        # Create a horizontal box for layout
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Add an icon to the menu item, if provided
        if icon_cache and icon_name:
            img = Gtk.Image.new_from_pixbuf(icon_cache.get_icon(icon_name))
        if img:
            img.show()
            box.pack_start(img, False, False, 0)
        else:
            # Add a placeholder to keep alignment consistent
            # when no icon is present
            placeholder = Gtk.Label()
            placeholder.set_size_request(24, -1)
            box.pack_start(placeholder, False, False, 0)

        # Add a label to the menu item
        self.label = Gtk.Label(label=label, xalign=0)
        box.pack_start(self.label, True, True, 0)

        # Add the box to the menu item
        self.add(box)

        # Connect the "activate" signal to the async function
        self.connect("activate", self.on_activate)

    @abc.abstractmethod
    async def perform_action(self):
        """
        Action this item should perform (to be implemented by subclasses).
        """

    def on_activate(self, *_args, **_kwargs):
        asyncio.create_task(self.perform_action())


class VMActionMenuItem(ActionMenuItem):
    # pylint: disable=abstract-method
    def __init__(self, vm, label, img=None, icon_cache=None, icon_name=None):
        super().__init__(
            label=label, img=img, icon_cache=icon_cache, icon_name=icon_name
        )
        self.vm = vm


class PauseItem(VMActionMenuItem):
    """Shutdown menu Item. When activated pauses the domain."""

    def __init__(self, vm, icon_cache):
        super().__init__(
            vm,
            label=_("Emergency pause"),
            icon_cache=icon_cache,
            icon_name="pause",
        )

    async def perform_action(self):
        try:
            await asyncio.to_thread(self.vm.pause)
        except exc.QubesException as ex:
            show_error(
                _("Error pausing qube"),
                _(
                    "The following error occurred while "
                    "attempting to pause qube {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )


class UnpauseItem(VMActionMenuItem):
    """Unpause menu Item. When activated unpauses the domain."""

    def __init__(self, vm, icon_cache):
        super().__init__(
            vm, label=_("Unpause"), icon_cache=icon_cache, icon_name="unpause"
        )

    async def perform_action(self):
        try:
            await asyncio.to_thread(self.vm.unpause)
        except exc.QubesException as ex:
            show_error(
                _("Error unpausing qube"),
                _(
                    "The following error occurred while attempting "
                    "to unpause qube {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )


class ShutdownItem(VMActionMenuItem):
    """Shutdown menu Item. When activated shutdowns the domain."""

    def __init__(
        self,
        vm,
        icon_cache,
        force=False,
        follow_shift=True,
        label=None,
        force_label=None,
        icon_name="shutdown",
    ):
        if force:
            init_label = force_label or _("Force shutdown")
        else:
            init_label = label or _("Shutdown")
        super().__init__(
            vm,
            label=init_label,
            icon_cache=icon_cache,
            icon_name=icon_name,
        )
        self.force = force
        self.follow_shift = follow_shift

    def set_force(self, force):
        if not self.follow_shift:
            return
        self.force = force
        if self.force:
            self.label.set_text(_("Force shutdown"))
        else:
            self.label.set_text(_("Shutdown"))

    async def perform_action(self):
        try:
            await asyncio.to_thread(self.vm.shutdown, force=self.force, wait=True)
        except exc.QubesException as ex:
            self.show_shutdown_dialog(ex)

    def shutdown_exception_body(self, ex):
        if isinstance(ex, exc.QubesVMInUseError):
            title = _("Qube {0} is in use").format(self.vm.name)
            markup = _(
                "The qube <b>{0}</b> could not be shut down because it "
                "is in use by connected qubes.\n\n"
                "<b>Warning:</b> force shutdown may cause unexpected "
                "issues in connected qubes."
            ).format(self.vm.name)
            action = "force"
        elif isinstance(ex, exc.QubesVMShutdownTimeoutError):
            title = _("Qube {0} shutdown timed out").format(self.vm.name)
            markup = _(
                "The qube <b>{0}</b> did not shut down within the "
                "expected time.\n\nYou can retry the shutdown or, "
                "if the problem persists, kill the qube."
            ).format(self.vm.name)
            action = "timeout"
        else:
            title = _("Error shutting down qube {0}").format(self.vm.name)
            markup = _(
                "The qube <b>{0}</b> could not be shut down. "
                "The following error occurred:\n"
                "<tt>{1}</tt>\n\n"
                "Would you like to kill the qube?"
            ).format(self.vm.name, str(ex))
            action = "kill"
        return title, markup, action

    def show_shutdown_dialog(self, ex):
        title, markup, action = self.shutdown_exception_body(ex)
        dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.NONE)
        dialog.set_title(title)
        dialog.set_markup(markup)
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        if action == "force":
            dialog.add_button(_("Force shutdown"), Gtk.ResponseType.OK)
        elif action == "timeout":
            if self.force:
                dialog.add_button(_("Retry force shutdown"), Gtk.ResponseType.OK)
            else:
                dialog.add_button(_("Retry shutdown"), Gtk.ResponseType.OK)
            dialog.add_button(_("Kill"), Gtk.ResponseType.YES)
        elif action == "kill":
            dialog.add_button(_("Kill"), Gtk.ResponseType.OK)
        dialog.connect("response", self.react_to_question, action)
        GLib.idle_add(dialog.show)

    def react_to_question(self, widget, response, action):
        asyncio.create_task(self.react_to_question_async(widget, response, action))

    async def react_to_question_async(self, widget, response, action):
        widget.destroy()
        try:
            await self.shutdown_from_response(response, action)
        except exc.QubesException as ex:
            self.show_shutdown_dialog(ex)

    async def shutdown_from_response(self, response, action):
        if action == "force":
            self.set_force(True)
            await asyncio.to_thread(self.vm.shutdown, force=True, wait=True)
        elif action == "timeout":
            if response == Gtk.ResponseType.YES:
                await asyncio.to_thread(self.vm.kill)
            elif response == Gtk.ResponseType.OK:
                await asyncio.to_thread(self.vm.shutdown, force=self.force, wait=True)
        elif action == "kill" and response == Gtk.ResponseType.OK:
            await asyncio.to_thread(self.vm.kill)


class RestartItem(ShutdownItem):
    """Restart menu Item. When activated shutdowns the domain and
    then starts it again."""

    def __init__(self, vm, icon_cache, force=False):
        super().__init__(
            vm,
            icon_cache,
            force=force,
            label=_("Restart"),
            force_label=_("Force restart"),
            icon_name="restart",
        )
        self.give_up = False

    def set_force(self, force):
        self.force = force
        if self.force:
            self.label.set_text(_("Force restart"))
        else:
            self.label.set_text(_("Restart"))

    async def start(self):
        if self.give_up:
            return
        try:
            await asyncio.to_thread(self.vm.start)
        except exc.QubesException as ex:
            show_error(
                _("Error restarting qube"),
                _(
                    "The following error occurred when restarting the qube "
                    "during start stage: {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )

    async def perform_action(self, *_args, **_kwargs):
        try:
            await asyncio.to_thread(self.vm.shutdown, force=self.force, wait=True)
        except exc.QubesException as ex:
            self.show_shutdown_dialog(ex)
        else:
            await self.start()

    def react_to_question(self, widget, response, action):
        asyncio.create_task(self.react_to_question_async(widget, response, action))

    async def react_to_question_async(self, widget, response, action):
        widget.destroy()
        if response not in (Gtk.ResponseType.OK, Gtk.ResponseType.YES):
            self.give_up = True
            return
        try:
            await self.shutdown_from_response(response, action)
        except exc.QubesException as ex:
            self.show_shutdown_dialog(ex)
        else:
            await self.start()


class KillItem(VMActionMenuItem):
    """Kill domain menu Item. When activated kills the domain."""

    def __init__(self, vm, icon_cache):
        super().__init__(vm, label=_("Kill"), icon_cache=icon_cache, icon_name="kill")

    async def perform_action(self, *_args, **_kwargs):
        try:
            await asyncio.to_thread(self.vm.kill)
        except exc.QubesException as ex:
            show_error(
                _("Error shutting down qube"),
                _(
                    "The following error occurred while attempting to kill"
                    "qube {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )


class PreferencesItem(VMActionMenuItem):
    """Preferences menu Item. When activated shows preferences dialog"""

    def __init__(self, vm, icon_cache):
        super().__init__(
            vm,
            label=_("Settings"),
            icon_cache=icon_cache,
            icon_name="preferences",
        )

    async def perform_action(self):
        # pylint: disable=consider-using-with
        await asyncio.create_subprocess_exec("qubes-vm-settings", self.vm.name)


class LogItem(ActionMenuItem):
    def __init__(self, name, path, icon_cache):
        super().__init__(
            label=name,
            icon_cache=icon_cache,
            icon_name="logs",
        )
        self.path = path

    async def perform_action(self):
        await asyncio.create_subprocess_exec("qubes-log-viewer", self.path)


class RunTerminalItem(VMActionMenuItem):
    """Run Terminal menu Item. When activated runs a terminal emulator."""

    def __init__(self, vm, icon_cache, as_root=False):
        super().__init__(
            vm,
            label=RunTerminalItem.dynamic_label(as_root),
            icon_cache=icon_cache,
            icon_name="terminal",
        )
        self.as_root = as_root

    @staticmethod
    def dynamic_label(as_root):
        if as_root:
            return _("Run Root Terminal")
        return _("Run Terminal")

    def set_as_root(self, as_root):
        self.as_root = as_root
        self.label.set_text(RunTerminalItem.dynamic_label(self.as_root))

    async def perform_action(self):
        service_args = {}
        if self.as_root:
            service_args["user"] = "root"
        try:
            await asyncio.to_thread(
                self.vm.run_service_for_stdio,
                "qubes.StartApp+qubes-run-terminal",
                **service_args,
            )
        except exc.QubesException as ex:
            show_error(
                _("Error starting terminal"),
                _(
                    "The following error occurred while attempting to "
                    "run terminal {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )


class RunDebugConsoleItem(VMActionMenuItem):
    """Run Debug Console menu Item. When activated runs a qvm-console-dispvm."""

    def __init__(self, vm, icon_cache):
        super().__init__(
            vm,
            label=_("Debug Console"),
            icon_cache=icon_cache,
            icon_name="debug",
        )
        self.visible = False
        self.connect("show", self.on_show_event)

    def on_show_event(self, widget):
        if self.visible:
            widget.show()
        else:
            widget.hide()

    async def perform_action(self):
        # pylint: disable=consider-using-with
        await asyncio.create_subprocess_exec("qvm-console-dispvm", self.vm.name)


class OpenFileManagerItem(VMActionMenuItem):
    """Attempts to open a file manager in the VM. If fails, displays an
    error message."""

    def __init__(self, vm, icon_cache):
        super().__init__(
            vm,
            label=_("Open File Manager"),
            icon_cache=icon_cache,
            icon_name="files",
        )

    async def perform_action(self):
        try:
            await asyncio.to_thread(
                self.vm.run_service_for_stdio, "qubes.StartApp+qubes-open-file-manager"
            )
        except exc.QubesException as ex:
            show_error(
                _("Error opening file manager"),
                _(
                    "The following error occurred while attempting to "
                    "open file manager {0}:\n{1}"
                ).format(self.vm.name, str(ex)),
            )


class InternalInfoItem(Gtk.MenuItem):
    """Internal info label."""

    def __init__(self, is_preload=False):
        super().__init__()
        self.label = Gtk.Label(xalign=0)
        title = "Internal qube"
        if is_preload:
            title += "\n(preloaded)"
        tooltip = (
            "Internal qubes are used by the operating system. Do not modify "
            "them or run programs in them unless you really know what you "
            "are doing."
        )
        if is_preload:
            tooltip += (
                "\n\nTo configure preloading, see Qubes Global Config and Qube "
                "Settings"
            )
        self.label.set_markup(_("<b>" + title + "</b>"))
        self.set_tooltip_text(tooltip)
        self.add(self.label)
        self.set_sensitive(False)


class StartedMenu(Gtk.Menu):
    """The sub-menu for a started domain"""

    def __init__(self, vm, app, icon_cache, shutdown_failed=False):
        super().__init__()
        self.vm = vm
        self.app = app

        self.open_file_manager = OpenFileManagerItem(self.vm, icon_cache)
        self.add(self.open_file_manager)
        self.run_terminal = RunTerminalItem(
            self.vm, icon_cache, as_root=app.shift_pressed
        )
        self.add(self.run_terminal)

        # Debug console for developers, troubleshooting, headless qubes
        self.debug_console = RunDebugConsoleItem(self.vm, icon_cache)
        self.add(self.debug_console)

        self.add(PreferencesItem(self.vm, icon_cache))
        self.add(PauseItem(self.vm, icon_cache))
        self.add(
            ShutdownItem(
                self.vm,
                icon_cache,
                force=app.shift_pressed and not shutdown_failed,
                follow_shift=not shutdown_failed,
            )
        )
        if shutdown_failed:
            self.add(ShutdownItem(self.vm, icon_cache, force=True, follow_shift=False))
            self.add(KillItem(self.vm, icon_cache))
        if self.vm.klass != "DispVM" or not self.vm.auto_cleanup:
            self.add(RestartItem(self.vm, icon_cache, force=app.shift_pressed))

        self.set_reserve_toggle_size(False)
        self.debug_console_update()
        self.show_all()
        # Keep later show_all() calls on parent menus from overriding visibility.
        # Initialize the action contents above before managing visibility here.
        self.open_file_manager.set_no_show_all(True)
        self.run_terminal.set_no_show_all(True)
        self.gui_actions_update()

    def gui_actions_update(self, *_args, **_kwargs):
        """Show GUI actions only when the qube has a usable GUI."""
        if vm_has_gui(self.vm):
            self.open_file_manager.show()
            self.run_terminal.show()
        else:
            self.open_file_manager.hide()
            self.run_terminal.hide()

    def debug_console_update(self, *_args, **_kwargs):
        # Debug console is shown only if debug property is set, no GUIVM is set
        # ... or with `expert-mode` feature per qube or per entire GUIVM.
        if (
            self.app.expert_mode
            or getattr(self.vm, "debug", False)
            or not getattr(self.vm, "guivm", None)
            or not self.vm.features.check_with_template("gui", False)
            or self.vm.features.get("expert-mode", False)
        ):
            self.debug_console.visible = True
            self.debug_console.show()
        else:
            self.debug_console.visible = False
            self.debug_console.hide()


class PausedMenu(Gtk.Menu):
    """The sub-menu for a paused domain"""

    def __init__(self, vm, icon_cache):
        super().__init__()
        self.vm = vm

        self.add(PreferencesItem(self.vm, icon_cache))
        self.add(UnpauseItem(self.vm, icon_cache))
        self.add(KillItem(self.vm, icon_cache))

        self.set_reserve_toggle_size(False)
        self.show_all()


class DebugMenu(Gtk.Menu):
    """Sub-menu providing multiple MenuItem for domain logs."""

    def __init__(self, vm, icon_cache):
        super().__init__()
        self.vm = vm

        self.add(PreferencesItem(self.vm, icon_cache))

        logs = [
            (
                _("Console Log"),
                "/var/log/xen/console/guest-" + vm.name + ".log",
            ),
            (
                _("QEMU Console Log"),
                "/var/log/xen/console/guest-" + vm.name + "-dm.log",
            ),
        ]

        for name, path in logs:
            if os.path.isfile(path):
                self.add(LogItem(name, path, icon_cache=icon_cache))

        self.add(KillItem(self.vm, icon_cache))

        self.set_reserve_toggle_size(False)
        self.show_all()


class InternalMenu(Gtk.Menu):
    """Sub-menu for Internal qubes"""

    def __init__(self, vm, icon_cache, working_correctly=True, is_preload=False):
        """
        :param vm: relevant Internal qube
        :param icon_cache: IconCache object
        :param working_correctly: if True, the VM should have a Shutdown
        option; otherwise, have a Kill option
        """
        super().__init__()
        self.vm = vm

        self.add(InternalInfoItem(is_preload=is_preload))

        logs = [
            (
                _("Console Log"),
                "/var/log/xen/console/guest-" + vm.name + ".log",
            ),
            (
                _("QEMU Console Log"),
                "/var/log/xen/console/guest-" + vm.name + "-dm.log",
            ),
        ]

        for name, path in logs:
            if os.path.isfile(path):
                self.add(LogItem(name, path, icon_cache=icon_cache))

        if working_correctly:
            self.add(ShutdownItem(self.vm, icon_cache))
        else:
            self.add(KillItem(self.vm, icon_cache))

        self.set_reserve_toggle_size(False)
        self.show_all()


class QubesManagerItem(Gtk.MenuItem):
    def __init__(self):
        super().__init__()

        # Main horizontal box
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Icon box with fixed width
        iconbox = Gtk.Image.new_from_icon_name("qubes-logo-icon", Gtk.IconSize.MENU)
        hbox.pack_start(iconbox, False, True, 6)

        # Name box
        namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(xalign=0)
        label.set_markup("<b>Open Qube Manager</b>")
        namebox.pack_start(label, False, True, 0)

        hbox.pack_start(namebox, True, True, 0)

        self.add(hbox)
        self.show_all()

        # Connect the "activate" signal to the async function
        self.connect("activate", self.on_activate)

    def on_activate(self, *_args, **_kwargs):
        asyncio.create_task(self.perform_action())

    async def perform_action(self):
        # pylint: disable=consider-using-with
        await asyncio.create_subprocess_exec("qubes-qube-manager")


# how far back the memory graph goes
MEMORY_HISTORY_SECONDS = 600


def memory_graph_ticks(low, high):
    """Round values (in MiB) for the y axis of the memory graph, covering
    *low* to *high* with at most 5 intervals"""
    if high - low < 30:
        # a flat line still gets a few MiB around it
        middle = (low + high) / 2
        low, high = max(middle - 15, 0), max(middle + 15, 30)
    magnitude = 10 ** math.floor(math.log10((high - low) / 5))
    for factor in (1, 2, 5, 10, 20, 50):
        step = int(factor * magnitude)
        first = math.floor(low / step) * step
        last = math.ceil(high / step) * step
        if (last - first) / step <= 5:
            break
    return list(range(first, last + 1, step))


class MemoryGraph(Gtk.DrawingArea):
    """Total memory assigned to and used by qubes over the last
    MEMORY_HISTORY_SECONDS, as recorded since the widget started."""

    def __init__(self):
        super().__init__()
        self.set_size_request(320, 160)
        # (time.monotonic(), assigned KiB, used KiB), oldest first
        self.samples: list[tuple[float, int, int]] = []
        self.connect("draw", self._draw)

    def add_sample(self, assigned_kb, used_kb):
        now = time.monotonic()
        if self.samples and now - self.samples[-1][0] < 1:
            # all qubes send their stats at the same time, keep one point
            self.samples[-1] = (self.samples[-1][0], assigned_kb, used_kb)
        else:
            self.samples.append((now, assigned_kb, used_kb))
        while now - self.samples[0][0] > MEMORY_HISTORY_SECONDS:
            self.samples.pop(0)
        self.queue_draw()

    def _draw(self, widget, context):
        # pylint: disable=too-many-locals
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        style = widget.get_style_context()
        # normal colors, even though the menu item is insensitive
        assigned_color = style.get_color(Gtk.StateFlags.NORMAL)
        found, used_color = style.lookup_color("theme_selected_bg_color")
        if not found:
            used_color = assigned_color

        def set_color(color, alpha=1.0):
            Gdk.cairo_set_source_rgba(
                context, Gdk.RGBA(color.red, color.green, color.blue, alpha)
            )

        if self.samples:
            values = [
                value / 1024
                for _time, assigned, used in self.samples
                for value in (assigned, used)
            ]
            ticks = memory_graph_ticks(min(values), max(values))
        else:
            ticks = []

        y_labels = [widget.create_pango_layout(f"{tick} MiB") for tick in ticks]
        x_labels = [
            widget.create_pango_layout(text)
            for text in (
                _("-{} min").format(MEMORY_HISTORY_SECONDS // 60),
                _("-{} min").format(MEMORY_HISTORY_SECONDS // 120),
                _("now"),
            )
        ]
        legend = [
            (widget.create_pango_layout(_("Assigned")), assigned_color),
            (widget.create_pango_layout(_("Used")), used_color),
        ]
        label_height = x_labels[0].get_pixel_size()[1]
        left = max((label.get_pixel_size()[0] for label in y_labels), default=0) + 6
        # the legend is above the graph
        top = label_height + 6
        right = width - x_labels[-1].get_pixel_size()[0] // 2 - 1
        bottom = height - label_height - 4

        x = left
        for label, color in legend:
            set_color(color)
            context.set_line_width(2)
            context.move_to(x, label_height / 2)
            context.line_to(x + 16, label_height / 2)
            context.stroke()
            Gtk.render_layout(style, context, x + 20, 0, label)
            x += 20 + label.get_pixel_size()[0] + 16

        context.set_line_width(1)
        set_color(assigned_color, 0.3)
        context.rectangle(left + 0.5, top + 0.5, right - left, bottom - top)
        context.stroke()

        for index, label in enumerate(x_labels):
            x = left + (right - left) * index / (len(x_labels) - 1)
            label_width = label.get_pixel_size()[0]
            Gtk.render_layout(
                style,
                context,
                min(max(x - label_width / 2, left), width - label_width),
                bottom + 4,
                label,
            )

        if not self.samples:
            return

        def to_y(value_kb):
            return bottom - (value_kb / 1024 - ticks[0]) / (ticks[-1] - ticks[0]) * (
                bottom - top
            )

        for tick, label in zip(ticks, y_labels):
            y = to_y(tick * 1024)
            set_color(assigned_color, 0.15)
            context.move_to(left, round(y) + 0.5)
            context.line_to(right, round(y) + 0.5)
            context.stroke()
            label_width, label_h = label.get_pixel_size()
            Gtk.render_layout(
                style, context, left - 6 - label_width, y - label_h / 2, label
            )

        now = time.monotonic()
        context.set_line_width(2)
        for index, color in ((1, assigned_color), (2, used_color)):
            points = [
                (
                    right - (now - sample[0]) / MEMORY_HISTORY_SECONDS * (right - left),
                    to_y(sample[index]),
                )
                for sample in self.samples
            ]
            # the latest value is the current one
            points.append((right, points[-1][1]))
            context.move_to(*points[0])
            for point in points[1:]:
                context.line_to(*point)
            set_color(color)
            context.stroke()


class MemorySummaryItem(Gtk.MenuItem):
    """Memory assigned to all running qubes, compared to the system memory,
    with a graph of the last minutes in its submenu.

    Hidden until the first stats event with ``memory_assigned_total``
    arrives."""

    def __init__(self):
        super().__init__()

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Same left offset as the icon of DomainMenuItem
        placeholder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        placeholder.set_size_request(16, 0)
        hbox.pack_start(placeholder, False, True, 6)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(4)

        name_label = Gtk.Label(xalign=0)
        name_label.set_markup(_("<b>Total memory assigned</b>"))
        name_label.set_hexpand(True)

        self.memory_label = Gtk.Label(xalign=1)

        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_min_value(0)
        self.level_bar.set_max_value(100)
        self.level_bar.set_hexpand(True)
        self.level_bar.set_valign(Gtk.Align.CENTER)

        self.percentage_label = Gtk.Label(xalign=1)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self.memory_label, 1, 0, 1, 1)
        grid.attach(self.level_bar, 0, 1, 1, 1)
        grid.attach(self.percentage_label, 1, 1, 1, 1)

        hbox.pack_start(grid, True, True, 0)
        self.add(hbox)

        self.graph = MemoryGraph()
        history_item = Gtk.MenuItem()
        history_item.add(self.graph)
        # only shows information
        history_item.set_sensitive(False)
        submenu = Gtk.Menu()
        submenu.add(history_item)
        submenu.show_all()
        self.set_submenu(submenu)

        hbox.show_all()
        # visibility is managed by update_state(), not by show_all() on menu
        self.level_bar.set_no_show_all(True)
        self.percentage_label.set_no_show_all(True)
        self.set_no_show_all(True)
        self.hide()

    def update_state(self, assigned_kb, used_kb, total_kb=None):
        """Show *assigned_kb* KiB assigned to qubes (of which they use
        *used_kb* KiB), out of *total_kb* KiB of system memory; if *total_kb*
        is not known, show only the sum."""
        assigned = int(assigned_kb / 1024)
        used = int(used_kb / 1024)
        self.graph.add_sample(assigned_kb, used_kb)
        if not total_kb:
            self.memory_label.set_markup(f"{assigned} MiB")
            self.level_bar.hide()
            self.percentage_label.hide()
            self.set_tooltip_markup(
                _(
                    "Memory assigned to running qubes: <b>{assigned} MiB</b>\n"
                    "Used by qubes (incl. swap; self-reported): <b>{used} MiB</b>"
                ).format(assigned=assigned, used=used)
            )
            self.show()
            return

        total = int(total_kb / 1024)
        unassigned = max(total - assigned, 0)
        fraction = min(assigned_kb / total_kb, 1)
        self.memory_label.set_markup(f"{assigned} / {total} MiB")
        self.level_bar.set_value(fraction * 100)
        # pylint: disable=consider-using-f-string
        self.percentage_label.set_markup("{:.1%}".format(fraction))
        self.set_tooltip_markup(
            _(
                "Memory assigned to running qubes: <b>{assigned} MiB</b>\n"
                "Used by qubes (incl. swap; self-reported): <b>{used} MiB</b>\n"
                "Not assigned to any qube: <b>{unassigned} MiB</b>\n"
                "Total system memory: <b>{total} MiB</b>"
            ).format(assigned=assigned, used=used, unassigned=unassigned, total=total)
        )
        self.level_bar.show()
        self.percentage_label.show()
        self.show()


class DomainMenuItem(Gtk.MenuItem):
    def __init__(self, vm, app, icon_cache, state=None):
        super().__init__()
        self.vm = vm
        self.app = app
        self.icon_cache = icon_cache
        self.shutdown_failed = False
        self.decorator = qui.decorators.DomainDecorator(vm)

        # Main horizontal box
        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Icon box with fixed width
        self.iconbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.iconbox.set_size_request(16, 0)
        self.set_label_icon()

        self.hbox.pack_start(self.iconbox, False, True, 6)

        # Name box
        namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.name = self.decorator.name()
        namebox.pack_start(self.name, False, True, 0)
        self.spinner = Gtk.Spinner()
        namebox.pack_start(self.spinner, False, True, 0)

        self.hbox.pack_start(namebox, True, True, 0)

        # Memory and CPU box
        mem_cpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.memory = self.decorator.memory()
        mem_cpu_box.pack_start(self.memory, False, True, 0)
        self.cpu = self.decorator.cpu()
        mem_cpu_box.pack_start(self.cpu, False, True, 0)

        self.hbox.pack_start(mem_cpu_box, False, True, 0)

        # Add hbox to the menu item
        self.add(self.hbox)

        if self.vm is None:  # if header
            self.set_reserve_indicator(True)  # align with submenu triangles
            self.cpu.update_state(header=True)
            self.memory.update_state(header=True)
            self.show_all()  # header should always be visible
        else:
            if self.vm.klass == "AdminVM":  # no submenu for AdminVM
                self.set_reserve_indicator(True)  # align with submenu triangles
            else:
                if not state:
                    self.update_state(self.vm.get_power_state())
                else:
                    self.update_state(state)

    def _set_submenu(self, state):
        if self.vm.features.get("internal", False):
            is_preload = getattr(self.vm, "is_preload", False)
            submenu = InternalMenu(
                self.vm,
                self.icon_cache,
                working_correctly=(state == "Running"),
                is_preload=is_preload,
            )
        elif state == "Running":
            submenu = StartedMenu(
                self.vm,
                self.app,
                self.icon_cache,
                shutdown_failed=self.shutdown_failed,
            )
        elif state == "Paused":
            submenu = PausedMenu(self.vm, self.icon_cache)
        else:
            submenu = DebugMenu(self.vm, self.icon_cache)
        submenu.connect("key-press-event", self.app.key_event)
        submenu.connect("key-release-event", self.app.key_event)
        # This is a workaround for a bug in Gtk which occurs when a
        # submenu is replaced while it is open.
        # see https://gitlab.gnome.org/GNOME/gtk/issues/885
        current_submenu = self.get_submenu()
        if current_submenu:
            current_submenu.grab_remove()
        self.set_submenu(submenu)

    def show_spinner(self):
        self.spinner.start()
        self.spinner.set_no_show_all(False)
        self.spinner.show()
        self.show_all()

    def hide_spinner(self):
        self.spinner.stop()
        self.spinner.set_no_show_all(True)
        self.spinner.hide()

    def update_state(self, state):
        vm_klass = getattr(self.vm, "klass", None)

        if not self.vm or vm_klass == "AdminVM":
            # it's a header or an AdminVM, no need to do anything
            return

        if not vm_klass:
            # it's a DispVM in a very fragile state; just make sure to add
            # correct submenu
            self._set_submenu(state)
            return

        # if VM is not running, hide it
        if state == "Halted":
            self.hide()
            return
        self.show_all()

        if state in ["Running", "Paused"]:
            self.hide_spinner()
        else:
            self.show_spinner()
        colormap = {
            "Paused": "grey",
            "Crashed": "red",
            "Transient": "red",
            "Starting": "red",
            "Halting": "red",
            "NA": "red",
        }
        if state in colormap:
            self.name.label.set_markup(
                f"<span color='{colormap[state]}'>{self.vm.name}</span>"
            )
        else:
            self.name.label.set_label(self.vm.name)

        self._set_submenu(state)

    def update_stats(self, memory_kb, cpu_usage):
        self.memory.update_state(int(memory_kb))
        self.cpu.update_state(int(cpu_usage))

    def set_label_icon(self):
        for child in self.iconbox.get_children():
            self.iconbox.remove(child)
        icon = self.decorator.icon()
        if icon:
            self.iconbox.pack_start(icon, False, True, 0)
            icon.show()
        else:
            placeholder = Gtk.Label()
            self.iconbox.pack_start(placeholder, False, True, 0)


class DomainTray(Gtk.Application):
    """A tray icon application listing all but halted domains. ”"""

    def __init__(self, app_name, qapp, dispatcher, stats_dispatcher):
        super().__init__()
        self.qapp = qapp
        self.dispatcher = dispatcher
        self.stats_dispatcher = stats_dispatcher

        self.widget_icon: Gtk.StatusIcon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name("qui-domains-scalable")
        self.widget_icon.connect("button-press-event", self.show_menu)
        self.widget_icon.set_tooltip_markup(
            _("<b>Qubes Domains</b>\nView and manage running domains.")
        )

        self.tray_menu = Gtk.Menu()
        self.tray_menu.set_reserve_toggle_size(False)
        self.fullscreen_window_hack = get_fullscreen_window_hack()
        self.fullscreen_window_hack.show_for_widget(self.tray_menu)
        self.tray_menu.connect("key-press-event", self.key_event)
        self.tray_menu.connect("key-release-event", self.key_event)

        self.icon_cache = IconCache()

        self.menu_items = {}

        # memory_assigned_total and memory_with_swap_used (KiB) of each
        # running qube, by name
        self.memory_assigned = {}
        self.memory_used = {}
        # system memory in KiB, fetched on first use (None if not available)
        self._system_memory_kb = None
        self._system_memory_checked = False
        self.memory_summary = MemorySummaryItem()

        self.unpause_all_action = Gio.SimpleAction.new("do-unpause-all", None)
        self.unpause_all_action.connect("activate", self.do_unpause_all)
        self.add_action(self.unpause_all_action)
        self.pause_notification_out = False

        # add refreshing tooltips with storage info
        GLib.timeout_add_seconds(120, self.refresh_tooltips)

        self.register_events()
        self.set_application_id(app_name)
        self.register()  # register Gtk Application

        # to display debug console for all qubes
        self.expert_mode = self.qapp.domains[self.qapp.local_name].features.get(
            "expert-mode", False
        )

    def register_events(self):
        self.dispatcher.add_handler("connection-established", self.refresh_all)
        self.dispatcher.add_handler("domain-pre-start", self.update_domain_item)
        self.dispatcher.add_handler("domain-start", self.update_domain_item)
        self.dispatcher.add_handler("domain-start-failed", self.update_domain_item)
        self.dispatcher.add_handler("domain-paused", self.update_domain_item)
        self.dispatcher.add_handler("domain-unpaused", self.update_domain_item)
        self.dispatcher.add_handler("domain-shutdown", self.update_domain_item)
        self.dispatcher.add_handler("domain-pre-shutdown", self.update_domain_item)
        self.dispatcher.add_handler("domain-shutdown-failed", self.update_domain_item)
        self.dispatcher.add_handler("domain-stopped", self.domain_stopped)

        self.dispatcher.add_handler("domain-add", self.add_domain_item)
        self.dispatcher.add_handler("domain-delete", self.remove_domain_item)

        self.dispatcher.add_handler("domain-pre-start", self.emit_notification)
        self.dispatcher.add_handler("domain-start", self.emit_notification)
        self.dispatcher.add_handler("domain-start-failed", self.emit_notification)
        self.dispatcher.add_handler("domain-pre-shutdown", self.emit_notification)
        self.dispatcher.add_handler("domain-shutdown", self.emit_notification)
        self.dispatcher.add_handler("domain-shutdown-failed", self.emit_notification)
        self.dispatcher.add_handler(
            "domain-preload-dispvm-used", self.emit_notification
        )

        self.dispatcher.add_handler("domain-start", self.check_pause_notify)
        self.dispatcher.add_handler("domain-paused", self.check_pause_notify)
        self.dispatcher.add_handler("domain-unpaused", self.check_pause_notify)
        self.dispatcher.add_handler("domain-shutdown", self.check_pause_notify)

        self.dispatcher.add_handler(
            "domain-feature-set:updates-available", self.feature_change
        )
        self.dispatcher.add_handler(
            "domain-feature-delete:updates-available", self.feature_change
        )
        self.dispatcher.add_handler(
            "property-set:active_template", self.property_change
        )
        self.dispatcher.add_handler(
            "property-reset:active_template", self.property_change
        )
        self.dispatcher.add_handler("property-set:template", self.property_change)
        self.dispatcher.add_handler("property-set:netvm", self.property_change)
        self.dispatcher.add_handler("property-set:label", self.property_change)

        self.dispatcher.add_handler("property-set:debug", self.debug_change)
        self.dispatcher.add_handler("property-set:guivm", self.debug_change)
        self.dispatcher.add_handler("property-reset:guivm", self.debug_change)
        self.dispatcher.add_handler("domain-feature-set:gui", self.debug_change)
        self.dispatcher.add_handler("domain-feature-delete:gui", self.debug_change)
        self.dispatcher.add_handler("domain-feature-set:expert-mode", self.debug_change)
        self.dispatcher.add_handler(
            "domain-feature-delete:expert-mode", self.debug_change
        )

        self.dispatcher.add_handler(
            "property-reset:is_preload", self.update_domain_item
        )
        self.dispatcher.add_handler(
            "domain-feature-set:internal", self.update_domain_item
        )
        self.dispatcher.add_handler(
            "domain-feature-delete:internal", self.update_domain_item
        )

        self.stats_dispatcher.add_handler("vm-stats", self.update_stats)

    def debug_change(self, vm, *_args, **_kwargs):
        if vm == self.qapp.local_name:
            self.expert_mode = self.qapp.domains[self.qapp.local_name].features.get(
                "expert-mode", False
            )
            vms = self.menu_items
        else:
            vms = {vm}
        for menu in vms:
            submenu = self.menu_items[menu].get_submenu()
            if isinstance(submenu, StartedMenu):
                submenu.debug_console_update()
                submenu.gui_actions_update()

    def show_menu(self, _unused, event):
        self.shift_pressed = False
        self.tray_menu.popup_at_pointer(event)  # None means current event

    def emit_notification(self, vm, event, **kwargs):
        if event == "domain-preload-dispvm-used":
            vm_name = kwargs["dispvm"]
        else:
            vm_name = vm.name
        notification = Gio.Notification.new(_("Qube Status: {}").format(vm_name))
        notification.set_priority(Gio.NotificationPriority.NORMAL)

        if event == "domain-start-failed":
            notification.set_body(
                _("Qube {} has failed to start: {}").format(vm.name, kwargs["reason"])
            )
            notification.set_priority(Gio.NotificationPriority.HIGH)
            notification.set_icon(Gio.ThemedIcon.new("dialog-warning"))
        elif event == "domain-pre-start":
            notification.set_body(_("Qube {} is starting.").format(vm.name))
        elif event == "domain-start":
            notification.set_body(_("Qube {} has started.").format(vm.name))
        elif event == "domain-preload-dispvm-used":
            notification.set_body(
                _("Qube {} was preloaded and is now being used.").format(
                    kwargs["dispvm"]
                )
            )
        elif event == "domain-pre-shutdown":
            notification.set_body(
                _("Qube {} is attempting to shut down.").format(vm.name)
            )
        elif event == "domain-shutdown":
            notification.set_body(_("Qube {} has shut down.").format(vm.name))
        elif event == "domain-shutdown-failed":
            notification.set_body(
                _("Qube {} failed to shut down: {}").format(vm.name, kwargs["reason"])
            )
            notification.set_priority(Gio.NotificationPriority.HIGH)
            notification.set_icon(Gio.ThemedIcon.new("dialog-warning"))
        else:
            return
        self.send_notification(None, notification)

    def emit_paused_notification(self):
        if not self.pause_notification_out:
            notification = Gio.Notification.new(_("Your qubes have been paused!"))
            notification.set_body(
                _(
                    "All your qubes are currently paused. If this was an "
                    "accident, simply click 'Unpause All' to unpause them "
                    "(except preloaded disposables). "
                    "Otherwise, you can unpause individual qubes via the "
                    "Qubes Domains tray widget."
                )
            )
            notification.set_icon(Gio.ThemedIcon.new("dialog-warning"))
            notification.add_button(_("Unpause All"), "app.do-unpause-all")
            notification.set_priority(Gio.NotificationPriority.HIGH)
            self.send_notification("vms-paused", notification)
            self.pause_notification_out = True

    def withdraw_paused_notification(self):
        if self.pause_notification_out:
            self.withdraw_notification("vms-paused")
            self.pause_notification_out = False

    def do_unpause_all(self, _vm, *_args, **_kwargs):
        for vm_name in self.menu_items:
            if vm_name == "dom0" or getattr(
                self.qapp.domains[vm_name], "is_preload", False
            ):
                continue
            try:
                self.qapp.domains[vm_name].unpause()
            except exc.QubesException:
                # we may not have permission to do that
                pass

    def check_pause_notify(self, _vm, _event, **_kwargs):
        if self.have_running_and_all_are_paused():
            self.emit_paused_notification()
        else:
            self.withdraw_paused_notification()

    def have_running_and_all_are_paused(self):
        found_paused = False
        for vm in self.qapp.domains:
            if vm.klass == "AdminVM" or getattr(vm, "is_preload", False):
                continue
            if vm.is_running() and vm.is_paused():
                # a running that is paused
                found_paused = True
            else:
                # found running that wasn't paused
                return False
        return found_paused

    def add_domain_item(self, _submitter, event, vm, **_kwargs):
        """Add a DomainMenuItem to menu; if event is None, this was fired
        manually (mot due to domain-add event, and it is assumed the menu items
        are created in alphabetical order. Otherwise, this method will
        attempt to sort menu items correctly."""
        # check if it already exists
        try:
            vm = self.qapp.domains[str(vm)]
        except KeyError:
            # the VM was not created successfully or was deleted before the
            # event was fully handled
            return
        if vm in self.menu_items:
            return
        if vm.klass == "RemoteVM":
            return

        try:
            state = vm.get_power_state()
        except exc.QubesException:
            # VM might have been already destroyed
            if vm not in self.qapp.domains:
                return
            # or we might not have permission to access its power state
            state = "NA"

        domain_item = DomainMenuItem(vm, self, self.icon_cache, state=state)
        if not event:  # menu item creation at widget start; we can assume
            # menu items are created in alphabetical order
            self.tray_menu.add(domain_item)
        else:
            position = 0
            for i in self.tray_menu:  # pylint: disable=not-an-iterable
                if not hasattr(i, "vm"):  # we reached the end
                    break
                if not i.vm:  # header should be skipper
                    position += 1
                    continue
                if i.vm.klass == "AdminVM":
                    # AdminVM(s) should be skipped
                    position += 1
                    continue
                if i.vm.name > vm.name:
                    # we reached correct alphabetical placement for the VM
                    break
                position += 1
            self.tray_menu.insert(domain_item, position)
        self.menu_items[vm] = domain_item

    def property_change(self, vm, event, *_args, **_kwargs):
        if vm not in self.menu_items:
            return
        item = self.menu_items[vm]
        if event == "property-set:netvm":
            item.name.update_tooltip(netvm_changed=True)
        elif event == "property-set:label":
            item.set_label_icon()
        elif event in [
            "property-set:active_template",
            "property-reset:active_template",
            "property-set:template",
        ]:
            item.name.update_template()

    def feature_change(self, vm, *_args, **_kwargs):
        if vm not in self.menu_items:
            return
        self.menu_items[vm].name.update_updateable()

    def refresh_tooltips(self):
        for item in self.menu_items.values():
            if item.vm and item.is_visible():
                try:
                    item.name.update_tooltip(storage_changed=True)
                except Exception:  # pylint: disable=broad-except
                    pass

    def remove_domain_item(self, _submitter, _event, vm, **_kwargs):
        self.forget_memory(vm)
        if vm not in self.menu_items:
            return
        vm_widget = self.menu_items[vm]
        self.tray_menu.remove(vm_widget)
        del self.menu_items[vm]

    def handle_domain_shutdown(self, vm):
        try:
            if getattr(vm, "klass", None) == "TemplateVM" or getattr(
                vm, "template_for_dispvms", False
            ):
                for menu_item in self.menu_items.values():
                    try:
                        if not menu_item.vm.is_running():
                            # A VM based on this template can only be
                            # outdated if the VM is currently running.
                            continue
                    except exc.QubesPropertyAccessError:
                        continue
                    template1 = getattr(menu_item.vm, "template", None)
                    template2 = getattr(template1, "template", None)
                    if vm in (template1, template2) and any(
                        vol.is_outdated() for vol in menu_item.vm.volumes.values()
                    ):
                        menu_item.name.update_outdated(True)
        except exc.QubesVMNotFoundError:
            # attribute not available anymore as VM was removed
            # in the meantime
            pass

    def update_domain_item(self, vm, event, **kwargs):
        """Update the menu item with the started menu for
        the specified vm in the tray"""
        try:
            item = self.menu_items[vm]
        except exc.QubesPropertyAccessError:
            print(_("Unexpected property access error"))  # req by @marmarek
            traceback.print_exc()
            self.remove_domain_item(vm, event, **kwargs)
            return
        except KeyError:
            self.add_domain_item(None, event, vm)
            if not vm in self.menu_items:
                # VM not added - already removed?
                return
            item = self.menu_items[vm]

        try:
            state = vm.get_power_state()
        except Exception:  # pylint: disable=broad-except
            # it's a fragile DispVM
            state = "NA"

        if state == "Halted" or event == "domain-shutdown":
            self.forget_memory(vm)

        if event == "domain-shutdown-failed":
            item.shutdown_failed = True
        elif event in ("domain-start", "domain-pre-start", "domain-shutdown"):
            item.shutdown_failed = False

        item.update_state(state)

        if event == "property-reset:is_preload":
            item.name.update_preload()

        if event == "domain-shutdown":
            self.handle_domain_shutdown(vm)
            # if the VM was shut down, it is no longer outdated
            item.name.update_outdated(False)

        if event in ("domain-start", "domain-pre-start"):
            # A newly started VM should not be outdated.
            item.name.update_outdated(False)
            item.show_all()
        if event == "domain-shutdown":
            item.hide()

    def update_stats(self, vm, _event, **kwargs):
        # memory_assigned_total is not sent by older dom0; it already includes
        # the memory of the qube's stubdomain, if any
        if "memory_assigned_total" in kwargs:
            item = self.menu_items.get(vm)
            # ignore late stats of a qube that has just shut down
            if item is None or item.get_visible():
                self.memory_assigned[str(vm)] = int(kwargs["memory_assigned_total"])
                self.memory_used[str(vm)] = int(kwargs["memory_with_swap_used"])
                self.update_memory_summary()
        if vm not in self.menu_items:
            return
        self.menu_items[vm].update_stats(kwargs["memory_kb"], kwargs["cpu_usage"])

    def domain_stopped(self, vm, _event, **_kwargs):
        # the qube is gone from Xen and qmemman gives its memory to the other
        # qubes right away, while domain-shutdown can come a second later
        self.forget_memory(vm)

    def forget_memory(self, vm):
        self.memory_used.pop(str(vm), None)
        if self.memory_assigned.pop(str(vm), None) is not None:
            self.update_memory_summary()

    @property
    def system_memory_kb(self):
        """Total system memory in KiB, or None if not available (older
        dom0 or no permission)"""
        if not self._system_memory_checked:
            self._system_memory_checked = True
            try:
                # global maxmem is in MiB
                maxmem = int(self.qapp.maxmem)
            except (exc.QubesException, AttributeError, TypeError, ValueError):
                maxmem = 0
            self._system_memory_kb = maxmem * 1024 if maxmem > 0 else None
        return self._system_memory_kb

    def update_memory_summary(self):
        if not self.memory_assigned:
            self.memory_summary.hide()
            return
        self.memory_summary.update_state(
            sum(self.memory_assigned.values()),
            sum(self.memory_used.values()),
            self.system_memory_kb,
        )

    def initialize_menu(self):
        self.tray_menu.add(DomainMenuItem(None, self, self.icon_cache))

        # Add AdminVMS
        for vm in sorted([vm for vm in self.qapp.domains if vm.klass == "AdminVM"]):
            self.add_domain_item(None, None, vm)

        # and the rest of them
        for vm in sorted([vm for vm in self.qapp.domains if vm.klass != "AdminVM"]):
            self.add_domain_item(None, None, vm)

        for item in self.menu_items.values():
            try:
                if item.vm and item.vm.is_running():
                    item.name.update_tooltip(storage_changed=True)
                    item.show_all()
                else:
                    item.hide()
            except exc.QubesPropertyAccessError:
                item.hide()

        # Memory summary, shown once stats are received
        self.tray_menu.add(self.memory_summary)

        # Separator
        separator = Gtk.SeparatorMenuItem()
        separator.show_all()
        self.tray_menu.add(separator)

        # Qube Manager entry
        self.tray_menu.add(QubesManagerItem())

        self.connect("shutdown", self._disconnect_signals)

    def refresh_all(self, _subject, _event, **_kwargs):
        items_to_delete = []
        for vm in self.menu_items:
            if vm not in self.qapp.domains:
                items_to_delete.append(vm)
        for vm in items_to_delete:
            self.remove_domain_item(None, None, vm)
        for name in list(self.memory_assigned):
            if name not in self.qapp.domains:
                self.forget_memory(name)
        for vm in self.qapp.domains:
            self.update_domain_item(vm, "")

    def run(self):  # pylint: disable=arguments-differ
        self.initialize_menu()

    def _disconnect_signals(self, _event):
        self.dispatcher.remove_handler("connection-established", self.refresh_all)
        self.dispatcher.remove_handler("domain-pre-start", self.update_domain_item)
        self.dispatcher.remove_handler("domain-start", self.update_domain_item)
        self.dispatcher.remove_handler("domain-start-failed", self.update_domain_item)
        self.dispatcher.remove_handler("domain-paused", self.update_domain_item)
        self.dispatcher.remove_handler("domain-unpaused", self.update_domain_item)
        self.dispatcher.remove_handler("domain-shutdown", self.update_domain_item)
        self.dispatcher.remove_handler("domain-stopped", self.domain_stopped)
        self.dispatcher.remove_handler("domain-pre-shutdown", self.update_domain_item)
        self.dispatcher.remove_handler(
            "domain-shutdown-failed", self.update_domain_item
        )

        self.dispatcher.remove_handler("domain-add", self.add_domain_item)
        self.dispatcher.remove_handler("domain-delete", self.remove_domain_item)

        self.dispatcher.remove_handler("domain-pre-start", self.emit_notification)
        self.dispatcher.remove_handler("domain-start", self.emit_notification)
        self.dispatcher.remove_handler("domain-start-failed", self.emit_notification)
        self.dispatcher.remove_handler("domain-pre-shutdown", self.emit_notification)
        self.dispatcher.remove_handler("domain-shutdown", self.emit_notification)
        self.dispatcher.remove_handler("domain-shutdown-failed", self.emit_notification)
        self.dispatcher.remove_handler(
            "domain-preload-dispvm-used", self.emit_notification
        )

        self.dispatcher.remove_handler("domain-start", self.check_pause_notify)
        self.dispatcher.remove_handler("domain-paused", self.check_pause_notify)
        self.dispatcher.remove_handler("domain-unpaused", self.check_pause_notify)
        self.dispatcher.remove_handler("domain-shutdown", self.check_pause_notify)

        self.dispatcher.remove_handler(
            "domain-feature-set:updates-available", self.feature_change
        )
        self.dispatcher.remove_handler(
            "domain-feature-delete:updates-available", self.feature_change
        )
        self.dispatcher.remove_handler(
            "property-set:active_template", self.property_change
        )
        self.dispatcher.remove_handler(
            "property-reset:active_template", self.property_change
        )
        self.dispatcher.remove_handler("property-set:template", self.property_change)
        self.dispatcher.remove_handler("property-set:netvm", self.property_change)
        self.dispatcher.remove_handler("property-set:label", self.property_change)

        self.dispatcher.remove_handler("property-set:debug", self.debug_change)
        self.dispatcher.remove_handler("property-set:guivm", self.debug_change)
        self.dispatcher.remove_handler("property-reset:guivm", self.debug_change)
        self.dispatcher.remove_handler("domain-feature-set:gui", self.debug_change)
        self.dispatcher.remove_handler("domain-feature-delete:gui", self.debug_change)
        self.dispatcher.remove_handler(
            "domain-feature-set:expert-mode", self.debug_change
        )
        self.dispatcher.remove_handler(
            "domain-feature-delete:expert-mode", self.debug_change
        )

        self.dispatcher.remove_handler(
            "domain-feature-set:internal", self.update_domain_item
        )
        self.dispatcher.remove_handler(
            "domain-feature-delete:internal", self.update_domain_item
        )

        self.stats_dispatcher.remove_handler("vm-stats", self.update_stats)

    @property
    def shift_pressed(self):
        try:
            return self._shift_pressed
        except AttributeError:
            self._shift_pressed = False
            return self.shift_pressed

    @shift_pressed.setter
    def shift_pressed(self, shift_pressed):
        if shift_pressed == self.shift_pressed:
            return

        self._shift_pressed = shift_pressed
        for item in self.menu_items.values():
            if item.vm:
                submenu = item.get_submenu()
                if submenu is None:
                    continue

                def do_emit(child):
                    if isinstance(child, RunTerminalItem):
                        child.set_as_root(shift_pressed)
                    if isinstance(child, (RestartItem, ShutdownItem)):
                        child.set_force(shift_pressed)

                submenu.foreach(do_emit)

    def key_event(self, _unused, event):
        if event.keyval in [Gdk.KEY_Shift_L, Gdk.KEY_Shift_R]:
            if event.type == Gdk.EventType.KEY_PRESS:
                self.shift_pressed = True
            elif event.type == Gdk.EventType.KEY_RELEASE:
                self.shift_pressed = False


def main():
    """main function"""
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    stats_dispatcher = qubesadmin.events.EventsDispatcher(
        qapp, api_method="admin.vm.Stats"
    )
    app = DomainTray("org.qubes.qui.tray.Domains", qapp, dispatcher, stats_dispatcher)
    app.run()

    loop = asyncio.get_event_loop()
    tasks = [
        asyncio.ensure_future(dispatcher.listen_for_events()),
        asyncio.ensure_future(stats_dispatcher.listen_for_events()),
    ]

    return qui.utils.run_asyncio_and_show_errors(loop, tasks, "Qubes Domains Widget")


if __name__ == "__main__":
    sys.exit(main())
