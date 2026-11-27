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


def send_stats(
    widget, vm_name, memory_kb, assigned_total=None, used=None, swap=None, **kwargs
):
    """Send a vm-stats event, without the new memory keys if
    *assigned_total* is None (like an older dom0 does). *used* defaults to
    *memory_kb* (a qube that does not report its memory)."""
    kwargs.update(memory_kb=memory_kb, cpu_usage=1)
    if assigned_total is not None:
        kwargs.update(
            memory_assigned_total=assigned_total,
            memory_assigned_usable=memory_kb,
            memory_with_swap_used=memory_kb if used is None else used,
            cpu_time=1000,
            online_vcpus=2,
        )
        if swap is not None:
            kwargs["swap_used"] = swap
    widget.stats_dispatcher.handle(vm_name, "vm-stats", **kwargs)


def send_round(widget, available="8192000"):
    """Stats of dom0 (with free memory) and untrusted"""
    send_stats(
        widget,
        "dom0",
        4096000,
        assigned_total=4097024,
        used=1024000,
        swap=0,
        memory_available=available,
    )
    send_stats(
        widget, "untrusted", 1024000, assigned_total=1025024, used=512000, swap=0
    )


def test_memory_summary_hidden_without_new_stats(widget_factory, caplog):
    """Older dom0: no summary, per-qube RAM as before and no RAM%."""
    widget = widget_factory()
    assert not widget.memory_summary.get_visible()
    send_stats(widget, "dom0", 4096000)
    send_stats(widget, "untrusted", 409600)
    assert not widget.memory_summary.get_visible()
    assert not global_property_calls(widget)
    item = widget.menu_items[widget.qapp.domains["untrusted"]]
    assert item.memory.mem_label.get_text() == "400 MiB"
    assert item.memory.percent_label.get_text() == "-"
    assert not caplog.records


def test_memory_summary_hidden_without_memory_available(widget_factory):
    """dom0 without memory_available: no summary."""
    widget = widget_factory()
    set_maxmem(widget)
    send_stats(widget, "dom0", 4096000, assigned_total=4097024)
    assert not widget.memory_summary.get_visible()


def test_memory_summary(widget_factory, caplog):
    """Free memory in MiB and percent of the system memory, totals in the tooltip."""
    widget = widget_factory()
    set_maxmem(widget)
    send_round(widget)
    summary = widget.memory_summary
    assert summary.get_visible()
    assert summary.memory_label.get_text() == "8000 MiB (50%)"
    tooltip = summary.get_tooltip_markup()
    assert "Free memory: <b>8000 MiB</b>" in tooltip
    assert "Assigned to running qubes: <b>5002 MiB</b>" in tooltip
    assert "Used by running qubes: <b>1500 MiB</b>" in tooltip
    assert "Total system memory: <b>16000 MiB</b>" in tooltip

    send_round(widget, available="4096000")
    assert summary.memory_label.get_text() == "4000 MiB (25%)"
    # the summary keeps its own visibility when the menu is shown again
    widget.tray_menu.show_all()
    assert summary.get_visible()
    assert not caplog.records


@pytest.mark.parametrize(
    "response",
    [
        b"",  # calls denied by policy
        None,  # no global maxmem property
    ],
    ids=["denied", "missing"],
)
def test_memory_summary_without_maxmem(widget_factory, response, caplog):
    """Without the system memory, only the free MiB are shown."""
    widget = widget_factory()
    if response is not None:
        set_maxmem(widget, response)
    else:
        widget.qapp.update_global_properties()
    send_round(widget)
    summary = widget.memory_summary
    assert summary.get_visible()
    assert summary.memory_label.get_text() == "8000 MiB"
    assert "Total system memory" not in summary.get_tooltip_markup()
    assert not caplog.records


def test_memory_summary_position(widget_factory):
    """The summary is after the qubes, before the separator."""
    widget = widget_factory()
    set_maxmem(widget)
    send_round(widget)
    children = widget.tray_menu.get_children()
    position = children.index(widget.memory_summary)
    assert all(hasattr(child, "vm") for child in children[:position])
    assert isinstance(children[position + 1], domains_widget.Gtk.SeparatorMenuItem)


