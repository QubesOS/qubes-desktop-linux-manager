#!/usr/bin/python
#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2024  Piotr Bartman-Szwarc <prbartman@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
""" Agent running in user session, responsible for asking the user about device
attachment."""

import os
import argparse
import asyncio

import importlib.resources

# pylint: disable=import-error,wrong-import-position
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# pylint: enable=import-error

# pylint: disable=wrong-import-order
import gbulb

# pylint: enable=wrong-import-position

from qrexec.server import SocketService
from qrexec.utils import sanitize_domain_name
from qrexec.tools.qrexec_policy_agent import (
    VMListModeler, RPCConfirmationWindow)
from qubesadmin.device_protocol import DeviceSerializer


DEVICE_AGENT_SOCKET_PATH = "/var/run/qubes/device-agent.GUI"


class VMAndPortListModeler(VMListModeler):
    def __init__(self, options, domains_info=None):
        super().__init__(domains_info)
        self._override_entries(options)

    def _override_entries(self, options):
        self._entries = {}
        for name, vm in self._domains_info.items():
            if name.startswith("@dispvm:"):
                vm_name = name[len("@dispvm:"):]
                prefix = "Disposable VM: "
            else:
                vm_name = name
                prefix = ""
            sanitize_domain_name(vm_name, assert_sanitized=True)

            icon = self._get_icon(vm.get("icon", None))

            display_name = prefix + vm_name + options.get(name, "")
            display_name = display_name.strip()
            self._entries[display_name] = {
                "api_name": vm_name,
                "icon": icon,
                "vm": vm,
            }

    def apply_icon(self, entry, qube_name):
        if isinstance(entry, Gtk.Entry):
            for vm_info in self._entries.values():
                if qube_name == vm_info['api_name']:
                    entry.set_icon_from_pixbuf(
                        Gtk.EntryIconPosition.PRIMARY, vm_info["icon"],
                    )
                    break
            else:
                raise ValueError(
                    f"The following source qube does not exist: {qube_name}")
        else:
            raise TypeError(
                "Only expecting Gtk.Entry objects to want our icon."
            )


class AttachmentConfirmationWindow(RPCConfirmationWindow):
    # pylint: disable=too-few-public-methods,too-many-instance-attributes
    _source_file_ref = importlib.resources.files("qui").joinpath(
        os.path.join("devices", "AttachConfirmationWindow.glade"))

    _source_id = {
        "window": "AttachConfirmationWindow",
        "ok": "okButton",
        "cancel": "cancelButton",
        "source": "sourceEntry",
        "device_label": "deviceLabel",
        "target": "TargetCombo",
        "error_bar": "ErrorBar",
        "error_message": "ErrorMessage",
    }

    # We reuse most parts of superclass, but we need custom init,
    # so we DO NOT call super().__init__()
    # pylint: disable=super-init-not-called
    def __init__(
        self,
        entries_info, source, device_name, argument, targets_list, target=None
    ):
        # pylint: disable=too-many-arguments
        sanitize_domain_name(source, assert_sanitized=True)
        DeviceSerializer.sanitize_str(
            device_name, DeviceSerializer.ALLOWED_CHARS_PARAM,
            error_message="Invalid device name")

        self._gtk_builder = Gtk.Builder()
        with importlib.resources.as_file(self._source_file_ref) as path:
            self._gtk_builder.add_from_file(str(path))
        self._rpc_window = self._gtk_builder.get_object(
            self._source_id["window"]
        )
        self._rpc_ok_button = self._gtk_builder.get_object(
            self._source_id["ok"]
        )
        self._rpc_cancel_button = self._gtk_builder.get_object(
            self._source_id["cancel"]
        )
        self._device_label = self._gtk_builder.get_object(
            self._source_id["device_label"]
        )
        self._source_entry = self._gtk_builder.get_object(
            self._source_id["source"]
        )
        self._rpc_combo_box = self._gtk_builder.get_object(
            self._source_id["target"]
        )
        self._error_bar = self._gtk_builder.get_object(
            self._source_id["error_bar"]
        )
        self._error_message = self._gtk_builder.get_object(
            self._source_id["error_message"]
        )
        self._target_name = None

        self._focus_helper = self._new_focus_stealing_helper()

        self._device_label.set_markup(device_name)

        self._entries_info = entries_info

        options = {name: " " + options for vm_data in targets_list
                   for name, _, options in (vm_data.partition(" "),)}
        list_modeler = self._new_vm_list_modeler_overridden(options)

        list_modeler.apply_model(
            self._rpc_combo_box,
            options.keys(),
            selection_trigger=self._update_ok_button_sensitivity,
            activation_trigger=self._clicked_ok,
        )

        self._source_entry.set_text(source + ":" + argument)
        list_modeler.apply_icon(self._source_entry, source)

        self._confirmed = None

        self._set_initial_target(source, target)

        self._connect_events()

    def _new_vm_list_modeler_overridden(self, options):
        return VMAndPortListModeler(options, self._entries_info)


async def confirm_attachment(
    entries_info, source, device_name, argument, targets_list, target=None
):
    # pylint: disable=too-many-arguments
    window = AttachmentConfirmationWindow(
        entries_info, source, device_name, argument, targets_list, target
    )

    return await window.confirm_rpc()


class DeviceAgent(SocketService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._app = Gtk.Application()
        self._app.set_application_id("qubes.device-agent")
        self._app.register()

    async def handle_request(self, params, service, source_domain):
        if service != "device-agent.GUI":
            raise ValueError("unknown service name: {}".format(service))
        source = params["source"]
        device_name = params["device_name"]
        argument = params["argument"]
        targets = params["targets"]
        default_target = params["default_target"]

        entries_info = {}
        for domain_name, icon in params["icons"].items():
            entries_info[domain_name] = {"icon": icon}

        target = await confirm_attachment(
            entries_info,
            source,
            device_name,
            argument,
            targets,
            default_target or None,
        )

        if target:
            return f"allow:{target}"
        return "deny"


parser = argparse.ArgumentParser()

parser.add_argument(
    "-s",
    "--socket-path",
    metavar="DIR",
    type=str,
    default=DEVICE_AGENT_SOCKET_PATH,
    help="path to socket",
)


def main():
    args = parser.parse_args()

    gbulb.install()
    agent = DeviceAgent(args.socket_path)

    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
