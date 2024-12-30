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
"""Tests for widget library"""
# pylint: disable=missing-function-docstring
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ..widgets import gtk_widgets


def test_token_name(test_qapp):
    token_name = gtk_widgets.TokenName("test-blue", test_qapp)

    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, gtk_widgets.QubeName)
    assert child.get_style_context().has_class("qube-box-blue")

    token_name.set_token("@anyvm")
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, Gtk.Label)
    assert not child.get_style_context().has_class("qube-box-blue")
    assert child.get_style_context().has_class("qube-type")

    token_name.set_token("test-red")
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, gtk_widgets.QubeName)
    assert not child.get_style_context().has_class("qube-box-blue")
    assert child.get_style_context().has_class("qube-box-red")


def test_token_name_categories(test_qapp):
    token_name = gtk_widgets.TokenName("@anyvm", test_qapp, {"@anyvm": "Any"})
    assert len(token_name.get_children()) == 1
    child = token_name.get_children()[0]
    assert isinstance(child, Gtk.Label)
    assert child.get_text() == "Any"


def test_qube_name(test_qapp):
    # missing name
    qube_name = gtk_widgets.QubeName(None)
    assert qube_name.label.get_text() == "None"
    assert qube_name.get_style_context().has_class("qube-box-black")
    assert qube_name.get_style_context().has_class("qube-box-base")

    vm = test_qapp.domains["test-red"]
    qube_name = gtk_widgets.QubeName(vm)
    assert qube_name.label.get_text() == "test-red"
    assert qube_name.get_style_context().has_class("qube-box-red")
    assert qube_name.get_style_context().has_class("qube-box-base")


def test_text_modeler_simple():
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox, values={"Pretty": 1, "Ugly": 2}
    )

    # expected initial setup
    assert combobox.get_active_text() == "Pretty"

    # select second value in combobox
    combobox.set_active(1)
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() == 2
    assert text_modeler.is_changed()

    # reset to initial settings
    text_modeler.reset()
    assert combobox.get_active_text() == "Pretty"
    assert text_modeler.get_selected() == 1
    assert not text_modeler.is_changed()

    # select second value via TextModeler
    text_modeler.select_value(2)
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() == 2
    assert text_modeler.is_changed()

    # mark changes as saved
    text_modeler.update_initial()
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() == 2
    assert not text_modeler.is_changed()


def test_text_modeler_none():
    """Check if there is no strangeness if one of the values is None"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox, values={"Pretty": 1, "Ugly": None}
    )

    # none will be selected as initial value if nothing else is provided
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # select second value in combobox
    combobox.set_active(0)
    assert combobox.get_active_text() == "Pretty"
    assert text_modeler.get_selected() == 1
    assert text_modeler.is_changed()

    # reset to initial settings
    text_modeler.reset()
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # select values via TextModeler
    text_modeler.select_value(1)
    assert combobox.get_active_text() == "Pretty"
    assert text_modeler.get_selected() == 1
    assert text_modeler.is_changed()

    text_modeler.select_value(None)
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()

    # mark changes as saved
    text_modeler.update_initial()
    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()


def test_text_modeler_missing():
    """Initial value is not in values set"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values={"Good": 1, "Ugly": 2, "Bad": 3},
        selected_value="Very Strange",
    )

    assert combobox.get_active_text() == "Very Strange"
    assert text_modeler.get_selected() == "Very Strange"
    assert not text_modeler.is_changed()


