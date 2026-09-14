"""Initialize the tray's GTK backend before other tests start GTK threads."""

# This module must load before GTK initialization in nested conftest files.
from qui.tray import gtk3_xwayland_menu_dismisser  # pylint: disable=unused-import