def test_memory_summary_drops_stopped_qube(widget_factory):
    """A stopped qube no longer counts, and its late stats are ignored."""
    widget = widget_factory()
    set_maxmem(widget)
    send_round(widget)
    widget.dispatcher.handle("untrusted", "domain-stopped")
    assert "Assigned to running qubes: <b>4001 MiB</b>" in (
        widget.memory_summary.get_tooltip_markup()
    )
    send_stats(widget, "untrusted", 1024000, assigned_total=1025024)
    send_stats(widget, "dom0", 4096000, assigned_total=4097024, memory_available="1")
    assert "Assigned to running qubes: <b>4001 MiB</b>" in (
        widget.memory_summary.get_tooltip_markup()
    )


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"memory_assigned_usable": "1000", "memory_with_swap_used": "600",
          "swap_used": "100"}, 50),
        # meminfo but no swapinfo (older agent)
        ({"memory_assigned_usable": "1000", "memory_with_swap_used": "600"}, 60),
        # no meminfo: dom0 sends the usable memory
        ({"memory_assigned_usable": "1000", "memory_with_swap_used": "1000"}, None),
        # older dom0
        ({"memory_kb": "1000"}, None),
        ({"memory_assigned_usable": "0", "memory_with_swap_used": "600",
          "swap_used": "0"}, None),
    ],
)  # fmt: skip
def test_memory_used_percent(kwargs, expected):
    """Used memory in percent of the usable memory, when the qube reports it."""
    assert domains_widget.memory_used_percent(kwargs) == expected


def test_memory_used_percent_column(widget_factory):
    """The per-qube RAM% column shows the used part of the usable memory."""
    widget = widget_factory()
    send_round(widget)
    item = widget.menu_items[widget.qapp.domains["untrusted"]]
    assert item.memory.mem_label.get_text() == "1000 MiB"
    assert item.memory.percent_label.get_text() == "50%"


def test_memory_graph_segments():
    """Samples are split at gaps; recent last values extend to now."""
    samples = [(1000.0, 1024, 512), (1003.0, 1024, 512), (1006.0, 1024, 512)]
    samples.append((1006.0 + domains_widget.MEMORY_GAP_SECONDS + 3, 2048, 1024))
    now = samples[-1][0] + 3
    segments = domains_widget.MemoryGraph._segments(samples, now)
    assert [[sample[0] for sample in segment] for segment in segments] == [
        [1000.0, 1003.0, 1006.0],
        [1039.0, 1042.0],
    ]
    now += domains_widget.MEMORY_GAP_SECONDS + 1
    assert domains_widget.MemoryGraph._segments(samples, now)[-1] == [
        (1039.0, 2048, 1024)
    ]


def test_memory_graph_y_range(widget_factory):
    """With the system memory, the y axis goes from 0 to it."""
    widget = widget_factory()
    graph = widget.memory_summary.graph
    widget.qapp.update_global_properties()
    send_round(widget)
    ticks, top = graph._y_range(graph._samples())
    assert top == ticks[-1] and ticks[0] > 0

    widget = widget_factory()
    set_maxmem(widget)
    graph = widget.memory_summary.graph
    send_round(widget)
    assert graph._y_range(graph._samples()) == (
        [0, 5000, 10000, 16000],
        16000,
    )


@pytest.mark.parametrize("maxmem", [True, False])
def test_memory_graph_draw(widget_factory, maxmem):
    """The graph draws the filled areas up to now."""
    cairo = pytest.importorskip("cairo")
    widget = widget_factory()
    if maxmem:
        set_maxmem(widget)
    else:
        widget.qapp.update_global_properties()
    graph = widget.memory_summary.graph
    clock = [1000.0]
    widget.stats_monitor.clock = lambda: clock[0]
    # two minutes of stats, every 3 seconds
    for _ in range(40):
        send_round(widget)
        clock[0] += 3
    window = domains_widget.Gtk.OffscreenWindow()
    graph.get_parent().remove(graph)
    window.add(graph)
    window.show_all()
    while domains_widget.Gtk.events_pending():
        domains_widget.Gtk.main_iteration()
    width = graph.get_allocated_width()
    height = graph.get_allocated_height()
    assert (width, height) == (320, 160)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    # called directly, as exceptions in GTK signal handlers are only printed
    graph._draw(graph, cairo.Context(surface))
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()

    def drawn_pixels(x):
        return sum(1 for y in range(height) if data[y * stride + x * 4 + 3])

    assert drawn_pixels(width - 30) > drawn_pixels(width // 2) + 10
    window.destroy()


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
    """Round y-axis ticks covering low to high."""
    assert domains_widget.memory_graph_ticks(low, high) == expected
