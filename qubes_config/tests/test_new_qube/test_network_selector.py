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
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring

import qubesadmin
from ...new_qube.network_selector import NetworkSelector


def test_network_handler(test_qapp, new_qube_builder):
    handler = NetworkSelector(new_qube_builder, test_qapp)

    assert handler.get_selected_netvm() == qubesadmin.DEFAULT
    assert handler.network_current_widget.vm == test_qapp.default_netvm
    assert handler.network_current_widget.vm == test_qapp.domains["sys-net"]
    assert not handler.network_current_none.get_visible()

    # select none
    handler.network_none.set_active(True)

    assert handler.get_selected_netvm() is None
    assert handler.network_current_none.get_visible()

    handler.network_custom.set_active(True)
    assert handler.get_selected_netvm() != test_qapp.domains["sys-net"]
    handler.network_modeler.select_value("sys-net")
    assert not handler.network_current_none.get_visible()

    assert handler.get_selected_netvm() == test_qapp.domains["sys-net"]
    assert handler.network_current_widget.vm == test_qapp.domains["sys-net"]

    handler.network_default.set_active(True)
    assert handler.get_selected_netvm() == qubesadmin.DEFAULT
    assert handler.network_current_widget.vm == test_qapp.default_netvm


def test_network_handler_whonix(test_qapp_whonix, new_qube_builder):
    handler = NetworkSelector(new_qube_builder, test_qapp_whonix)

    assert handler.get_selected_netvm() == qubesadmin.DEFAULT

    handler.network_tor.set_active(True)

    assert (
        handler.get_selected_netvm() == test_qapp_whonix.domains["sys-whonix"]
    )
    assert (
        handler.network_current_widget.vm
        == test_qapp_whonix.domains["sys-whonix"]
    )
