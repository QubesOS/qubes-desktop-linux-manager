# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023 Marta Marczykowska-Górecka
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
import html
import subprocess
import sys
import re
from typing import Callable, Optional, Dict, Tuple

import gi
import importlib.resources

import qubesadmin
from qrexec.policy.admin_client import PolicyClient
from qrexec.policy.parser import StringPolicy
from qrexec.exc import PolicySyntaxError

from qubes_config.widgets.gtk_utils import load_theme, show_error, \
    ask_question, is_theme_light
from qubes_config.widgets.utils import open_url_in_disposable

gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '4')
from gi.repository import Gtk, GtkSource, Gio, Gdk


HEADER_NORMAL = ' service_name\targument\tsource_qube' \
                '\ttarget_qube\taction [parameter=value]    '

class FileListBoxRow(Gtk.ListBoxRow):
    def __init__(self, filename):
        super().__init__()
        label = Gtk.Label(xalign=0)
        label.set_text(filename)
        self.add(label)
        self.show_all()
        self.filename = filename

class OpenDialogHandler:
    def __init__(self, builder: Gtk.Builder,
                 policy_client: 'PolicyClientWrapper',
                 triggered_func: Callable):
        self.policy_client = policy_client
        self.triggered_func = triggered_func

        self.dialog_window: Gtk.Dialog = builder.get_object('open_dialog')
        self.file_list: Gtk.ListBox = builder.get_object('open_policy_list')
        self.ok_button: Gtk.Button = builder.get_object('open_button_ok')
        self.cancel_button: Gtk.Button = \
            builder.get_object('open_button_cancel')

        self.file_list.connect('row-activated', self._ok)

        # populate dialog
        for file in self.policy_client.policy_list():
            self.file_list.add(FileListBoxRow(file))

        self.file_list.show_all()
        self.dialog_window.set_modal(True)
        self.ok_button.connect('clicked', self._ok)
        self.ok_button.set_sensitive(False)
        self.cancel_button.connect('clicked', self._cancel)
        self.file_list.connect('row-selected', self._selection_changed)
        self.dialog_window.connect('hide', self._on_hide)

    def _selection_changed(self, *_args):
        if self.get_selected_file():
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)

    def get_selected_file(self):
        if self.file_list.get_selected_row():
            return self.file_list.get_selected_row().filename
        return None

    def _ok(self, *_args):
        self.triggered_func(self.get_selected_file())
        self.dialog_window.hide()

    def _cancel(self, *_args):
        self.triggered_func(None)
        self.dialog_window.hide()

    def show_dialog(self):
        self.dialog_window.show_all()

    def _on_hide(self, *_args):
        self.file_list.select_row(None)


class PolicyClientWrapper:
    """
    wrapper for policy client that handles files with include/ prefix
    transparently
    """
    INCLUDE_PREFIX = 'include/'
    def __init__(self, policy_client: PolicyClient):
        self.policy_client = policy_client

    def policy_list(self):
        """List all policy files, prefacing those from include directory
        with include/"""
        file_list = self.policy_client.policy_list()
        file_list.extend(['include/' + name for name in
                          self.policy_client.policy_include_list()])
        return file_list

    def policy_get(self, name: str) -> Tuple[str, str]:
        """Get provided policy file, return contents and token."""
        if name.startswith(self.INCLUDE_PREFIX):
            name = name[len(self.INCLUDE_PREFIX):]
            return self.policy_client.policy_include_get(name)
        return self.policy_client.policy_get(name)

    def policy_replace(self, name: str, content: str, token="any"):
        """Replace provided policy file."""
        if name.startswith(self.INCLUDE_PREFIX):
            name = name[len(self.INCLUDE_PREFIX):]
            self.policy_client.policy_include_replace(name, content, token)
            return
        self.policy_client.policy_replace(name, content, token)


