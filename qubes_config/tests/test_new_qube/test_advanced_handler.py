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
# pylint: disable=protected-access

from ...new_qube.advanced_handler import AdvancedHandler


def test_advanced_handler(test_qapp, new_qube_builder):
    handler = AdvancedHandler(new_qube_builder, test_qapp)

    assert not handler.provides_network_check.get_active()
    assert not handler.get_provides_network()

    handler.provides_network_check.set_active(True)

    assert handler.provides_network_check.get_active()
    assert handler.get_provides_network()

    assert not handler.install_system_check.get_sensitive()
    assert not handler.get_install_system()

    # simulate a template changed to none signal
    handler._template_changed(None, None)

    assert handler.install_system_check.get_sensitive()
    assert handler.install_system_check.get_active()
    assert handler.get_install_system()

    handler.install_system_check.set_active(False)
    assert not handler.get_install_system()

    # check interaction with launch settings
    assert not handler.launch_settings_check.get_active()
    assert not handler.get_launch_settings()

    handler.launch_settings_check.set_active(True)
    assert not handler.install_system_check.get_active()
    assert handler.get_launch_settings()
    handler.install_system_check.set_active(True)
    assert not handler.launch_settings_check.get_active()
    assert not handler.get_launch_settings()

    handler._template_changed(None, "fedora-35")

    assert not handler.install_system_check.get_sensitive()
    assert not handler.get_install_system()

    # init ram

    assert handler.initram.get_value() == 0
    assert handler.get_init_ram() is None

    handler.initram.set_value(50)
    assert handler.initram.get_value() == 50
    assert handler.get_init_ram() == 50

    handler.initram.set_value(0)
    assert handler.initram.get_value() == 0
    assert handler.get_init_ram() is None

    # storage pool
    assert handler.get_pool() is None
    # defaults from conftest
    assert handler.pool.get_active_id() == "default (file)"

    handler.pool.set_active_id("lvm")
    assert handler.get_pool() == "lvm"

    handler.pool.set_active_id("default (file)")
    assert handler.get_pool() is None
