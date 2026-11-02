"""Domains widget tests using real GTK menus and mock Qubes objects."""

# pylint: disable=protected-access,redefined-outer-name

import pytest

import qui.tray.domains as domains_widget
from qubesadmin.tests.mock_app import MockDispatcher, MockQube, MockQubes, Property


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
        if gui is not None:
            widget.dispatcher.handle("untrusted", event, feature="gui", value=gui)
        else:
            widget.dispatcher.handle("untrusted", event, feature="gui")
        assert_actions(widget, visible, debug_visible)
    assert not caplog.records


def test_disconnect_guivm_reset_handler(widget_factory):
    widget = widget_factory()
    widget.emit("shutdown")
    assert not widget.dispatcher.handlers.get("property-reset:guivm")
    # Restore the registrations so fixture cleanup can disconnect them normally.
    widget.register_events()


def global_property_calls(widget):
    return [
        call
        for call in widget.qapp.actual_calls
        if call[1] in ("admin.property.Get", "admin.property.GetAll")
    ]


def set_maxmem(widget, response=None, value="16000"):
    """Make the global maxmem property available, or answer its requests
    with *response*"""
    qapp = widget.qapp
    if response is None:
        qapp._global_properties["maxmem"] = Property(value, "int", True)
        qapp.update_global_properties()
    else:
        qapp.expected_calls[("dom0", "admin.property.GetAll", None, None)] = response
        qapp.expected_calls[("dom0", "admin.property.Get", "maxmem", None)] = response


def send_stats(widget, vm_name, memory_kb, assigned_total=None):
    """Send a vm-stats event, without the new memory keys if
    *assigned_total* is None (like an older dom0 does)."""
    kwargs = {"memory_kb": memory_kb, "cpu_usage": 1}
    if assigned_total is not None:
        kwargs.update(
            memory_assigned_total=assigned_total,
            memory_assigned_usable=memory_kb,
            memory_with_swap_used=memory_kb,
        )
    widget.stats_dispatcher.handle(vm_name, "vm-stats", **kwargs)


def shutdown(widget, vm_name):
    widget.qapp._qubes[vm_name].running = False
    widget.qapp.update_vm_calls()
    widget.dispatcher.handle(vm_name, "domain-shutdown")


def test_memory_summary_hidden_without_new_stats(widget_factory, caplog):
    widget = widget_factory()
    assert not widget.memory_summary.get_visible()
    send_stats(widget, "dom0", 4096000)
    send_stats(widget, "untrusted", 409600)
    assert not widget.memory_summary.get_visible()
    assert not global_property_calls(widget)
    # existing per-qube column still updated
    item = widget.menu_items[widget.qapp.domains["untrusted"]]
    assert item.memory.mem_label.get_text() == "400 MiB"
    assert not caplog.records


def test_memory_summary(widget_factory, caplog):
    widget = widget_factory()
    set_maxmem(widget)
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    send_stats(widget, "sys-net", 409600, assigned_total=410624)
    send_stats(widget, "untrusted", 409600, assigned_total=1024000)
    calls = global_property_calls(widget)
    assert calls
    # stats are sent periodically, the latest value replaces the previous one
    send_stats(widget, "untrusted", 409600, assigned_total=1638400)

    summary = widget.memory_summary
    assert summary.get_visible()
    assert summary.memory_label.get_text() == "6002 / 16000 MiB"
    assert summary.percentage_label.get_text() == "37.5%"
    assert summary.level_bar.get_visible()
    assert summary.level_bar.get_value() == pytest.approx(37.51, abs=0.01)
    tooltip = summary.get_tooltip_markup()
    assert "Not assigned to any qube: <b>9998 MiB</b>" in tooltip
    assert "Used by qubes (incl. swap; self-reported): <b>4800 MiB</b>" in tooltip
    # maxmem cannot change, so it is fetched only once
    assert global_property_calls(widget) == calls

    shutdown(widget, "untrusted")
    assert summary.memory_label.get_text() == "4402 / 16000 MiB"
    # late stats of a qube that is already halted are ignored
    send_stats(widget, "untrusted", 409600, assigned_total=1638400)
    assert summary.memory_label.get_text() == "4402 / 16000 MiB"

    # menu is shown again, the summary must stay in sync
    widget.tray_menu.show_all()
    shutdown(widget, "sys-net")
    widget.dispatcher.handle(None, "domain-delete", vm="dom0")
    assert not summary.get_visible()
    widget.tray_menu.show_all()
    assert not summary.get_visible()
    assert not caplog.records


