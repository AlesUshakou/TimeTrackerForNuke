import os
import sys

# Ensure our src is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import nuke
import timeTracker_ui
import settings_ui

nuke.menu("Nuke").addCommand("TimeTracker/Show Window", "timeTracker_ui.show_window()")
nuke.menu("Nuke").addCommand("TimeTracker/Settings", "settings_ui.show_settings()")
