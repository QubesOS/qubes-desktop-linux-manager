#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2017 boring-stuff <boring-stuff@users.noreply.github.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, see <https://www.gnu.org/licenses/>.
#
import unittest
import time
from gi.repository import Gtk
import qui.tray.domains as domains_widget
from qubesadmin import Qubes


class DomainsWidgetTest(unittest.TestCase):

    def setUp(self):
        super(DomainsWidgetTest, self).setUp()

        self.widget = domains_widget.DomainTray("org.qubes.ui.tray.Domains")
        self.widget.initialize_menu()

        self.qapp = Qubes()

    def tearDown(self):
        del self.qapp
        del self.widget
        super(DomainsWidgetTest, self).tearDown()

    def test_00_icon_loads(self):
        self.assertGreater(len(self.widget.tray_menu), 0, "Tray menu is empty!")

    def test_01_correct_vm_state(self):
        # are all running VMs listed
        domains_in_widget = []
        for menu_item in self.widget.tray_menu:
            domain = self.qapp.domains[menu_item.vm["name"]]
            domains_in_widget.append(domain)
            self.assertTrue(
                domain.is_running(), "halted domain listed incorrectly"
            )
        for domain in self.qapp.domains:
            if domain.klass != "AdminVM":
                self.assertEqual(
                    domain in domains_in_widget,
                    domain.is_running(),
                    "domain missing from list",
                )

    def test_02_stop_vm(self):
        domain_to_stop = self.qapp.domains["test-running"]

        if not domain_to_stop.is_running():
            domain_to_stop.start()
            while domain_to_stop.get_power_state() != "Running":
                time.sleep(1)
            time.sleep(10)

        menu_item = self.__find_menu_item(domain_to_stop)
        self.assertIsNotNone(menu_item, "running item incorrectly not listed")

        domain_to_stop.shutdown()

        countdown = 100

        while domain_to_stop.get_power_state() != "Halted" and countdown > 0:
            time.sleep(1)
            countdown -= 1

        self.__refresh_gui(20)

        menu_item = self.__find_menu_item(domain_to_stop)
        self.assertIsNone(menu_item, "stopped item still incorrectly listed")

    def test_03_start_vm(self):
        domain_to_start = self.qapp.domains["test-halted"]

        if domain_to_start.is_running():
            domain_to_start.shutdown()
            while domain_to_start.get_power_state() != "Halted":
                time.sleep(1)
            time.sleep(10)

        # check if selected domain is correctly not listed
        item = self.__find_menu_item(domain_to_start)
        self.assertIsNone(item, "domain incorrectly listed as running")

        # start domain
        domain_to_start.start()

        # should finish starting
        countdown = 100
        while countdown > 0:
            if domain_to_start.get_power_state() == "Running":
                self.__refresh_gui(45)
                item = self.__find_menu_item(domain_to_start)
                self.assertIsNotNone(item, "domain not listed as started")
                self.assertIsNotNone(item, "item incorrectly not listed")
                self.assertIsInstance(
                    item.get_submenu(),
                    domains_widget.StartedMenu,
                    "incorrect menu (debug not start)",
                )
                break
            time.sleep(1)
            countdown -= 1

        domain_to_start.shutdown()

    def __find_menu_item(self, vm):
        for menu_item in self.widget.tray_menu:
            menu_domain = self.qapp.domains[menu_item.vm["name"]]
            if menu_domain == vm:
                return menu_item
        return None

    @staticmethod
    def __refresh_gui(delay=0):
        time.sleep(delay)
        while Gtk.events_pending():
            Gtk.main_iteration_do(blocking=True)


if __name__ == "__main__":
    unittest.main()
