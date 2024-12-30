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

# pylint: disable=import-error
"""Global Qubes Config tool."""
import sys
from typing import Dict, Optional, List, Union, Any
from html import escape
import importlib.resources
import logging

import qubesadmin
import qubesadmin.events
import qubesadmin.exc
import qubesadmin.vm
from ..widgets.gtk_utils import show_error, show_dialog_with_icon, load_theme
from ..widgets.gtk_widgets import ProgressBarDialog, ViewportHandler
from ..widgets.utils import open_url_in_disposable
from .page_handler import PageHandler
from .policy_handler import PolicyHandler, VMSubsetPolicyHandler
from .policy_rules import (
    RuleSimple,
    RuleSimpleAskIsAllow,
    RuleTargeted,
    SimpleVerbDescription,
    RuleSimpleNoAllow,
)
from .policy_manager import PolicyManager
from .updates_handler import UpdatesHandler
from .usb_devices import DevicesHandler
from .basics_handler import BasicSettingsHandler, FeatureHandler
from .policy_exceptions_handler import DispvmExceptionHandler
from .thisdevice_handler import ThisDeviceHandler

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GObject, Gio

logger = logging.getLogger("qubes-global-config")

import gettext

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

# in order to add more places as referencable locations, you need to add
# a focusable widget to the UI and then add its name here
LOCATIONS = [
    "default_qubes",
    "window_management",
    "memory_balancing",
    "linux_kernel",
    "usb_input",
    "u2f",
    "dom0_updates",
    "check_for_updates",
    "update_proxy",
    "template_repositories",
    "clipboard_shortcut",
    "clipboard_policy",
    "filecopy_policy",
    "open_in_vm",
]


class ClipboardHandler(PageHandler):
    """Handler for Clipboard policy. Adds a couple of comboboxes to a
    normal policy handler."""

    COPY_FEATURE = "gui-default-secure-copy-sequence"
    PASTE_FEATURE = "gui-default-secure-paste-sequence"

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
        policy_manager: PolicyManager,
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager
        self.vm = self.qapp.domains[self.qapp.local_name]

        self.copy_combo: Gtk.ComboBoxText = gtk_builder.get_object(
            "clipboard_copy_combo"
        )
        self.paste_combo: Gtk.ComboBoxText = gtk_builder.get_object(
            "clipboard_paste_combo"
        )

        self.handlers: List[Union[PolicyHandler, FeatureHandler]] = [
            PolicyHandler(
                qapp=self.qapp,
                gtk_builder=gtk_builder,
                policy_manager=policy_manager,
                prefix="clipboard",
                service_name="qubes.ClipboardPaste",
                policy_file_name="50-config-clipboard",
                default_policy="""qubes.ClipboardPaste * @adminvm @anyvm ask\n
qubes.ClipboardPaste * @anyvm @anyvm ask\n""",
                verb_description=SimpleVerbDescription(
                    {
                        "ask": _("be allowed to paste\n into clipboard of"),
                        "deny": _("be allowed to paste\n into clipboard of"),
                    }
                ),
                rule_class=RuleSimpleAskIsAllow,
                include_admin_vm=True,
            ),
            FeatureHandler(
                trait_holder=self.vm,
                trait_name=self.COPY_FEATURE,
                widget=self.copy_combo,
                options={
                    _("default (Ctrl+Shift+C)"): None,
                    _("Ctrl+Shift+C"): "Ctrl-Shift-c",
                    _("Ctrl+Win+C"): "Ctrl-Mod4-c",
                    _("Win+C"): "Mod4-c",
                },
                readable_name=_("Global Clipboard copy shortcut"),
            ),
            FeatureHandler(
                trait_holder=self.vm,
                trait_name=self.PASTE_FEATURE,
                widget=self.paste_combo,
                options={
                    _("default (Ctrl+Shift+V)"): None,
                    _("Ctrl+Shift+V"): "Ctrl-Shift-V",
                    _("Ctrl+Win+V"): "Ctrl-Mod4-v",
                    _("Ctrl+Insert"): "Ctrl-Ins",
                    _("Win+V"): "Mod4-v",
                },
                readable_name=_("Global Clipboard paste shortcut"),
            ),
        ]

    def reset(self):
        for handler in self.handlers:
            handler.reset()

    def save(self):
        for handler in self.handlers:
            handler.save()

    def get_unsaved(self) -> str:
        unsaved = []
        for handler in self.handlers:
            unsaved_changes = handler.get_unsaved()
            if unsaved_changes:
                unsaved.append(unsaved_changes)
        return "\n".join(unsaved)


