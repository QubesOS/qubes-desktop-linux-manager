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
# type: ignore

from unittest.mock import patch, call

from ..global_config.usb_devices import InputDeviceHandler, U2FPolicyHandler, \
    DevicesHandler

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk


def test_input_devices_simple_policy(test_qapp,
                                     test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb})

    for widget in handler.widgets.values():
        assert widget.get_parent()

    assert handler.widgets[
               ('qubes.InputMouse', 'sys-usb')].model.get_selected() == 'ask'
    assert handler.widgets[('qubes.InputKeyboard',
                            'sys-usb')].model.get_selected() == 'deny'
    assert handler.widgets[
               ('qubes.InputTablet', 'sys-usb')].model.get_selected() == 'allow'

    # check that things are in correct place: change something from fourth row,
    # second column (should be tablet widget for sys-usb)
    handler.policy_grid.get_child_at(1, 3).model.select_value('deny')

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules("""
qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_input_devices_complex_policy(test_qapp,
                                     test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    sys_net = test_qapp.domains['sys-net']
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm allow
qubes.InputMouse * sys-net @adminvm deny
qubes.InputKeyboard * sys-net @adminvm deny
qubes.InputTablet * sys-net @adminvm allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb, sys_net})

    for widget in handler.widgets.values():
        assert widget.get_parent()

    assert handler.widgets[
               ('qubes.InputMouse', 'sys-usb')].model.get_selected() == 'ask'
    assert handler.widgets[('qubes.InputKeyboard',
                            'sys-usb')].model.get_selected() == 'deny'
    assert handler.widgets[
               ('qubes.InputTablet', 'sys-usb')].model.get_selected() == 'allow'
    assert handler.widgets[
               ('qubes.InputMouse', 'sys-net')].model.get_selected() == 'deny'
    assert handler.widgets[('qubes.InputKeyboard',
                            'sys-net')].model.get_selected() == 'deny'
    assert handler.widgets[
               ('qubes.InputTablet', 'sys-net')].model.get_selected() == 'allow'

    # which row is sys_net in? change KB for it
    i = 1
    while i <= 2:
        if handler.policy_grid.get_child_at(i, 0).token_name == 'sys-net':
            handler.policy_grid.get_child_at(i, 1).model.select_value('allow')
            break
        i += 1
    else:
        raise AssertionError("no sys-net in grid")

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules("""
qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm allow
qubes.InputMouse * sys-net @adminvm deny
qubes.InputKeyboard * sys-net @adminvm allow
qubes.InputTablet * sys-net @adminvm allow
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert sorted([str(rule) for rule in expected_rules]) == \
               sorted([str(rule) for rule in rules])


def test_input_devices_no_policy_one_usb(test_qapp,
                                         test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb})

    # check if defaults worked
    for widget in handler.widgets.values():
        assert widget.model.get_selected() == 'deny'
        assert widget.get_parent()

    # no warning is needed
    assert not handler.warn_box.get_visible()

    # change things up
    mouse_widget = handler.widgets[('qubes.InputMouse', 'sys-usb')]
    mouse_widget.model.select_value('ask')

    assert mouse_widget.model.get_selected() == 'ask'
    assert handler.get_unsaved() == 'Mouse input settings'

    # revert
    handler.reset()
    assert mouse_widget.model.get_selected() == 'deny'
    assert handler.get_unsaved() == ''

    # change and save
    mouse_widget = handler.widgets[('qubes.InputMouse', 'sys-usb')]
    mouse_widget.model.select_value('ask')

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
"""qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_input_devices_faulty_policy_lines(test_qapp,
                                           test_policy_manager, real_builder):
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-usb @adminvm deny
qubes.InputKeyboard * sys-usb @adminvm ask default_target=@adminvm
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    sys_usb = test_qapp.domains['sys-usb']
    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb})

    # check if defaults worked
    for designation, widget in handler.widgets.items():
        if designation[0] == 'qubes.InputKeyboard':
            assert widget.model.get_selected() == 'ask'
        else:
            assert widget.model.get_selected() == 'deny'

    # exactly 3 widgets
    assert len(handler.widgets) == 3

    # no warning is needed
    assert not handler.warn_box.get_visible()

    # if user changes nothing, there should be no changes
    assert handler.get_unsaved() == ''


def test_input_devices_faulty_policy_lines_2(test_qapp,
                                             test_policy_manager, real_builder):
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-net @adminvm deny
qubes.InputKeyboard * sys-usb @adminvm ask default_target=@adminvm
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    sys_usb = test_qapp.domains['sys-usb']
    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb})

    # check if defaults worked
    for designation, widget in handler.widgets.items():
        if designation[0] == 'qubes.InputKeyboard':
            assert widget.model.get_selected() == 'ask'
        else:
            assert widget.model.get_selected() == 'deny'

    # check if there's warning visible
    assert handler.warn_box.get_visible()

    # change something
    mouse_widget = handler.widgets[('qubes.InputTablet', 'sys-usb')]
    mouse_widget.model.select_value('allow')

    # the weird rule should not be discarded, I think
    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
"""
qubes.InputMouse * sys-net @adminvm deny
qubes.InputKeyboard * sys-usb @adminvm ask default_target=@adminvm
qubes.InputMouse * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm allow
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_input_devices_no_usbvm(test_qapp,
                                test_policy_manager, real_builder):
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-usb @adminvm ask default_target=@adminvm
qubes.InputKeyboard * sys-usb @adminvm deny
qubes.InputTablet * sys-usb @adminvm deny
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, set())

    for widget in handler.widgets.values():
        assert not widget.get_parent()

    assert handler.warn_box.get_visible()

    assert handler.get_unsaved() == ''

    # no policy should be changed
    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()
        assert len(mock_save.mock_calls) == 0


