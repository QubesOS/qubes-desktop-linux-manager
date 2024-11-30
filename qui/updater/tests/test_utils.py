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
from qui.utils import check_support
from qubesadmin.tests.mock_app import MockQubes, MockQube


def test_check_support():
    qapp = MockQubes()
    vm_supported = MockQube(
        "test-qube-1", qapp, features={"os-eol": "2060-01-01"}
    )
    vm_not_supported = MockQube(
        "test-qube-2", qapp, features={"os-eol": "1990-01-01"}
    )
    fedora_min = MockQube(
        "test-qube-3", qapp, features={"template-name": "fedora-36-minimal"}
    )
    fedora_xfce = MockQube(
        "test-qube-4", qapp, features={"template-name": "fedora-35-xfce"}
    )
    wrong_name = MockQube(
        "test-qube-5", qapp, features={"template-name": "faedora-66"}
    )
    debian_minimal = MockQube(
        "test-qube-6", qapp, features={"template-name": "debian-9-minimal"}
    )
    normal_debian = MockQube(
        "test-qube-7", qapp, features={"template-name": "debian-8"}
    )
    nothing_special = MockQube("test-qube-8", qapp)

    qapp.update_vm_calls()

    assert check_support(vm_supported)
    assert not check_support(vm_not_supported)

    assert not check_support(fedora_min)
    assert not check_support(fedora_xfce)
    assert check_support(wrong_name)
    assert not check_support(debian_minimal)
    assert not check_support(normal_debian)
    assert check_support(nothing_special)
