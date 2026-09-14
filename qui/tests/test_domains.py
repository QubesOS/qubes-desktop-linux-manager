"""Domains widget tests using real GTK menus and mock Qubes objects."""

# pylint: disable=protected-access,redefined-outer-name

import pytest

import qui.tray.domains as domains_widget
from qubesadmin.tests.mock_app import MockDispatcher, MockQube, MockQubes


@pytest.fixture
def widget_factory(monkeypatch):
    """Build menus without registering a desktop application or sending notices."""
    monkeypatch.setattr(domains_widget.DomainTray, "register", lambda self: True)
    monkeypatch.setattr(
        domains_widget.DomainTray, "send_notification", lambda *_args: None
    )
    monkeypatch.setattr(
        domains_widget.DomainTray, "withdraw_notification", lambda *_args: None
    )
    monkeypatch.setattr(domains_widget.GLib, "timeout_add_seconds", lambda *_args: 0)
    monkeypatch.setattr(
        domains_widget.qui.decorators.DomainDecorator,
        "icon",
        lambda self: domains_widget.Gtk.Image(),
    )
    widgets = []

    def create(*, running=True, guivm="dom0", gui="1"):
        qapp = MockQubes()
        qapp._qubes["untrusted"] = MockQube(
            name="untrusted",
            qapp=qapp,
            running=running,
            guivm=guivm,
            features={"gui": gui},
        )
        for mock_vm in qapp._qubes.values():
            mock_vm.features["expert-mode"] = None
            mock_vm.features.setdefault("gui", None)
        qapp.update_vm_calls()
        dispatcher = MockDispatcher(qapp)
        stats_dispatcher = MockDispatcher(qapp, api_method="admin.vm.Stats")
        widget = domains_widget.DomainTray(
            "org.qubes.ui.tray.Domains.test", qapp, dispatcher, stats_dispatcher
        )
        widgets.append(widget)
        widget.widget_icon.set_visible(False)
        widget.initialize_menu()
        return widget

    yield create

    for widget in widgets:
        widget._disconnect_signals(None)
        widget.fullscreen_window_hack.clear_widget()
        widget.tray_menu.destroy()


def assert_actions(widget, visible, debug_visible):
    """Check the displayed actions, including after recursive menu display."""
    item = widget.menu_items[widget.qapp.domains["untrusted"]]
    assert item.get_visible()
    submenu = item.get_submenu()
    assert isinstance(submenu, domains_widget.StartedMenu)
    for _ in range(2):
        for action in (submenu.open_file_manager, submenu.run_terminal):
            assert action.get_visible() is visible
            if visible:
                assert action.get_child().get_visible()
                assert action.label.get_visible()
        assert submenu.debug_console.get_visible() is debug_visible
        widget.tray_menu.show_all()


@pytest.mark.parametrize("running", [True, False], ids=["widget-start", "vm-start"])
@pytest.mark.parametrize(
    "guivm,gui,visible,debug_visible",
    [
        ("dom0", "1", True, False),
        ("dom0", "", False, True),
        ("", "1", False, True),
        ("dom0", None, True, True),
    ],
    ids=["graphical", "gui-disabled", "no-guivm", "gui-unset"],
)
def test_gui_actions_on_start(
    widget_factory, running, guivm, gui, visible, debug_visible, caplog
):
    widget = widget_factory(running=running, guivm=guivm, gui=gui)
    if not running:
        vm = widget.qapp.domains["untrusted"]
        assert not widget.menu_items[vm].get_visible()
        widget.dispatcher.handle("untrusted", "domain-pre-start")
        widget.qapp._qubes["untrusted"].running = True
        widget.qapp.update_vm_calls()
        widget.dispatcher.handle("untrusted", "domain-start")
    assert_actions(widget, visible, debug_visible)
    assert not caplog.records


@pytest.mark.parametrize("event", ["property-set:guivm", "property-reset:guivm"])
def test_gui_actions_on_guivm_change(widget_factory, event, caplog):
    widget = widget_factory()
    assert_actions(widget, True, False)
    mock_vm = widget.qapp._qubes["untrusted"]
    for guivm, visible in [("", False), ("dom0", True)]:
        if event == "property-reset:guivm":
            mock_vm.set_property_default("guivm", guivm)
        else:
            mock_vm.guivm = guivm
        mock_vm.update_calls()
        widget.dispatcher.handle("untrusted", event, name="guivm")
        assert_actions(widget, visible, not visible)
    assert not caplog.records


def test_gui_actions_on_feature_change(widget_factory, caplog):
    widget = widget_factory()
    assert_actions(widget, True, False)
    for gui, event, visible, debug_visible in [
        ("", "domain-feature-set:gui", False, True),
        ("1", "domain-feature-set:gui", True, False),
        ("", "domain-feature-set:gui", False, True),
        (None, "domain-feature-delete:gui", True, True),
    ]:
        widget.qapp._qubes["untrusted"].features["gui"] = gui
        widget.qapp.update_vm_calls()
        widget.dispatcher.handle("untrusted", event, feature="gui")
        assert_actions(widget, visible, debug_visible)
    assert not caplog.records


def test_disconnect_guivm_reset_handler(widget_factory):
    widget = widget_factory()
    widget.emit("shutdown")
    assert not widget.dispatcher.handlers.get("property-reset:guivm")
    # Restore the registrations so fixture cleanup can disconnect them normally.
    widget.register_events()