def test_input_devices_faulty_policy_err(test_qapp,
                                         test_policy_manager, real_builder):
    test_policy_manager.policy_client.files['50-config-input'] = """
qubes.InputMouse * sys-usb @adminvm allow target=test-red
qubes.InputTablet * sys-usb test-red deny
qubes.InputKeyboard * sys-usb @adminvm ask default_target=sys-net
"""
    test_policy_manager.policy_client.file_tokens['50-config-input'] = '55'

    sys_usb = test_qapp.domains['sys-usb']
    handler = InputDeviceHandler(test_qapp, test_policy_manager,
                                 real_builder, {sys_usb})

    # check if defaults worked
    for _, widget in handler.widgets.items():
        assert widget.model.get_selected() == 'deny'

    # check if there's warning visible
    assert handler.warn_box.get_visible()


def test_u2f_handler_init(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert handler.get_unsaved() == ''

    # settings from conftest: only vms that have this available are 'test-vm'
    # and 'fedora-35', only test-vm can use the service, policy is default
    testvm = test_qapp.domains['test-vm']
    testred = test_qapp.domains['test-red']
    fedora35 = test_qapp.domains['fedora-35']
    sysusb = test_qapp.domains['sys-usb']

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]
    assert handler.enable_some_handler.add_qube_model.is_vm_available(testvm)
    assert handler.enable_some_handler.add_qube_model.is_vm_available(fedora35)
    assert not handler.enable_some_handler.add_qube_model.is_vm_available(
        testred)
    assert not handler.enable_some_handler.add_qube_model.is_vm_available(
        sysusb)

    assert not handler.register_check.get_active()
    assert not handler.register_some_handler.selected_vms

    assert not handler.blanket_check.get_active()
    assert not handler.blanket_handler.selected_vms