class PolicyEditor(Gtk.Application):
    """
    Main Gtk.Application for new qube widget.
    """
    def __init__(self, filename: str, policy_client: PolicyClient):
        super().__init__(application_id='org.qubesos.policyeditor')
        self.token: Optional[str] = None
        self.policy_client = PolicyClientWrapper(policy_client)
        self.filename = filename
        self.window_title = 'Qubes OS Policy Editor'
        self.action_items: Dict[str, Gio.SimpleAction] = {}
        self.accel_group = Gtk.AccelGroup()

    def do_activate(self, *args, **kwargs):
        """
        Method called whenever this program is run; it executes actual setup
        only at true first start, in other cases just presenting the main window
        to user.
        """
        self.perform_setup()
        assert self.main_window
        self.main_window.show()
        self.hold()

    def perform_setup(self):
        # pylint: disable=attribute-defined-outside-init
        """
        The function that performs actual widget realization and setup.
        """
        self.clipboard: Gtk.Clipboard = \
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        self.builder = Gtk.Builder()

        glade_ref = (importlib.resources.files('qubes_config') /
                      'policy_editor.glade')
        with importlib.resources.as_file(glade_ref) as path:
            self.builder.add_from_file(str(path))

        self.file_select_handler = OpenDialogHandler(self.builder,
                                                     self.policy_client,
                                                     self.open_policy_file)

        self.main_window : Gtk.ApplicationWindow = \
            self.builder.get_object('main_window')

        # Reserving 3 pixels for window border on all sides (most themes use 2)
        # Reserving 32x2 pixels for taskbar (default on top) and Window title.
        # Setting minimum supported size
        self.main_window.set_size_request(1024 - 3*2, 768 - 3*2 - 32*2)
        width = min(1920, self.main_window.get_screen().get_width())
        height= min(1280, self.main_window.get_screen().get_height())
        self.main_window.set_default_size(width - 3*2, height - 3*2 - 32*2)
        # ToDo: Considering maximizing by default as it packs too much info.
        # self.main_window.maximize()

        # setup source and help
        header_box: Gtk.Box = self.builder.get_object('header_box')
        self.header_view = GtkSource.View()
        self.header_buffer: GtkSource.Buffer = self.header_view.get_buffer()
        header_box.pack_start(self.header_view, True, True, 0)
        header_box.show_all()
        self.header_buffer.set_text(HEADER_NORMAL)
        self.header_view.set_show_line_numbers(True)
        self.header_view.set_monospace(True)
        self.header_view.set_editable(False)

        self.source_viewport: Gtk.Viewport = \
            self.builder.get_object('source_viewport')

        self.source_view = GtkSource.View()
        self.source_buffer: GtkSource.Buffer = self.source_view.get_buffer()
        self.source_view.show()
        self.source_view.set_hexpand(True)
        self.source_viewport.add(self.source_view)

        self.help_window: Gtk.ScrolledWindow = \
            self.builder.get_object('help_window')
        self.about_window: Gtk.AboutDialog = \
            self.builder.get_object('about_window')
        self.about_window.connect('response',
                                  lambda *_args: self.about_window.hide())
        self.about_window.connect('activate-link',
                                  self._open_docs)

        self.error_info: Gtk.Label = self.builder.get_object('error_info')

        self.menu_bar: Gtk.MenuBar = self.builder.get_object('menubar')

        self.main_window.connect('delete-event', self._ask_to_quit)

        self.setup_actions()
        self.setup_menu()

        load_theme(widget=self.main_window, package_name='qubes_config',
                   light_file_name='qubes-policy-editor-light.css',
                   dark_file_name='qubes-policy-editor-dark.css')

        self.setup_source()
        help_text = importlib.resources.files(
            'qubes_config').joinpath(
            'policy_editor/policy_help.txt').read_text()
        self.builder.get_object("help_label").set_markup(help_text)

        self.open_policy_file(self.filename)

    @staticmethod
    def _open_docs(_widget, url):
        qapp = qubesadmin.Qubes()
        open_url_in_disposable(url, qapp)
        return True

    def setup_actions(self):
        self.main_window.add_accel_group(self.accel_group)
        actions = {
            "quit": self._ask_to_quit,
            "save": self._save,
            "new": self._new,
            "open": self._open,
            "redo": self._redo,
            "undo": self._undo,
            "copy": self._copy,
            "paste": self._paste,
            "reset": self._reset,
            "about": self._about,
            "help": self._toggle_help,
            "save_exit": self._save_exit}

        for name, func in actions.items():
            action: Gio.SimpleAction = Gio.SimpleAction.new(name, None)
            action.connect("activate", func)
            self.main_window.add_action(action)
            self.action_items[name] = action

    def setup_menu(self):
        # File
        file_menu = Gtk.Menu()
        file_item = self._get_menu_item("_File")
        file_item.set_submenu(file_menu)
        file_menu.add(self._get_menu_item_with_ac(
            "_New", "win.new", Gdk.KEY_n))
        file_menu.add(self._get_menu_item_with_ac(
            "_Open", "win.open", Gdk.KEY_o))
        file_menu.add(self._get_menu_item_with_ac(
            "_Save", "win.save", Gdk.KEY_s))
        file_menu.add(self._get_menu_item_with_ac(
            "_Quit", "win.quit", Gdk.KEY_q))
        self.menu_bar.add(file_item)

        # Edit
        edit_menu = Gtk.Menu()
        edit_item = self._get_menu_item("_Edit")
        edit_item.set_submenu(edit_menu)
        edit_menu.add(self._get_menu_item_with_ac(
            "_Redo", "win.redo", Gdk.KEY_y))
        edit_menu.add(self._get_menu_item_with_ac(
            "_Undo", "win.undo", Gdk.KEY_z))
        edit_menu.add(self._get_menu_item_with_ac(
            "_Copy", "win.copy", Gdk.KEY_c))
        edit_menu.add(self._get_menu_item_with_ac(
            "_Paste", "win.paste", Gdk.KEY_v))
        edit_menu.add(self._get_menu_item_with_ac(
            "Re_set", "win.reset", None))
        self.menu_bar.add(edit_item)

        # About
        help_menu = Gtk.Menu()
        help_item = self._get_menu_item("_Help")
        help_item.set_submenu(help_menu)
        help_menu.add(self._get_menu_item_with_ac(
            "_Show/Hide Help", "win.help", Gdk.KEY_h))
        help_menu.add(self._get_menu_item_with_ac("_About", "win.about", None))
        self.menu_bar.add(help_item)

        self.menu_bar.show_all()

    @staticmethod
    def _get_menu_item(name) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=name)
        item.set_use_underline(True)
        return item

    def _get_menu_item_with_ac(self, name: str, action: str, key):
        item = self._get_menu_item(name)
        if key:
            item.add_accelerator("activate", self.accel_group, key,
                                 Gdk.ModifierType.CONTROL_MASK,
                                 Gtk.AccelFlags.VISIBLE)
        item.set_action_name(action)
        return item

    def setup_source(self):
        lang_manager = GtkSource.LanguageManager()
        self.source_buffer.set_language(lang_manager.get_language('qubes-rpc'))

        self.source_buffer.set_highlight_syntax(True)
        self.source_view.set_show_line_numbers(True)
        self.source_view.set_input_hints(
            self.source_view.get_input_hints() | Gtk.InputHints.NO_EMOJI)
        self.source_view.set_monospace(True)
        self.source_buffer.connect('changed', self._text_changed)
        self.source_buffer.get_undo_manager().connect('can-redo-changed',
                                                      self._redo_changed)
        self.source_buffer.get_undo_manager().connect('can-undo-changed',
                                                      self._undo_changed)

        style_manager = GtkSource.StyleSchemeManager()
        if is_theme_light(self.main_window):
            scheme = style_manager.get_scheme("classic")
            self.source_buffer.set_style_scheme(scheme)
        else:
            scheme = style_manager.get_scheme("cobalt")
            self.source_buffer.set_style_scheme(scheme)

    def _ask_to_quit(self, *_args):
        if self.source_buffer.get_modified():
            # changes can be saved
            response = ask_question(
                self.main_window,
                "Unsaved changes found",
                "Do you want to save changes before exiting?")
            if response == Gtk.ResponseType.YES:
                if not self._save():
                    return True
            elif response == Gtk.ResponseType.CANCEL:
                return True
        self._quit()
        return False

    def _quit(self, *_args):
        self.quit()

    def _new(self, *_args):
        if self.action_items['save'].get_enabled():
            response = ask_question(
                self.main_window,
                "Unsaved changes found",
                "Do you want to save changes before creating a new file?")
            if response == Gtk.ResponseType.YES:
                if not self._save():
                    return
            elif response == Gtk.ResponseType.CANCEL:
                return

        ask_dialog = Gtk.MessageDialog(transient_for=self.main_window,
                                       modal=True,
                                       message_type=Gtk.MessageType.QUESTION,
                                       buttons=Gtk.ButtonsType.OK_CANCEL,
                                       text="Name of the new policy file:")

        ask_dialog.set_title("New file")
        entry = Gtk.Entry()
        ask_dialog.get_content_area().pack_end(entry, False, False, 0)

        # manually connect Enter to closing the window
        entry.connect('activate', lambda *_args:
            ask_dialog.response(Gtk.ResponseType.OK))

        ask_dialog.show_all()
        try:
            response = ask_dialog.run()
            if response != Gtk.ResponseType.OK:
                return
            new_name = entry.get_text()
        finally:
            ask_dialog.destroy()

        # validation - only alphanumerics and - _
        if not re.compile(r'^[\w-]+$').match(new_name):
            show_error(self.main_window, "Invalid policy file name",
                       f"Invalid policy file name: {new_name}. Policy file "
                       "names must contain only alphanumeric characters, "
                       "underscore and hyphen.")
            return

        # try to create new file
        if new_name in self.policy_client.policy_list():
            show_error(self.main_window, "File already exists",
                       f"Policy file: {new_name} already exists.")
            return

        self.token = "new"
        self._set_policy_file(new_name, "")


    def _save(self, *_args):
        """Save changes. If successful, return True."""
        try:
            self.policy_client.policy_replace(self.filename,
                                              self.policy_text, self.token)
        except subprocess.CalledProcessError as ex:
            err_msg = "An error occurred while trying to save the policy" \
                      " file:\n"
            if ex.stdout:
                err_msg += ex.stdout.decode()
            else:
                err_msg += str(ex)
            show_error(self.main_window, "Failed to save policy", err_msg)
            return False
        self.open_policy_file(self.filename)
        self.source_buffer.set_modified(False)
        self.action_items['save'].set_enabled(False)
        self.action_items['save_exit'].set_enabled(False)
        return True

    def _save_exit(self, *_args):
        if self._save():
            self._quit()

    def _open(self, *_args):
        self.file_select_handler.show_dialog()

    def _redo(self, *_args):
        self.source_buffer.redo()

    def _undo(self, *_args):
        self.source_buffer.undo()

    def _copy(self, *_args):
        self.source_buffer.copy_clipboard(self.clipboard)

    def _paste(self, *_args):
        self.source_buffer.paste_clipboard(self.clipboard, None, True)

    def _reset(self, *_args):
        if self.token != "new":
            self.open_policy_file(self.filename)
        else:
            self._set_policy_file(self.filename, "")

    def _about(self, *_args):
        self.about_window.show()

    def _toggle_help(self, *_args):
        self.help_window.set_visible(not self.help_window.get_visible())

    def _set_policy_file(self, name,
                         contents=''):
        """If name is an empty string, disable all available edit buttons
         and ignore contents to show a generic error message"""
        if not name:
            contents = "# Create new file or open an existing one."
            self.source_view.set_sensitive(False)
            self.error_info.set_visible(False)
        else:
            self.source_view.set_sensitive(True)
            self.error_info.set_visible(True)
        self.filename = name
        self.source_buffer.begin_not_undoable_action()
        self.source_buffer.set_text(contents)
        self.window_title = 'Qubes OS Policy Editor - ' + self.filename
        self.main_window.set_title(self.window_title)
        self.source_buffer.set_modified(False)
        self.source_buffer.end_not_undoable_action()
        self.action_items['undo'].set_enabled(False)
        self.action_items['redo'].set_enabled(False)
        self.action_items['save'].set_enabled(False)
        self.action_items['save_exit'].set_enabled(False)

    def open_policy_file(self, name: Optional[str]):
        """Open file of provided name.
        If name is None, nothing will happen.
        If name is an empty string, do not open a file and show information
        about that.
        If name is a non-empty string, try to open provided file. If failed,
        ask user what to do.
        """
        if name is None:
            return
        if name == '':
            self.token = None
            text = ''
        else:
            try:
                text, self.token = self.policy_client.policy_get(name)
            except subprocess.CalledProcessError as ex:
                if ex.returncode == 126:
                    show_error(self.main_window, "Access denied",
                               "Access denied to file {}.".format(name))
                    response = Gtk.ResponseType.NO
                else:
                    response = ask_question(
                        self.main_window, "Policy file not found",
                        "File {} not found. Do you want to create a "
                        "new policy file?".format(name))
                if response == Gtk.ResponseType.YES:
                    # make new file
                    text = ""
                    self.token = "new"
                elif response == Gtk.ResponseType.NO:
                    # make no file
                    name = ""
                    text = ""
                    self.token = None
                else:
                    # quit
                    self._quit()
                    return
        self._set_policy_file(name, text)

    def _text_changed(self, *_args):
        errors = []
        text = self.policy_text
        for lineno, line in enumerate(text.split('\n')):
            if not line or line.startswith('#') or line.startswith('!include'):
                continue
            try:
                StringPolicy(policy={'__main__': line}).rules
            except PolicySyntaxError as ex:
                msg = str(ex).split(':', 2)[-1]
                msg = html.escape(msg, quote=True)
                errors.append('<b>Line ' + str(lineno + 1) + '</b>:' + msg)

        if errors:
            self.error_info.get_style_context().remove_class('error_ok')
            self.error_info.get_style_context().add_class('error_bad')
            self.error_info.set_markup(
                '<b>Errors found:</b>\n' + '\n'.join(errors))
        else:
            self.error_info.get_style_context().remove_class('error_bad')
            self.error_info.get_style_context().add_class('error_ok')
            self.error_info.set_text("No errors found!")

        if self.source_buffer.get_modified():
            self.main_window.set_title(self.window_title + ' *')
        else:
            self.main_window.set_title(self.window_title)

        if not errors and self.source_buffer.get_modified():
            self.action_items['save'].set_enabled(True)
            self.action_items['save_exit'].set_enabled(True)
        else:
            self.action_items['save'].set_enabled(False)
            self.action_items['save_exit'].set_enabled(False)

        # source_buffer can_undo and can_redo always report False here
        # do not use them to fix undo/redo enabledness

    def _redo_changed(self, undo_manager):
        self.action_items['redo'].set_enabled(undo_manager.can_redo())

    def _undo_changed(self, undo_manager):
        self.action_items['undo'].set_enabled(undo_manager.can_undo())

    @property
    def policy_text(self):
        return self.source_buffer.get_text(
            self.source_buffer.get_start_iter(),
            self.source_buffer.get_end_iter(), False)

def main():
    """
    Start the app
    """
    policy_client = PolicyClient()
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = ''
    app = PolicyEditor(filename, policy_client)
    app.run()

if __name__ == '__main__':
    sys.exit(main())