class FileAccessHandler(PageHandler):
    """Handler for FileAccess page. Requires separate handler because
    it combines two policies in itself."""

    def __init__(
        self,
        qapp: qubesadmin.Qubes,
        gtk_builder: Gtk.Builder,
        policy_manager: PolicyManager,
    ):
        self.qapp = qapp
        self.policy_manager = policy_manager

        self.filecopy_handler = PolicyHandler(
            qapp=self.qapp,
            gtk_builder=gtk_builder,
            prefix="filecopy",
            policy_manager=self.policy_manager,
            default_policy="""qubes.Filecopy * @anyvm @adminvm deny\n
qubes.Filecopy * @anyvm @anyvm ask""",
            service_name="qubes.Filecopy",
            policy_file_name="50-config-filecopy",
            verb_description=SimpleVerbDescription(
                {
                    "ask": _("to be allowed to copy files to"),
                    "allow": _("allow files to be copied to"),
                    "deny": _("be allowed to copy files to"),
                }
            ),
            rule_class=RuleSimple,
        )

        self.openinvm_handler = DispvmExceptionHandler(
            gtk_builder=gtk_builder,
            qapp=self.qapp,
            service_name="qubes.OpenInVM",
            policy_file_name="50-config-openinvm",
            prefix="openinvm",
            policy_manager=self.policy_manager,
        )

    def reset(self):
        self.filecopy_handler.reset()
        self.openinvm_handler.reset()

    def save(self):
        self.filecopy_handler.save()
        self.openinvm_handler.save()

    def get_unsaved(self) -> str:
        unsaved = []
        for handler in [self.filecopy_handler, self.openinvm_handler]:
            unsaved_changes = handler.get_unsaved()
            if unsaved_changes:
                unsaved.append(unsaved_changes)
        return "\n".join(unsaved)


