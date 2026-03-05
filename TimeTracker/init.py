import os
import sys

# Ensure our src is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import nuke
import timeTracker


def _tt_any_knob_changed(*args, **kwargs):
    timeTracker.mark_activity()


def _tt_user_create(*args, **kwargs):
    timeTracker.mark_activity()


def _tt_user_delete(*args, **kwargs):
    timeTracker.mark_activity()

def _tt_on_render_abort():
    import timeTracker
    timeTracker.on_render_abort()

for name in ("addOnRenderAbort", "addOnRenderCancelled", "addOnRenderCancel"):
    try:
        getattr(nuke, name)(_tt_on_render_abort)
    except Exception:
        pass

# activity
nuke.addKnobChanged(_tt_any_knob_changed)
nuke.addOnUserCreate(_tt_user_create)
nuke.addOnDestroy(_tt_user_delete)

# render
nuke.addBeforeRender(timeTracker.on_before_render)
nuke.addAfterRender(timeTracker.on_after_render)

# script lifecycle
nuke.addOnScriptLoad(timeTracker.start_session)
nuke.addOnScriptSave(timeTracker.on_script_save)
nuke.addOnScriptClose(timeTracker.on_script_close)
