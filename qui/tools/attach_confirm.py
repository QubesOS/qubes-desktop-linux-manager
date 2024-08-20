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
import os
import sys
import json
import asyncio

from qubes import Qubes


SOCKET_PATH = "/var/run/qubes"


def call_socket_service(
    remote_domain, service, source_domain, params, socket_path=SOCKET_PATH
):
    """
    Call a socket service, either over qrexec or locally.

    The request is JSON-encoded, response is plain ASCII text.
    """

    if remote_domain == source_domain:
        return call_socket_service_local(
            service, source_domain, params, socket_path
        )
    raise NotImplementedError()
    # return call_socket_service_remote(remote_domain, service, params)


async def call_socket_service_local(
    service, source_domain, params, socket_path=SOCKET_PATH
):
    if source_domain == "dom0":
        header = f"{service} dom0 name dom0\0".encode("ascii")
    else:
        header = f"{service} {source_domain}\0".encode("ascii")

    path = os.path.join(socket_path, service)
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write(header)
    writer.write(json.dumps(params).encode("ascii"))
    writer.write_eof()
    await writer.drain()
    response = await reader.read()
    return response.decode("ascii")


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
        guivm, socket, "dom0", params
    ))

    if ask_response.startswith("allow:"):
        print(ask_response[len("allow:"):], end="")
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