def test_text_modeler_initial():
    """Initial value is set"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values={"Good": 1, "Ugly": 2, "Bad": 3},
        selected_value=2,
    )

    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() == 2
    assert not text_modeler.is_changed()


def test_text_modeler_initial_none():
    """Initial value corresponding to None is set"""
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values={"Pretty": 1, "Ugly": None},
        selected_value=None,
    )

    assert combobox.get_active_text() == "Ugly"
    assert text_modeler.get_selected() is None
    assert not text_modeler.is_changed()


def test_text_modeler_style_changes():
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values={"Good": 1, "Ugly": 2, "Bad": 3},
        selected_value=1,
        style_changes=True,
    )

    assert not combobox.get_style_context().has_class("combo-changed")

    # change selected value manually
    combobox.set_active(2)
    assert combobox.get_style_context().has_class("combo-changed")

    # and back to initial
    combobox.set_active(0)
    assert not combobox.get_style_context().has_class("combo-changed")

    # change selected value with modeler
    text_modeler.select_value(2)
    assert combobox.get_style_context().has_class("combo-changed")

    # and reset
    text_modeler.reset()
    assert not combobox.get_style_context().has_class("combo-changed")


def test_text_modeler_style_changes_none_val():
    combobox = Gtk.ComboBoxText()

    text_modeler = gtk_widgets.TextModeler(
        combobox=combobox,
        values={"Good": 1, "Ugly": None, "Bad": 3},
        selected_value=None,
        style_changes=True,
    )

    assert not combobox.get_style_context().has_class("combo-changed")

    # change selected value manually
    combobox.set_active(2)
    assert combobox.get_style_context().has_class("combo-changed")

    # and back to initial
    combobox.set_active(1)
    assert not combobox.get_style_context().has_class("combo-changed")

    # change selected value with modeler
    text_modeler.select_value(3)
    assert combobox.get_style_context().has_class("combo-changed")

    # and reset
    text_modeler.reset()
    assert not combobox.get_style_context().has_class("combo-changed")

    # change selected value with modeler v 2
    text_modeler.select_value(3)
    assert combobox.get_style_context().has_class("combo-changed")
    text_modeler.select_value(None)
    assert not combobox.get_style_context().has_class("combo-changed")


#######################
### VMModeler tests ###
#######################


def get_selected_text(combobox: Gtk.ComboBox, col_no: int = 1):
    tree_iter = combobox.get_active_iter()
    model = combobox.get_model()
    # in VMListModeler 0 is row numer, 1 is readable name,
    # 2 is pixbuf, 3 is api_name
    return model[tree_iter][col_no]


#### initial params


def test_vmmodeler_simple(test_qapp):
    """simplest vm modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
    )

    assert get_selected_text(combobox) is not None


def test_vmmodeler_selected(test_qapp):
    """simplest vm modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    initial_vm = test_qapp.domains["test-vm"]
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value=initial_vm,
    )

    assert get_selected_text(combobox) == "test-vm"


def test_vmmodeler_default(test_qapp):
    """simplest vm modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    default_vm = test_qapp.domains["test-blue"]
    _ = gtk_widgets.VMListModeler(
        combobox=combobox, qapp=test_qapp, default_value=default_vm
    )

    assert get_selected_text(combobox) == "test-blue (default)"


def test_vmmodeler_default_none(test_qapp):
    """simplest vm modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        default_value="None",
        additional_options=gtk_widgets.NONE_CATEGORY,
    )

    assert get_selected_text(combobox) == "(none) (default)"


def test_vmmodeler_default_current(test_qapp):
    """simplest vm modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    initial_vm = test_qapp.domains["test-vm"]
    default_vm = test_qapp.domains["test-blue"]
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value=initial_vm,
        default_value=default_vm,
    )

    assert get_selected_text(combobox) == "test-vm"
    found = False
    model = combobox.get_model()
    for item in model:
        if item[1] == "test-blue (default)":
            found = True
    assert found


def test_vmmodeler_filter(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    vms = ["test-vm", "test-blue", "test-red"]
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        filter_function=lambda vm: str(vm) in vms,
    )

    selected_vms = []
    model = combobox.get_model()
    for item in model:
        selected_vms.append(item[1])

    assert sorted(selected_vms) == sorted(vms)


def test_vmmodeler_categories_none(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    _ = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        additional_options=gtk_widgets.NONE_CATEGORY,
    )

    assert get_selected_text(combobox) == "(none)"


def test_vmmodeler_current_not_found(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox, qapp=test_qapp, current_value="RandomText"
    )

    assert get_selected_text(combobox) == "RandomText"
    assert modeler.get_selected() == "RandomText"


def test_vmmodeler_str(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    vm = test_qapp.domains["test-blue"]
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="RandomText",
        default_value=vm,
        additional_options=gtk_widgets.NONE_CATEGORY,
    )

    assert str(modeler) == "RandomText"
    modeler.select_value("test-blue")
    assert str(modeler) == "test-blue (default)"
    modeler.select_value("None")
    assert str(modeler) == "(none)"


