# coding=utf-8
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023  Piotr Bartman <prbartman@invisiblethingslab.com>
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
import argparse

import pytest
from unittest.mock import patch
from unittest.mock import Mock

from qui.updater.tests.conftest import test_qapp_impl
from qui.updater.intro_page import IntroPage, UpdateRowWrapper, UpdatesAvailable
from qui.updater.updater import parse_args
from qui.updater.utils import ListWrapper, HeaderCheckbox

@patch('subprocess.check_output')
def test_populate_vm_list(
        mock_subprocess, real_builder, test_qapp,
        mock_next_button, mock_settings
):
    mock_log = Mock()
    sut = IntroPage(real_builder, mock_log, mock_next_button)
    test_qapp.expected_calls[
        ('test-standalone', "admin.vm.feature.Get", 'updates-available', None)
    ] = b"0\x00" + str(1).encode()
    # inconsistent output of qubes-vm-update, but it does not matter
    mock_subprocess.return_value = \
            b'Following templates will be updated:test-standalone'

    assert not sut.is_populated

    sut.populate_vm_list(test_qapp, mock_settings)

    assert sut.is_populated
    assert len(sut.list_store) == 4
    assert len(sut.get_vms_to_update()) == 1

    test_qapp.expected_calls[
        ('fedora-36', "admin.vm.feature.Get", 'updates-available', None)
    ] = b"0\x00" + str(1).encode()
    mock_subprocess.return_value = \
            b'Following templates will be updated:test-standalone,fedora-36'

    sut.populate_vm_list(test_qapp, mock_settings)
    assert len(sut.list_store) == 4
    assert len(sut.get_vms_to_update()) == 2


@pytest.mark.parametrize(
    "updates_available, expectations",
    (
        pytest.param((2, 6), (0, 2, 6, 12, 0)),
        pytest.param((6, 0), (0, 6, 12, 0)),
    ),
)
def test_on_header_toggled(
        real_builder, test_qapp, updates_available, expectations,
        mock_next_button, mock_settings, mock_list_store
):
    mock_log = Mock()
    sut = IntroPage(real_builder, mock_log, mock_next_button)

    # populate_vm_list
    sut.list_store = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        sut.list_store.append_vm(vm)

    assert len(sut.list_store) == 12

    for i, row in enumerate(sut.list_store):
        if i < updates_available[0]:
            value = True
        elif i < updates_available[1]:
            value = None
        else:
            value = False
        row.raw_row[row._UPDATES_AVAILABLE] = UpdatesAvailable.from_features(value, True)
    sut.head_checkbox.state = HeaderCheckbox.NONE

    for expected in expectations:
        selected_num = len([row for row in sut.list_store if row.selected])
        assert selected_num == expected
        assert sut.checkbox_column_button.get_inconsistent() \
               and expected not in (0, 12) \
               or sut.checkbox_column_button.get_active() \
               and expected == 12 \
               or not sut.checkbox_column_button.get_active() \
               and expected == 0
        assert mock_next_button.sensitive or expected == 0
        sut.on_header_toggled(None)


def test_on_checkbox_toggled(
        real_builder, test_qapp,
        mock_next_button, mock_settings, mock_list_store
):
    mock_log = Mock()
    sut = IntroPage(real_builder, mock_log, mock_next_button)

    # populate_vm_list
    sut.list_store = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        sut.list_store.append_vm(vm)

    assert len(sut.list_store) == 12

    sut.head_checkbox.state = HeaderCheckbox.NONE
    sut.head_checkbox.set_buttons()

    # If button is inconsistent we do not care if it is active or not
    # (we do not use this value)

    # no selected row
    assert not sut.checkbox_column_button.get_inconsistent()
    assert not sut.checkbox_column_button.get_active()

    # only one row selected
    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    assert sut.checkbox_column_button.get_inconsistent()

    for i in range(len(sut.list_store)):
        sut.on_checkbox_toggled(_emitter=None, path=(i,))

    # almost all rows selected (except one)
    assert sut.checkbox_column_button.get_inconsistent()

    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    # all rows selected
    assert not sut.checkbox_column_button.get_inconsistent()
    assert sut.checkbox_column_button.get_active()

    sut.on_checkbox_toggled(_emitter=None, path=(3,))

    # almost all rows selected (except one)
    assert sut.checkbox_column_button.get_inconsistent()

    for i in range(len(sut.list_store)):
        if i == 3:
            continue
        sut.on_checkbox_toggled(_emitter=None, path=(i,))

    # no selected row
    assert not sut.checkbox_column_button.get_inconsistent()
    assert not sut.checkbox_column_button.get_active()


doms = test_qapp_impl().domains
_domains = {vm.name for vm in doms}
_templates = {vm.name for vm in doms if vm.klass == "TemplateVM"}
_standalones = {vm.name for vm in doms if vm.klass == "StandaloneVM"}
_tmpls_and_stndas = _templates.union(_standalones)
_non_derived_qubes = {"dom0"}.union(_tmpls_and_stndas)
_derived_qubes = _domains.difference(_non_derived_qubes)


