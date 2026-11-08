"""Updates widget tests using real GTK menus and mock Qubes objects."""

# pylint: disable=protected-access,redefined-outer-name

import pytest

import qui.tray.updates as updates_widget
from qubesadmin.tests.mock_app import MockDispatcher, MockQubes


def set_reboot_required(qapp, value):
    """Set or unset the dom0 feature in the mock app."""
    features = qapp._qubes["dom0"].features
    if value is None:
        features.pop("reboot-required", None)
    else:
        features["reboot-required"] = value
    qapp.update_vm_calls()
    if value is None:
        qapp.expected_calls[
            ("dom0", "admin.vm.feature.Get", "reboot-required", None)
        ] = b"2\x00QubesFeatureNotFoundError\x00\x00reboot-required\x00"


@pytest.fixture
def widget_factory(monkeypatch):
    """Build the widget without registering a desktop application."""
    monkeypatch.setattr(updates_widget.UpdatesTray, "register", lambda self: True)
    monkeypatch.setattr(updates_widget.GLib, "timeout_add_seconds", lambda *_args: 0)
    notifications = []
    monkeypatch.setattr(
        updates_widget.UpdatesTray,
        "send_notification",
        lambda _self, _id, notification: notifications.append(notification),
    )
    widgets = []

    def create(reboot_required=None):
        qapp = MockQubes()
        set_reboot_required(qapp, reboot_required)
        dispatcher = MockDispatcher(qapp)
        widget = updates_widget.UpdatesTray(
            "org.qubes.qui.tray.Updates.test", qapp, dispatcher
        )
        widget.notifications = notifications
        widget.run()
        widgets.append(widget)
        return widget

    yield create

    for widget in widgets:
        widget.fullscreen_window_hack.clear_widget()
        widget.tray_menu.destroy()


def menu_texts(widget):
    widget.tray_menu = updates_widget.Gtk.Menu()
    widget.setup_menu()
    return [item.get_child().get_text() for item in widget.tray_menu.get_children()]


def test_no_reboot_required(widget_factory):
    widget = widget_factory()
    assert not widget.reboot_required
    assert not widget.widget_icon.get_visible()
    assert not menu_texts(widget)


def test_reboot_required_on_start(widget_factory):
    widget = widget_factory(reboot_required="kernel xen-hypervisor")
    assert widget.reboot_required
    assert widget.widget_icon.get_visible()
    assert "restart required" in widget.widget_icon.get_tooltip_text()
    assert menu_texts(widget) == [
        "System restart required!\n"
        "Restart the computer to finish applying dom0 updates."
    ]


def test_reboot_required_on_feature_change(widget_factory):
    widget = widget_factory()

    set_reboot_required(widget.qapp, "kernel")
    widget.dispatcher.handle(
        "dom0",
        "domain-feature-set:reboot-required",
        feature="reboot-required",
        value="kernel",
    )
    assert widget.reboot_required
    assert widget.widget_icon.get_visible()
    assert len(widget.notifications) == 1

    # setting it again does not notify again
    widget.dispatcher.handle(
        "dom0",
        "domain-feature-set:reboot-required",
        feature="reboot-required",
        value="kernel",
    )
    assert len(widget.notifications) == 1

    set_reboot_required(widget.qapp, None)
    widget.dispatcher.handle(
        "dom0",
        "domain-feature-delete:reboot-required",
        feature="reboot-required",
    )
    assert not widget.reboot_required
    assert not widget.widget_icon.get_visible()
    assert "Updates are available" in widget.widget_icon.get_tooltip_text()


def test_reboot_required_ignores_other_qubes(widget_factory):
    widget = widget_factory()
    widget.qapp._qubes["sys-net"].features["reboot-required"] = "1"
    widget.qapp.update_vm_calls()
    widget.dispatcher.handle(
        "sys-net",
        "domain-feature-set:reboot-required",
        feature="reboot-required",
        value="1",
    )
    assert not widget.reboot_required
    assert not widget.widget_icon.get_visible()
    assert not widget.notifications