def test_u2f_handler_init_disable(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert not handler.enable_check.get_active()
    assert not handler.problem_fatal_box.get_visible()


def test_u2f_handler_init_no_u2f_in_sysub(
        test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_qapp.expected_calls[
        ('sys-usb', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert not handler.enable_check.get_sensitive()
    assert not handler.enable_check.get_active()
    assert handler.problem_fatal_box.get_visible()


def test_u2f_handler_no_usb_vm(
        test_qapp, test_policy_manager, real_builder):
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               set())

    assert not handler.enable_check.get_sensitive()
    assert not handler.enable_check.get_active()
    assert handler.problem_fatal_box.get_visible()


def test_u2f_handler_init_policy(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
u2f.Register * fedora-35 sys-usb allow
u2f.Register * test-vm sys-usb allow
u2f.Authenticate * test-vm sys-usb allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]

    assert handler.register_check.get_active()
    assert handler.register_some_radio.get_active()
    assert handler.register_some_handler.selected_vms == [fedora35, testvm]

    assert handler.blanket_check.get_active()
    assert handler.blanket_handler.selected_vms == [testvm]


def test_u2f_handler_init_no_policy(test_qapp,
                                    test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    # disable service
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert handler.enable_check.get_sensitive()
    assert not handler.enable_check.get_active()

    assert handler.register_check.get_sensitive()
    assert not handler.register_check.get_active()

    assert handler.blanket_check.get_sensitive()
    assert not handler.blanket_check.get_active()


def test_u2f_handler_init_policy_2(test_qapp,
                                   test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register sys-usb @anyvm allow target=dom0
u2f.Register * @anyvm sys-usb allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]

    assert handler.register_check.get_active()
    assert handler.register_all_radio.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()


def test_u2f_handler_init_policy_mismatch(test_qapp,
                                          test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'
    test_qapp.expected_calls[
        ('test-standalone', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register test-standalone @anyvm allow target=dom0
u2f.Register * @anyvm test-standalone allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})
    assert handler.usb_qube_model.get_selected() == sys_usb

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]

    assert not handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert handler.error_handler.error_box.get_visible()


def test_u2f_handler_2_usbvms(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_standalone = test_qapp.domains['test-standalone']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('test-standalone', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'
    test_qapp.expected_calls[
        ('test-standalone', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register test-standalone @anyvm allow target=dom0
u2f.Register * @anyvm test-standalone allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb, test_standalone})
    assert handler.usb_qube_model.get_selected() == test_standalone
    assert handler.usb_qube_model.is_vm_available(sys_usb)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    assert handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert not handler.error_handler.error_box.get_visible()


def test_u2f_handler_2_usbvms_switch(test_qapp,
                                     test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_standalone = test_qapp.domains['test-standalone']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[('test-standalone', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'0\x001'
    test_qapp.expected_calls[
        ('test-standalone', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = b'0\x001'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register test-standalone @anyvm allow target=dom0
u2f.Register * @anyvm test-standalone allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb, test_standalone})
    assert handler.usb_qube_model.get_selected() == test_standalone
    assert handler.usb_qube_model.is_vm_available(sys_usb)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    assert handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert not handler.error_handler.error_box.get_visible()

    handler.usb_qube_model.select_value(sys_usb.name)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    assert not handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert handler.error_handler.error_box.get_visible()

    handler.usb_qube_model.select_value(test_standalone.name)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    assert handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert not handler.error_handler.error_box.get_visible()


def test_u2f_handler_2_usbvms_broken(test_qapp, test_policy_manager,
                                     real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    test_standalone = test_qapp.domains['test-standalone']
    testvm = test_qapp.domains['test-vm']
    test_qapp.expected_calls[
        ('test-standalone', 'admin.vm.feature.CheckWithTemplate',
         U2FPolicyHandler.SUPPORTED_SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    test_policy_manager.policy_client.files['50-config-u2f'] = """
policy.RegisterArgument +u2f.Register test-standalone @anyvm allow target=dom0
u2f.Register * @anyvm test-standalone allow
"""
    test_policy_manager.policy_client.file_tokens['50-config-u2f'] = '55'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb, test_standalone})
    assert handler.usb_qube_model.get_selected() == sys_usb
    assert not handler.usb_qube_model.is_vm_available(test_standalone)

    assert handler.enable_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    assert not handler.register_check.get_active()

    assert not handler.blanket_check.get_active()
    assert not handler.problem_fatal_box.get_visible()
    assert handler.error_handler.error_box.get_visible()


def test_u2f_unsaved_reset(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']

    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]

    handler.enable_check.set_active(False)
    assert handler.get_unsaved() == 'U2F disabled'

    handler.enable_check.set_active(True)
    assert handler.get_unsaved() == ''

    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()

    handler.enable_some_handler.add_selected_vm(fedora35)
    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]
    assert handler.get_unsaved() == 'List of qubes with U2F enabled changed'

    handler.reset()
    assert handler.enable_check.get_active()
    assert not handler.register_check.get_active()
    assert not handler.blanket_check.get_active()
    assert handler.enable_some_handler.selected_vms == [testvm]
    assert handler.get_unsaved() == ''

    handler.blanket_check.set_active(True)
    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)
    handler.blanket_handler.add_selected_vm(fedora35)
    handler.register_some_handler.add_selected_vm(fedora35)

    assert handler.blanket_handler.selected_vms == [fedora35]
    assert handler.register_some_handler.selected_vms == [fedora35]
    assert 'U2F key registration' in handler.get_unsaved()
    assert 'unrestricted U2F key' in handler.get_unsaved()

    handler.reset()
    assert handler.get_unsaved() == ''
    assert not handler.blanket_handler.selected_vms
    assert not handler.register_some_handler.selected_vms

def test_u2f_save_disable(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    handler.enable_check.set_active(False)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        mock_apply.assert_called_with(
            test_qapp.domains['test-vm'], handler.SERVICE_FEATURE, None)
        assert len(mock_apply.mock_calls) == 1

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Authenticate * @anyvm @anyvm deny
u2f.Register * @anyvm @anyvm deny
policy.RegisterArgument +u2f.Register @anyvm @anyvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_save_service(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})
    fedora35 = test_qapp.domains['fedora-35']

    assert handler.enable_check.get_active()
    handler.enable_some_handler.add_selected_vm(fedora35)

    test_qapp.expected_calls[('fedora-35', 'admin.vm.feature.Set',
                              'service.qubes-u2f-proxy', b'1')] = b'0\x00'
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Set',
                              'service.qubes-u2f-proxy', b'1')] = b'0\x00'

    with patch.object(handler.policy_manager, 'save_rules') as mock_save:
        handler.save()

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Register * @anyvm @anyvm deny
policy.RegisterArgument +u2f.Authenticate @anyvm @anyvm deny
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_handler_save_complex(test_qapp, test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert not handler.enable_check.get_active()

    handler.enable_check.set_active(True)
    handler.enable_some_handler.add_selected_vm(testvm)
    handler.enable_some_handler.add_selected_vm(fedora35)

    handler.register_check.set_active(True)
    handler.register_all_radio.set_active(True)

    handler.blanket_check.set_active(True)
    handler.blanket_handler.add_selected_vm(testvm)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        assert call(test_qapp.domains['test-vm'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert call(test_qapp.domains['fedora-35'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert len(mock_apply.mock_calls) == 2

        expected_rules = handler.policy_manager.text_to_rules(
            """
policy.RegisterArgument +u2f.Authenticate sys-usb @anyvm allow target=dom0
u2f.Register * @anyvm sys-usb allow
u2f.Authenticate * test-vm sys-usb allow
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]


def test_u2f_handler_save_complex_2(test_qapp,
                                    test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    testvm = test_qapp.domains['test-vm']
    fedora35 = test_qapp.domains['fedora-35']
    test_qapp.expected_calls[('test-vm', 'admin.vm.feature.Get',
                             U2FPolicyHandler.SERVICE_FEATURE, None)] = \
        b'2\x00QubesFeatureNotFoundError\x00\x00' + \
        str(U2FPolicyHandler.SERVICE_FEATURE).encode() + b'\x00'

    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert not handler.enable_check.get_active()

    handler.enable_check.set_active(True)
    handler.enable_some_handler.add_selected_vm(testvm)
    handler.enable_some_handler.add_selected_vm(fedora35)

    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)
    handler.register_some_handler.add_selected_vm(fedora35)
    handler.register_some_handler.add_selected_vm(testvm)

    handler.blanket_check.set_active(False)

    with patch.object(handler.policy_manager, 'save_rules') as mock_save, \
            patch('qubes_config.global_config.usb_devices.'
               'apply_feature_change') as mock_apply:
        handler.save()

        assert call(test_qapp.domains['test-vm'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert call(test_qapp.domains['fedora-35'],
                    handler.SERVICE_FEATURE, True) in mock_apply.mock_calls
        assert len(mock_apply.mock_calls) == 2

        expected_rules = handler.policy_manager.text_to_rules(
            """
u2f.Register * fedora-35 sys-usb allow
u2f.Register * test-vm sys-usb allow
policy.RegisterArgument +u2f.Authenticate sys-usb @anyvm allow target=dom0
""")
        assert len(mock_save.mock_calls) == 1
        _, rules, _ = mock_save.mock_calls[0].args
        assert [str(rule) for rule in expected_rules] == \
               [str(rule) for rule in rules]

def test_u2f_handler_add_without_service(test_qapp,
                                         test_policy_manager, real_builder):
    sys_usb = test_qapp.domains['sys-usb']
    fedora35 = test_qapp.domains['fedora-35']
    testvm = test_qapp.domains['test-vm']
    handler = U2FPolicyHandler(test_qapp, test_policy_manager, real_builder,
                               {sys_usb})

    assert handler.get_unsaved() == ''

    # settings from conftest: only vms that have this available are 'test-vm'
    # and 'fedora-35', only test-vm can use the service, policy is default

    handler.register_check.set_active(True)
    handler.register_some_radio.set_active(True)

    assert not handler.register_some_handler.selected_vms
    assert handler.enable_some_handler.selected_vms == [testvm]

    handler.register_some_handler.add_button.clicked()
    handler.register_some_handler.add_qube_model.select_value('fedora-35')
    # refuse
    with patch('qubes_config.global_config.usb_devices.'
               'ask_question') as mock_question:
        mock_question.return_value = Gtk.ResponseType.NO
        handler.register_some_handler.add_confirm.clicked()
        assert mock_question.mock_calls
    assert not handler.register_some_handler.selected_vms
    assert handler.enable_some_handler.selected_vms == [testvm]

    # accept
    with patch('qubes_config.global_config.usb_devices.'
               'ask_question') as mock_question:
        mock_question.return_value = Gtk.ResponseType.YES
        handler.register_some_handler.add_confirm.clicked()
        assert mock_question.mock_calls
    assert handler.register_some_handler.selected_vms == [fedora35]

    assert handler.enable_some_handler.selected_vms == [fedora35, testvm]


def test_devices_handler_unsaved(test_qapp, test_policy_manager, real_builder):
    test_qapp.expected_calls[('sys-usb', "admin.vm.device.pci.Attached",
                              None, None)] = \
        b"0\x00dom0+00_0d.0 device_id='*' port_id='00_0d.0' devclass='pci' " \
        b"backend_domain='dom0' required='yes' attach_automatically='yes' " \
        b"_no-strict-reset='yes'\n"
    test_qapp.expected_calls[('dom0', "admin.vm.device.pci.Available",
                              None, None)] = \
        b"0\x0000_0d.0 device_id='0000:0000::p0c0300' port_id='00_0d.0' " \
        b"devclass='pci' backend_domain='dom0' interfaces='p0c0300' " \
        b"_function='0' _bus='00' _libvirt_name='pci_0000_00_0d_0' " \
        b"_device='0d'\n"

    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    assert handler.get_unsaved() == ''

    # some changes
    kb_widget = handler.input_handler.widgets[
        ('qubes.InputKeyboard', 'sys-usb')]
    assert kb_widget.model.get_selected() == 'deny'
    kb_widget.model.select_value('ask')

    assert handler.u2f_handler.enable_check.get_active()
    handler.u2f_handler.enable_check.set_active(False)

    assert 'Keyboard input' in handler.get_unsaved()
    assert 'U2F disabled' in handler.get_unsaved()


def test_devices_handler_detect_usbvms(test_qapp,
                                       test_policy_manager, real_builder):
    test_qapp.expected_calls[('sys-usb', "admin.vm.device.pci.Attached",
                              None, None)] = \
        b"0\x00dom0+00_0d.0 device_id='*' port_id='00_0d.0' devclass='pci' " \
        b"backend_domain='dom0' required='yes' attach_automatically='yes' " \
        b"_no-strict-reset='yes'\n"
    test_qapp.expected_calls[('test-standalone', "admin.vm.device.pci.Attached",
                              None, None)] = \
        b"0\x00dom0+00_0f.0 device_id='*' port_id='00_0f.0' devclass='pci' " \
        b"backend_domain='dom0' required='yes' attach_automatically='yes' " \
        b"_no-strict-reset='yes'\n"
    test_qapp.expected_calls[('dom0', "admin.vm.device.pci.Available",
                              None, None)] = \
        b"0\x0000_0f.0 device_id='0000:0000::p0c0300' port_id='00_0f.0' " \
        b"devclass='pci' backend_domain='dom0' interfaces='p0c0300' " \
        b"_function='0' _bus='00' _libvirt_name='pci_0000_00_0f_0' " \
        b"_device='0f'\n" \
        b"00_0d.0 device_id='0000:0000::p0c0300' port_id='00_0d.0' " \
        b"devclass='pci' backend_domain='dom0' interfaces='p0c0300' " \
        b"_function='0' _bus='00' _libvirt_name='pci_0000_00_0d_0' " \
        b"_device='0d'\n"

    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    sys_usb = test_qapp.domains['sys-usb']
    test_standalone = test_qapp.domains['test-standalone']

    assert handler.input_handler.usb_qubes == {sys_usb, test_standalone}


def test_devices_handler_save_reset(test_qapp,
                                    test_policy_manager, real_builder):
    handler = DevicesHandler(test_qapp, test_policy_manager, real_builder)

    # check all handlers have their save/reset called
    with patch.object(handler.u2f_handler, 'save') as mock_u2f, \
            patch.object(handler.input_handler, 'save') as mock_input:
        handler.save()
        mock_input.assert_called()
        mock_u2f.assert_called()

    with patch.object(handler.u2f_handler, 'reset') as mock_u2f, \
            patch.object(handler.input_handler, 'reset') as mock_input:
        handler.reset()
        mock_input.assert_called()
        mock_u2f.assert_called()


def test_devices_handler_no_sys_usb(test_qapp_simple,
                                    test_policy_manager, real_builder):
    handler = DevicesHandler(test_qapp_simple,
                             test_policy_manager, real_builder)

    assert not handler.input_handler.usb_qubes
    assert handler.u2f_handler.problem_fatal_box.get_visible()
    assert not handler.u2f_handler.enable_check.get_sensitive()