@patch('subprocess.check_output')
@pytest.mark.parametrize(
    # args: for `qubes-vm-update`
    # selection is based on a result of `qubes-vm-update --dry-run *args`
    # templates_and_standalones: mocked selection of templates and standalones
    # derived_qubes: mocked selection of derived qubes
    # expected_selection: gui should select what
    "args, tmpls_and_stndas, derived_qubes, expected_selection, expected_args",
    (
        # `qubes-update-gui --all`
        # Target all updatable VMs (AdminVM, TemplateVMs and StandaloneVMs)
        pytest.param(
            ('--all', '--force-update'),
            ",".join(_tmpls_and_stndas).encode(),
            ",".join(_derived_qubes).encode(), _non_derived_qubes,
            ('--all', '--force-update'),
            id="all"),
        # `qubes-update-gui --update-if-stale 10`
        # Target all TemplateVMs and StandaloneVMs with known updates or for
        # which last update check was more than <10> days ago.
        pytest.param(
            ('--non-interactive', '--update-if-stale', '10'),
            b'fedora-36', b'', {'fedora-36', 'dom0'},
            ('--update-if-stale', '10'),
            id="if-stale with dom0"),
        pytest.param(
            ('--non-interactive', '--update-if-stale', '10'),
            b'fedora-36', b'', {'fedora-36'},
            ('--update-if-stale', '10'),
            id="if-stale without dom0"),
        # `qubes-update-gui --targets dom0,fedora-36`
        # Comma separated list of VMs to target
        pytest.param(
            ('--targets', 'dom0,fedora-36'), b'fedora-36',
            b'', {'dom0', 'fedora-36'}, ('--targets', 'fedora-36'),
            id="targets"),
        # `qubes-update-gui --standalones`
        # Target all StandaloneVMs
        pytest.param(
            ('--standalones',), b'',
            ",".join(_standalones).encode(), _standalones, ('--standalones',),
            id="standalones"),
        # `qubes-update-gui --dom0`
        # Target dom0
        pytest.param(('--dom0', '--force-update'), b'', b'', {'dom0'},
                     None, id="dom0"),
        # `qubes-update-gui --dom0 --skip dom0`
        # Comma separated list of VMs to be skipped,
        # works with all other options.
        pytest.param(('--dom0', '--skip', 'dom0'), b'', b'', set(), None,
                     id="skip all"),
        # `qubes-update-gui --skip dom0`
        pytest.param(('--skip', 'dom0'), b'', b'', set(), None,
                     id="skip dom0"),
        # `qubes-update-gui --skip garbage-name`
        pytest.param(('--skip', 'garbage-name'),
                     ",".join(_tmpls_and_stndas).encode(),
                     ",".join(_derived_qubes).encode(), _tmpls_and_stndas,
                     ('--skip', 'garbage-name'),
                     id="skip non dom0"),
        # `qubes-update-gui --targets dom0 --skip dom0`
        # the same as `qubes-update-gui --dom0 --skip dom0`
        pytest.param(
            ('--targets', 'dom0', '--skip', 'dom0'), b'', b'', set(),
            None, id="skip all targets"),
        # `qubes-update-gui --templates dom0 --skip fedora-36,garbage-name`
        # expected args are in alphabetical order
        pytest.param(('--templates', '--skip', 'fedora-36,garbage-name'),
                     ",".join(_templates.difference({"fedora-36"})).encode(),
                     b'',
                     _templates.difference({"fedora-36"}),
                     ('--skip', 'fedora-36,garbage-name', '--templates'),
                     id="templates with skip"),
        pytest.param(('--force-update',), b'', b'', set(), None,
                     id="force-update"),
    ),
)
def test_select_rows_ignoring_conditions(
        mock_subprocess,
        args, tmpls_and_stndas, derived_qubes, expected_selection,
        expected_args,
        real_builder, test_qapp, mock_next_button, mock_settings,
        mock_list_store
):
    mock_log = Mock()
    sut = IntroPage(real_builder, mock_log, mock_next_button)

    # populate_vm_list
    sut.list_store = ListWrapper(UpdateRowWrapper, mock_list_store)
    for vm in test_qapp.domains:
        sut.list_store.append_vm(vm)

    assert len(sut.list_store) == 12

    result = b''
    if tmpls_and_stndas:
        result += (b'Following templates and standalones will be updated: '
                   + tmpls_and_stndas)
    if derived_qubes:
        if result:
            result += b'\n'
        result += b'Following qubes will be updated: ' + derived_qubes
    mock_subprocess.return_value = result

    if (expected_args == ('--update-if-stale', '10')
            and expected_selection == {'fedora-36'}):
        test_qapp.expected_calls[
            ('dom0', 'admin.vm.feature.Get', 'last-updates-check', None)] = \
            b'0\x00' + b'3020-01-01 00:00:00'

    cliargs = parse_args(args, test_qapp)
    sut.select_rows_ignoring_conditions(cliargs, test_qapp.domains['dom0'])
    to_update = {row.name for row in sut.list_store if row.selected}

    assert to_update == expected_selection

    if expected_args is None:
        mock_subprocess.assert_not_called()
    else:
        mock_subprocess.assert_called_with(
            ['qubes-vm-update', '--dry-run', '--quiet', *expected_args])