@pytest.mark.parametrize(
    "response",
    [
        b"",  # calls denied by policy
        None,  # older dom0, no global maxmem property
    ],
    ids=["denied", "missing"],
)
def test_memory_summary_without_maxmem(widget_factory, response, caplog):
    widget = widget_factory()
    if response is not None:
        set_maxmem(widget, response)
    else:
        widget.qapp.update_global_properties()
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    calls = global_property_calls(widget)
    send_stats(widget, "untrusted", 409600, assigned_total=410624)
    summary = widget.memory_summary
    assert summary.get_visible()
    assert summary.memory_label.get_text() == "4402 MiB"
    assert not summary.level_bar.get_visible()
    assert not summary.percentage_label.get_visible()
    widget.tray_menu.show_all()
    assert not summary.level_bar.get_visible()
    assert global_property_calls(widget) == calls
    assert not caplog.records


def test_memory_summary_position(widget_factory):
    widget = widget_factory()
    set_maxmem(widget)
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    children = widget.tray_menu.get_children()
    position = children.index(widget.memory_summary)
    # after all qubes, before the separator and Qube Manager entry
    assert all(hasattr(child, "vm") for child in children[:position])
    assert isinstance(children[position + 1], domains_widget.Gtk.SeparatorMenuItem)


def test_memory_history(widget_factory, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(domains_widget.time, "monotonic", lambda: clock[0])
    widget = widget_factory()
    set_maxmem(widget)
    summary = widget.memory_summary
    assert isinstance(summary.get_submenu(), domains_widget.Gtk.Menu)

    # stats of all qubes in one round give one point
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    send_stats(widget, "untrusted", 409600, assigned_total=1024000)
    # memory_with_swap_used is memory_kb in send_stats()
    assert summary.graph.samples == [(1000.0, 5121024, 4505600)]

    clock[0] += 3
    send_stats(widget, "untrusted", 819200, assigned_total=2048000)
    assert summary.graph.samples == [
        (1000.0, 5121024, 4505600),
        (1003.0, 6145024, 4915200),
    ]

    # older points are dropped
    clock[0] += domains_widget.MEMORY_HISTORY_SECONDS - 1
    send_stats(widget, "untrusted", 409600, assigned_total=1024000)
    assert [sample[1:] for sample in summary.graph.samples] == [
        (6145024, 4915200),
        (5121024, 4505600),
    ]


@pytest.mark.parametrize("maxmem", [True, False])
def test_memory_graph_draw(widget_factory, maxmem):
    cairo = pytest.importorskip("cairo")
    widget = widget_factory()
    if maxmem:
        set_maxmem(widget)
    else:
        widget.qapp.update_global_properties()
    graph = widget.memory_summary.graph
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 300, 120)
    # called directly, as exceptions in GTK signal handlers are only printed
    graph._draw(graph, cairo.Context(surface))
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    send_stats(widget, "untrusted", 409600, assigned_total=1024000)
    graph._draw(graph, cairo.Context(surface))


@pytest.mark.parametrize(
    "low, high, expected",
    [
        (3700, 3988, [3700, 3800, 3900, 4000]),
        (3843.5, 3988.2, [3800, 3850, 3900, 3950, 4000]),
        (100, 4095, [0, 1000, 2000, 3000, 4000, 5000]),
        # flat line
        (3988, 3988, [3970, 3980, 3990, 4000, 4010]),
        (0, 0, [0, 10, 20, 30]),
    ],
)
def test_memory_graph_ticks(low, high, expected):
    assert domains_widget.memory_graph_ticks(low, high) == expected


def test_memory_forgotten_on_domain_stopped(widget_factory):
    widget = widget_factory()
    set_maxmem(widget)
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    send_stats(widget, "untrusted", 409600, assigned_total=1024000)
    # qmemman gives the memory of the stopped qube to the other ones before
    # domain-shutdown arrives
    widget.dispatcher.handle("untrusted", "domain-stopped")
    send_stats(widget, "dom0", 4096000, assigned_total=5121024)
    assert widget.memory_summary.memory_label.get_text() == "5001 / 16000 MiB"
