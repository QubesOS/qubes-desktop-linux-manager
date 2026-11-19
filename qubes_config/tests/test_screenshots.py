# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2026 Frédéric Pierret <frederic@invisiblethingslab.com>
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
import math
import os
from unittest.mock import patch

import cairo
import pytest

from ..global_config.global_config import GlobalConfig, LOCATIONS

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR")
WIDTH = 1280


@pytest.mark.skipif(not SCREENSHOT_DIR, reason="SCREENSHOT_DIR is not set")
@patch("subprocess.check_output")
@patch("qubes_config.global_config.global_config.show_error")
def test_global_config_screenshots(
    mock_error, mock_subprocess, test_qapp, test_policy_manager, test_builder
):
    assert SCREENSHOT_DIR
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    mock_subprocess.return_value = b""
    # pylint: disable=no-member
    Gtk.IconTheme.get_default().append_search_path(
        os.path.join(os.path.dirname(__file__), "..", "..", "icons", "scalable")
    )
    app = GlobalConfig(test_qapp, test_policy_manager)
    app.perform_setup()
    assert test_builder

    app.main_window.show()
    for widget_name in LOCATIONS:
        app.builder.get_object(widget_name).set_visible(False)

    for page_num in range(app.main_notebook.get_n_pages()):
        page = app.main_notebook.get_nth_page(page_num)
        app.main_notebook.set_current_page(page_num)
        policy = page.get_policy()
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

        allocation = app.main_window.get_allocation()
        allocation.width = WIDTH
        allocation.height = app.main_window.get_preferred_height().minimum_height
        app.main_window.size_allocate(allocation)
        adjustment = page.get_vadjustment()
        allocation.height += max(
            0, math.ceil(adjustment.get_upper() - adjustment.get_page_size())
        )
        app.main_window.size_allocate(allocation)

        surface = cairo.ImageSurface(
            cairo.FORMAT_RGB24, allocation.width, allocation.height
        )
        app.main_window.draw(cairo.Context(surface))
        path = os.path.join(SCREENSHOT_DIR, f"global-config-{page.get_name()}.png")
        surface.write_to_png(path)
        assert os.path.getsize(path) > 0
        page.set_policy(*policy)

    assert not mock_error.called