class GlobalConfig(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """

    def __init__(self, qapp: qubesadmin.Qubes, policy_manager: PolicyManager):
        """
        :param qapp: qubesadmin.Qubes object
        :param policy_manager: PolicyManager object
        """
        super().__init__(
            application_id="org.qubesos.globalconfig",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.qapp: qubesadmin.Qubes = qapp
        self.policy_manager = policy_manager

        self.add_main_option(
            "open-at",
            ord("o"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING,
            "Open config tool at the provided location.",
            "page_name#location",
        )

        self.open_at: Optional[str] = None

        self.progress_bar_dialog = ProgressBarDialog(
            self, _("Loading system settings...")
        )
        self.handlers: Dict[str, PageHandler] = {}

    def do_command_line(self, command_line):
        """
        Handle CLI arguments. This method overrides default do_command_line
        from Gtk.Application (and due to pygtk being dynamically generated
        pylint is confused about its arguments).
        """
        # pylint: disable=arguments-differ
        Gtk.Application.do_command_line(self, command_line)
        options = command_line.get_options_dict()
        options = options.end().unpack()
        self.parse_options(options)
        self.activate()
        return 0

    def parse_options(self, options: Dict[str, Any]):
        """Parse command-line options."""
        if "open-at" in options:
            self.open_at = options["open-at"]
        else:
            self.open_at = None

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
        # resize to screen size
        if (
            self.main_window.get_allocated_width()
            > self.main_window.get_screen().get_width()
        ):
            width = int(self.main_window.get_screen().get_width() * 0.9)
        else:
            # try to have at least 1100 pixels
            width = min(
                int(self.main_window.get_screen().get_width() * 0.9), 1100
            )
        if (
            self.main_window.get_allocated_height()
            > self.main_window.get_screen().get_height() * 0.9
        ):
            height = int(self.main_window.get_screen().get_height() * 0.9)
        else:
            height = self.main_window.get_allocated_height()
        self.main_window.resize(width, height)

        # open at specified location
        if self.open_at:
            self.scroll_to_location(self.open_at)

        for widget_name in LOCATIONS:
            widget = self.builder.get_object(widget_name)
            widget.set_visible(False)

        self.hold()

    def scroll_to_location(self, location_string):
        """
        Scroll to provided location. Location should be provided as
        page[#location]. Currently supported pages and locations can be found
        in the README.
        """
        if "#" in location_string:
            page, location = location_string.split("#")
        else:
            page, location = location_string, None

        for i in range(self.main_notebook.get_n_pages()):
            if self.main_notebook.get_nth_page(i).get_name() == page:
                self.main_notebook.set_current_page(i)
                break
        else:
            print("Page not found: ", page, file=sys.stderr)
            return

        if location in LOCATIONS:
            widget: Gtk.Widget = self.builder.get_object(location)
            # hopefully it has some children
            widget.grab_focus()
        elif location:
            print("Location not found: ", location, file=sys.stderr)

    @staticmethod
    def register_signals():
        """Register necessary Gtk signals"""
        GObject.signal_new(
            "rules-changed",
            Gtk.ListBox,
            GObject.SignalFlags.RUN_LAST,
            GObject.TYPE_PYOBJECT,
            (GObject.TYPE_PYOBJECT,),
        )

        # signal that informs other pages that a given page has been changed
        GObject.signal_new(
            "page-changed",
            Gtk.Window,
            GObject.SignalFlags.RUN_LAST,
            GObject.TYPE_PYOBJECT,
            (GObject.TYPE_STRING,),
        )

        GObject.signal_new(
            "child-removed",
            Gtk.FlowBox,
            GObject.SignalFlags.RUN_LAST,
            GObject.TYPE_PYOBJECT,
            (GObject.TYPE_PYOBJECT,),
        )

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
        """
        The function that performs actual widget realization and setup.
        """
        self.builder = Gtk.Builder()
        glade_ref = (
            importlib.resources.files("qubes_config") / "global_config.glade"
        )
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.main_window: Gtk.Window = self.builder.get_object("main_window")
        self.main_notebook: Gtk.Notebook = self.builder.get_object(
            "main_notebook"
        )

        load_theme(
            widget=self.main_window,
            package_name="qubes_config",
            light_file_name="qubes-global-config-light.css",
            dark_file_name="qubes-global-config-dark.css",
        )

        self.progress_bar_dialog.show_all()
        self.progress_bar_dialog.update_progress(0)

        self.apply_button: Gtk.Button = self.builder.get_object("apply_button")
        self.cancel_button: Gtk.Button = self.builder.get_object(
            "cancel_button"
        )
        self.ok_button: Gtk.Button = self.builder.get_object("ok_button")

        self.apply_button.connect("clicked", self._apply)
        self.cancel_button.connect("clicked", self._quit)
        self.ok_button.connect("clicked", self._ok)

        self.main_window.connect("delete-event", self._ask_to_quit)

        page_progress = 1 / self.main_notebook.get_n_pages()

        # match page by widget name to handler
        self.handlers["basics"] = BasicSettingsHandler(self.builder, self.qapp)
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["usb"] = DevicesHandler(
            self.qapp, self.policy_manager, self.builder
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["updates"] = UpdatesHandler(
            qapp=self.qapp,
            policy_manager=self.policy_manager,
            gtk_builder=self.builder,
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["splitgpg"] = VMSubsetPolicyHandler(
            qapp=self.qapp,
            gtk_builder=self.builder,
            policy_manager=self.policy_manager,
            prefix="splitgpg",
            service_name="qubes.Gpg",
            policy_file_name="50-config-splitgpg",
            default_policy="",
            main_rule_class=RuleSimpleNoAllow,
            main_verb_description=SimpleVerbDescription(
                {
                    "ask": _("ask to access GPG\nkeys from"),
                    "deny": _("access GPG\nkeys from"),
                }
            ),
            exception_rule_class=RuleTargeted,
            exception_verb_description=SimpleVerbDescription(
                {
                    "allow": _("access GPG\nkeys from"),
                    "ask": _("to access GPG\nkeys from"),
                    "deny": _("access GPG\nkeys from"),
                }
            ),
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["clipboard"] = ClipboardHandler(
            qapp=self.qapp,
            gtk_builder=self.builder,
            policy_manager=self.policy_manager,
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["file"] = FileAccessHandler(
            qapp=self.qapp,
            gtk_builder=self.builder,
            policy_manager=self.policy_manager,
        )
        self.progress_bar_dialog.update_progress(page_progress)
        self.handlers["url"] = DispvmExceptionHandler(
            gtk_builder=self.builder,
            qapp=self.qapp,
            service_name="qubes.OpenURL",
            policy_file_name="50-config-openurl",
            prefix="url",
            policy_manager=self.policy_manager,
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.handlers["thisdevice"] = ThisDeviceHandler(
            self.qapp, self.builder, self.policy_manager
        )
        self.progress_bar_dialog.update_progress(page_progress)

        self.main_notebook.connect("switch-page", self._page_switched)

        self._handle_urls()

        self.progress_bar_dialog.update_progress(1)
        self.progress_bar_dialog.hide()
        self.progress_bar_dialog.destroy()

        self.viewport_handler = ViewportHandler(
            self.main_window,
            [
                self.builder.get_object("basics_scrolled_window"),
                self.builder.get_object("usb_scrolled_window"),
                self.builder.get_object("updates_scrolled_window"),
                self.builder.get_object("splitgpg_scrolled_window"),
                self.builder.get_object("clipboard_scrolled_window"),
                self.builder.get_object("file_scrolled_window"),
                self.builder.get_object("url_scrolled_window"),
                self.builder.get_object("thisdevice_scrolled_window"),
            ],
        )

        self.progress_bar_dialog.update_progress(1)
        self.progress_bar_dialog.hide()
        self.progress_bar_dialog.destroy()

    def _handle_urls(self):
        url_label_ids = [
            "basics_info",
            "u2fproxy_info",
            "splitgpg_info2",
            "copymove_info",
            "openinvm_info",
            "url_info",
            "thisdevice_certified_yes_info",
            "thisdevice_security_info",
        ]
        for url_label_id in url_label_ids:
            label: Gtk.Label = self.builder.get_object(url_label_id)
            label.connect("activate-link", self._activate_link)

    def _activate_link(self, _widget, url):
        open_url_in_disposable(url, self.qapp)
        return True

    def get_current_page(self) -> Optional[PageHandler]:
        """Get currently visible page."""
        page_num = self.main_notebook.get_current_page()
        return self.handlers.get(
            self.main_notebook.get_nth_page(page_num).get_name(), None
        )

    def save_page(self, page: PageHandler) -> bool:
        """Save provided page and emit any necessary signals;
        return True if successful, False otherwise"""
        # pylint: disable=protected-access
        # need to invalidate cache before and after saving to avoid
        # stale cache

        self.qapp._invalidate_cache_all()
        try:
            page.save()
            for name, handler in self.handlers.items():
                if handler == page:
                    self.main_window.emit("page-changed", name)
                    break
            self.qapp._invalidate_cache_all()
            page.reset()
        except Exception as ex:
            show_error(
                self.main_window,
                _("Could not save changes"),
                _("The following error occurred: ") + escape(str(ex)),
            )
            return False
        return True

    def verify_changes(self) -> bool:
        """Verify the current state of the page. Return True if page can
        be abandoned, False if there are unsaved changes remaining."""
        page = self.get_current_page()
        if page:
            unsaved = page.get_unsaved()
            if unsaved != "":
                response = self._ask_unsaved(unsaved)
                if response == Gtk.ResponseType.YES:
                    return self.save_page(page)
                if response == Gtk.ResponseType.NO:
                    page.reset()
                    return True
                return False
        return True

    def _page_switched(self, *_args):
        old_page_num = self.main_notebook.get_current_page()
        allow_switch = self.verify_changes()
        if not allow_switch:
            GLib.timeout_add(
                1, lambda: self.main_notebook.set_current_page(old_page_num)
            )

    def _ask_unsaved(self, description: str) -> Gtk.ResponseType:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        label_1 = Gtk.Label()
        label_1.set_markup(
            _("The following <b>unsaved changes</b> " "were found:")
        )
        label_1.set_xalign(0)
        label_2 = Gtk.Label()
        label_2.set_text(
            "\n".join([f"- {row}" for row in description.split("\n")])
        )
        label_2.set_margin_start(20)
        label_2.set_xalign(0)
        label_3 = Gtk.Label()
        label_3.set_text(_("Do you want to save changes?"))
        label_3.set_xalign(0)
        box.pack_start(label_1, False, False, 10)
        box.pack_start(label_2, False, False, 10)
        box.pack_start(label_3, False, False, 10)

        response = show_dialog_with_icon(
            parent=self.main_window,
            title=_("Unsaved changes"),
            text=box,
            buttons={
                _("_Save changes"): Gtk.ResponseType.YES,
                _("_Discard changes"): Gtk.ResponseType.NO,
                _("_Cancel"): Gtk.ResponseType.CANCEL,
            },
            icon_name="qubes-ask",
        )

        return response

    def _apply(self, _widget=None):
        page = self.get_current_page()
        if page:
            self.save_page(page)

    def _reset(self, _widget=None):
        page = self.get_current_page()
        if page:
            page.reset()

    def _quit(self, _widget=None):
        # Hide the main Window
        self.main_window.hide()
        while Gtk.events_pending():
            Gtk.main_iteration()
        # Then wait for disposable helper threads to finish
        self.quit()

    def _ok(self, widget):
        self._apply(widget)
        self._quit(widget)

    def _ask_to_quit(self, *_args):
        can_quit = self.verify_changes()
        if not can_quit:
            return True
        self.main_window.hide()
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.quit()
        return False


def main():
    """
    Start the app
    """
    qapp = qubesadmin.Qubes()
    qapp.cache_enabled = True
    policy_manager = PolicyManager()
    app = GlobalConfig(qapp, policy_manager)
    app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
