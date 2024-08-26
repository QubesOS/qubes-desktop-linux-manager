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
import sys
import asyncio

from qubes import Qubes

from qrexec.server import call_socket_service

SOCKET_PATH = "/var/run/qubes"


def main():
    socket = "device-agent.GUI"

    guivm = sys.argv[1]

    number_of_targets = len(sys.argv) - 5
    doms = Qubes().domains

    params = {
        "source": sys.argv[2],
        "device_name": sys.argv[4],
        "argument": sys.argv[3],
        "targets": sys.argv[5:],
        "default_target": sys.argv[5] if number_of_targets == 1 else "",
        "icons": {
            doms[d].name
            if doms[d].klass != "DispVM" else f'@dispvm:{doms[d].name}':
            doms[d].icon for d in doms.keys()
        },
    }

    ask_response = asyncio.run(call_socket_service(
        guivm, socket, "dom0", params, SOCKET_PATH
    ))

    if ask_response.startswith("allow:"):
        print(ask_response[len("allow:"):], end="")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
