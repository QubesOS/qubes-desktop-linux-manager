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
"""helper functions for various qui tools"""
# pylint: disable=wrong-import-position,import-error
import asyncio
import json
import sys
import traceback
from html import escape

from qubesadmin import exc

import gettext

import importlib.resources
from datetime import datetime

t = gettext.translation("desktop-linux-manager", fallback=True)
_ = t.gettext

import gi  # isort:skip

gi.require_version("Gtk", "3.0")  # isort:skip
from gi.repository import Gtk  # isort:skip

with importlib.resources.files("qui").joinpath("eol.json").open() as stream:
    EOL_DATES = json.load(stream)
# remove the following suffixes when checking for EOL
SUFFIXES = ["-minimal", "-xfce"]


def run_asyncio_and_show_errors(loop, tasks, name, restart=True):
    """
    Run listed asyncio tasks, show error message on errors and return
    correct exit code.
    :param loop: main loop
    :param tasks: list of asyncio tasks
    :param name: name of the widget/program
    :param restart: should the user be told that the widget will restart itself?
    :return: exit code
    """
    done, _unused = loop.run_until_complete(
        asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    )

    exit_code = 0

    message = _(
        "<b>Whoops. A critical error in {} has occurred.</b>"
        " This is most likely a bug."
    ).format(name)
    if restart:
        message += _(" {} will restart itself.").format(name)

    for d in done:  # pylint: disable=invalid-name
        try:
            d.result()
        except Exception as _ex:  # pylint: disable=broad-except
            exc_type, exc_value = sys.exc_info()[:2]
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK
            )
            dialog.set_title(_("Houston, we have a problem..."))
            dialog.set_markup(message)
            exc_value_descr = escape(str(exc_value))
            traceback_descr = escape(traceback.format_exc(limit=10))
            exc_description = "\n<b>{}</b>: {}\n{}".format(
                exc_type.__name__, exc_value_descr, traceback_descr
            )
            dialog.format_secondary_markup(exc_description)
            dialog.run()
            exit_code = 1
    return exit_code


def check_update(vm) -> bool:
    """Return true if the given template/standalone vm is updated or not
    updateable or skipped. default returns true"""
    try:
        if not vm.features.get("updates-available", False):
            return True
        if not getattr(vm, "updateable", False):
            return True
        if bool(vm.features.get("skip-update", False)):
            return True
    except exc.QubesException:
        return True
    return False


def check_support(vm) -> bool:
    """Return true if the given template/standalone vm is still supported, by
    default returns true"""
    try:
        # first, we skip VMs with `skip-update` feature set to true
        if bool(vm.features.get("skip-update", False)):
            return True

        # next, check if qube itself has known eol
        eol_string: str = vm.features.get("os-eol", "")

        if not eol_string:
            template_name: str = vm.features.get("template-name", "")
            if not template_name:
                return True
            for suffix in SUFFIXES:
                template_name = template_name.removesuffix(suffix)
            eol_string = EOL_DATES.get(template_name, None)
            if not eol_string:
                return True
    except exc.QubesException:
        return True
    eol = datetime.strptime(eol_string, "%Y-%m-%d")
    return eol > datetime.now()