def test_vmmodeler_simple_actions(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox, qapp=test_qapp, current_value="test-vm"
    )

    vm = test_qapp.domains["test-vm"]
    other_vm = test_qapp.domains["test-blue"]

    # expected initial setup
    assert combobox.get_child().get_text() == "test-vm"
    assert get_selected_text(combobox) == "test-vm"
    assert modeler.get_selected() == vm
    assert not modeler.is_changed()

    # select something else
    modeler.select_value("test-blue")
    assert combobox.get_child().get_text() == "test-blue"
    assert get_selected_text(combobox) == "test-blue"
    assert modeler.get_selected() == other_vm
    assert modeler.is_changed()

    # and reset
    modeler.reset()
    assert combobox.get_child().get_text() == "test-vm"
    assert get_selected_text(combobox) == "test-vm"
    assert modeler.get_selected() == vm
    assert not modeler.is_changed()

    # select something manually
    combobox.set_active(combobox.get_active() + 1)
    assert modeler.is_changed()

    # and back to start
    modeler.select_value("test-vm")
    assert combobox.get_child().get_text() == "test-vm"
    assert get_selected_text(combobox) == "test-vm"
    assert modeler.get_selected() == vm
    assert not modeler.is_changed()

    # select and save changes
    modeler.select_value("test-blue")
    modeler.update_initial()
    assert combobox.get_child().get_text() == "test-blue"
    assert get_selected_text(combobox) == "test-blue"
    assert modeler.get_selected() == other_vm
    assert not modeler.is_changed()


def test_vmmodeler_actions_complex(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    additional_categories = gtk_widgets.NONE_CATEGORY.copy()
    additional_categories["@anyvm"] = "Any Qube"
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="@anyvm",
        additional_options=additional_categories,
    )

    vm = test_qapp.domains["test-vm"]

    # expected initial setup
    assert get_selected_text(combobox) == "Any Qube"
    assert modeler.get_selected() == "@anyvm"
    assert not modeler.is_changed()

    # select something else
    modeler.select_value("test-vm")
    assert get_selected_text(combobox) == "test-vm"
    assert modeler.get_selected() == vm
    assert modeler.is_changed()

    # select none
    modeler.select_value("None")
    assert get_selected_text(combobox) == "(none)"
    assert modeler.get_selected() is None
    assert modeler.is_changed()

    modeler.update_initial()
    assert not modeler.is_changed()


def test_modeler_style_changes(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    entry_box = combobox.get_child()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="test-vm",
        style_changes=True,
    )

    # switch selection back and forth
    assert not entry_box.get_style_context().has_class("combo-changed")
    modeler.select_value("test-blue")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.select_value("test-vm")
    assert not entry_box.get_style_context().has_class("combo-changed")

    # switch and reset
    modeler.select_value("test-blue")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.reset()
    assert not entry_box.get_style_context().has_class("combo-changed")

    # switch and update initial
    modeler.select_value("test-blue")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.update_initial()
    assert not entry_box.get_style_context().has_class("combo-changed")


def test_modeler_change_callback(test_qapp):
    counter = []

    def incr(*_args):
        counter.append(1)

    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="test-vm",
        event_callback=incr,
    )

    assert counter
    counter.clear()
    modeler.select_value("test-blue")
    assert counter


def test_modeler_change_callback_later(test_qapp):
    counter = []

    def incr(*_args):
        counter.append(1)

    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="test-vm",
    )

    assert not counter
    modeler.connect_change_callback(incr)
    assert not counter
    modeler.select_value("test-blue")
    assert counter


def test_modeler_input_test(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    entry_box: Gtk.Entry = combobox.get_child()
    modeler = gtk_widgets.VMListModeler(
        combobox=combobox,
        qapp=test_qapp,
        current_value="test-vm",
    )

    entry_box.set_text("test-blue")
    assert modeler.get_selected() == test_qapp.domains["test-blue"]

    entry_box.set_text("test")
    assert modeler.get_selected() is None


def test_modeler_is_available(test_qapp):
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    vms = [test_qapp.domains["test-vm"], test_qapp.domains["test-blue"]]
    other_vms = [test_qapp.domains["test-red"]]

    vm_modeler = gtk_widgets.VMListModeler(
        combobox=combobox, qapp=test_qapp, filter_function=lambda vm: vm in vms
    )

    for vm in vms:
        assert vm_modeler.is_vm_available(vm)
    for vm in other_vms:
        assert not vm_modeler.is_vm_available(vm)


########################
### Image List tests ###
########################

#### initial params


def test_imagemodeler_simple():
    """simplest image modeler: no special params, just check it does not error
    out"""
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    _ = gtk_widgets.ImageListModeler(
        combobox=combobox, value_list={"1": {"icon": "test", "object": None}}
    )

    assert get_selected_text(combobox, 0) is not None


def test_imagemodeler_selected():
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    _ = gtk_widgets.ImageListModeler(
        combobox=combobox,
        value_list={
            "a": {"icon": "test", "object": 1},
            "b": {"icon": "test", "object": 2},
        },
        selected_value="b",
    )

    assert get_selected_text(combobox, 0) == "b"


def test_imagemodeler_simple_actions():
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()

    modeler = gtk_widgets.ImageListModeler(
        combobox=combobox,
        value_list={
            "a": {"icon": "test", "object": 1},
            "b": {"icon": "test", "object": 2},
            "c": {"icon": "test", "object": 3},
        },
        selected_value="b",
    )

    # expected initial setup
    assert combobox.get_active_id() == "b"
    assert get_selected_text(combobox, 0) == "b"
    assert modeler.get_selected() == 2
    assert not modeler.is_changed()

    # select something else
    modeler.select_name("c")
    assert combobox.get_active_id() == "c"
    assert get_selected_text(combobox, 0) == "c"
    assert modeler.get_selected() == 3
    assert modeler.is_changed()

    # and reset
    modeler.reset()
    assert combobox.get_active_id() == "b"
    assert get_selected_text(combobox, 0) == "b"
    assert modeler.get_selected() == 2
    assert not modeler.is_changed()

    # select something manually
    combobox.set_active(combobox.get_active() + 1)
    assert modeler.is_changed()

    # and back to start
    modeler.select_name("b")
    assert combobox.get_active_id() == "b"
    assert get_selected_text(combobox, 0) == "b"
    assert modeler.get_selected() == 2
    assert not modeler.is_changed()

    # select and save changes
    modeler.select_name("c")
    modeler.update_initial()
    assert combobox.get_active_id() == "c"
    assert get_selected_text(combobox, 0) == "c"
    assert modeler.get_selected() == 3
    assert not modeler.is_changed()


def test_imagemodeler_style_changes():
    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    entry_box = combobox.get_child()
    modeler = gtk_widgets.ImageListModeler(
        combobox=combobox,
        value_list={
            "a": {"icon": "test", "object": 1},
            "b": {"icon": "test", "object": 2},
            "c": {"icon": "test", "object": 3},
        },
        selected_value="b",
        style_changes=True,
    )

    # switch selection back and forth
    assert not entry_box.get_style_context().has_class("combo-changed")
    modeler.select_name("c")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.select_name("b")
    assert not entry_box.get_style_context().has_class("combo-changed")

    # switch and reset
    modeler.select_name("c")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.reset()
    assert not entry_box.get_style_context().has_class("combo-changed")

    # switch and update initial
    modeler.select_name("c")
    assert entry_box.get_style_context().has_class("combo-changed")
    modeler.update_initial()
    assert not entry_box.get_style_context().has_class("combo-changed")


def test_imagemodeler_change_callback():
    counter = []

    def incr(*_args):
        counter.append(1)

    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.ImageListModeler(
        combobox=combobox,
        value_list={
            "a": {"icon": "test", "object": 1},
            "b": {"icon": "test", "object": 2},
            "c": {"icon": "test", "object": 3},
        },
        selected_value="a",
        event_callback=incr,
    )

    assert counter
    counter.clear()
    modeler.select_name("c")
    assert counter


def test_imagemodeler_change_callback_later():
    counter = []

    def incr(*_args):
        counter.append(1)

    combobox: Gtk.ComboBox = Gtk.ComboBox.new_with_entry()
    modeler = gtk_widgets.ImageListModeler(
        combobox=combobox,
        value_list={
            "a": {"icon": "test", "object": 1},
            "b": {"icon": "test", "object": 2},
            "c": {"icon": "test", "object": 3},
        },
        selected_value="a",
    )

    assert not counter
    modeler.connect_change_callback(incr)
    assert not counter
    modeler.select_name("c")
    assert counter


#### ImageTextButton


def test_imagetextbutton():
    clicks = []
    button = gtk_widgets.ImageTextButton(
        "icon",
        "label",
        click_function=lambda *args: clicks.append(1),
        style_classes=["a_class"],
    )

    assert button.get_style_context().has_class("a_class")
    assert not clicks
    button.clicked()
    assert len(clicks) == 1

    # button contains two objects, label and image
    assert len(button.get_child().get_children()) == 2

    button_without_label = gtk_widgets.ImageTextButton("icon", None)
    # button contains just image
    assert len(button_without_label.get_child().get_children()) == 1

    insensitive_button = gtk_widgets.ImageTextButton("icon", "text")
    assert not insensitive_button.get_sensitive()
