# timeTracker.py
# Core time tracking logic for Nuke.

from __future__ import annotations

import os
import json
import time
import base64
import hashlib
import hmac
import re
import platform
import nuke

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtWidgets

from settings import get_ttk_dir, is_ales_on

__version__ = "v1.02"


_TIMETRACKER_KEY = "Ales_Ushakou_Internal_Key_2026"
_TIMETRACKER_SALT = "Ales_Ushakou_Salt_2026"

DATA_FILE_TEMPLATE = "timetracker_{shot}.enc"

# --- runtime knobs ---
IDLE_TIMEOUT_SEC = 20          # if no activity for >20s => idle
TICK_INTERVAL_MS = 1000        # tick interval
AUTOSAVE_MODE = "minute"       # "save" or "minute"
AUTOSAVE_INTERVAL_SEC = 60


# -------------------------
# Helpers: shot + paths
# -------------------------

def _script_path() -> str:
    try:
        r = nuke.root()
        return r["name"].value()
    except Exception:
        return ""


def _is_script_saved() -> bool:
    try:
        r = nuke.root()
        p = _script_path()
        return (r.name() != "Root") and bool(p) and (p != "Root")
    except Exception:
        return False


def get_shot_name() -> str:
    """Shot name from .nk filename, ignoring version tokens like _v001.

    Examples:
        SH010_v001 -> SH010
        SH010_v001_comp -> SH010_comp
    """
    if not _is_script_saved():
        return "UNSAVED"

    name = os.path.splitext(os.path.basename(_script_path()))[0].strip()
    if not name:
        return "UNKNOWN_SHOT"

    # Remove version token "v###" if it appears as a standalone segment (start or between underscores).
    # This keeps suffixes like "_comp" while grouping all versions into one shot.
    name = re.sub(r"(?i)(?:^|_)v\d{2,4}(?=_|$)", "", name)

    # Cleanup repeated/edge underscores after removal
    name = re.sub(r"_+", "_", name).strip("_ ").strip()

    return name or "UNKNOWN_SHOT"


def _docs_dir() -> str:
    # One shared directory for all tracker files.
    return os.path.normpath(get_ttk_dir())


def _data_path() -> str:
    shot = get_shot_name()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", shot)
    return os.path.join(_docs_dir(), DATA_FILE_TEMPLATE.format(shot=safe))


def _ensure_docs_dir() -> None:
    d = _docs_dir()
    if not os.path.exists(d):
        os.makedirs(d)


def _current_state_key():
    """Key that uniquely represents current tracking target."""
    if not _is_script_saved():
        return None
    return (_docs_dir(), get_shot_name())

def _computer_name() -> str:
    # Windows: COMPUTERNAME, Linux/macOS: HOSTNAME, fallback: platform.node()
    return (
        os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or platform.node()
        or "UNKNOWN_PC"
    )


# -------------------------
# Obfuscation "encryption"
# -------------------------

def _machine_salt() -> bytes:
    return _TIMETRACKER_SALT.encode("utf-8")


def _derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8", "ignore"),
        _machine_salt(),
        120_000,
        dklen=32,
    )


def _keystream(key: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def encrypt_json(payload: dict, passphrase: str) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key = _derive_key(passphrase)
    ks = _keystream(key, len(raw))
    enc = bytes([a ^ b for a, b in zip(raw, ks)])
    return base64.urlsafe_b64encode(enc).decode("ascii")


def decrypt_json(token: str, passphrase: str) -> dict:
    enc = base64.urlsafe_b64decode(token.encode("ascii"))
    key = _derive_key(passphrase)
    ks = _keystream(key, len(enc))
    raw = bytes([a ^ b for a, b in zip(enc, ks)])
    return json.loads(raw.decode("utf-8"))


def _passphrase() -> str:
    return _TIMETRACKER_KEY


# -------------------------
# Data model
# -------------------------

def _default_state() -> dict:
    now = time.time()
    return {
        "schema": 3,
        "computer": _computer_name(),
        "shot": get_shot_name(),
        "script_path": _script_path(),

        "work_seconds": 0.0,
        "render_seconds": 0.0,

        "created_at": now,
        "updated_at": now,

        "session_active": False,
        "last_tick": 0.0,

        "rendering": False,

        "last_activity": now,
        "app_active": True,
        "last_write": 0.0,
    }


def load_state() -> dict:
    if not _is_script_saved():
        return _default_state()

    path = _data_path()
    if not os.path.exists(path):
        return _default_state()

    try:
        with open(path, "r", encoding="utf-8") as f:
            token = f.read().strip()
        st = decrypt_json(token, _passphrase())

        # normalize
        st["shot"] = get_shot_name()
        st["script_path"] = _script_path()

        st.setdefault("schema", 3)
        st.setdefault("computer", _computer_name())
        st.setdefault("work_seconds", 0.0)
        st.setdefault("render_seconds", 0.0)
        st.setdefault("rendering", False)
        st.setdefault("last_activity", time.time())
        st.setdefault("app_active", True)
        st.setdefault("last_write", 0.0)
        st.setdefault("created_at", time.time())
        st.setdefault("updated_at", time.time())

        return st
    except Exception:
        return _default_state()


def save_state(st: dict) -> None:
    if not _is_script_saved():
        return
    _ensure_docs_dir()
    st["updated_at"] = time.time()
    token = encrypt_json(st, _passphrase())
    with open(_data_path(), "w", encoding="utf-8") as f:
        f.write(token)


# -------------------------
# Runtime state + ticking
# -------------------------

_STATE = None
_STATE_KEY = None
_TICKER = None
_APPSTATE_CONN = None
_UI_OPEN = False


def set_ui_open(is_open: bool) -> None:
    """Called by UI window when it opens/closes."""
    global _UI_OPEN
    _UI_OPEN = bool(is_open)


def _get_state() -> dict:
    global _STATE, _STATE_KEY

    key = _current_state_key()

    if key is not None and _STATE_KEY != key:
        _STATE = None
        _STATE_KEY = key

    if _STATE is None:
        _STATE = load_state()
        _STATE_KEY = _current_state_key()

    return _STATE


def _now() -> float:
    return time.time()


def mark_activity() -> None:
    """Called often from callbacks. Must never throw."""
    try:
        if not _is_script_saved():
            return
        st = _get_state()
        st["last_activity"] = _now()
    except Exception:
        return


def _is_user_active(st: dict, now: float) -> bool:
    if not st.get("app_active", True):
        return False

    # Backdoor: if enabled AND the UI is open, count as active even without callbacks.
    if is_ales_on() and _UI_OPEN:
        return True

    return (now - float(st.get("last_activity", 0.0) or 0.0)) <= IDLE_TIMEOUT_SEC


def _commit_tick(st: dict, now: float) -> None:
    last = float(st.get("last_tick", 0.0) or 0.0)
    if last <= 0:
        st["last_tick"] = now
        return

    dt = now - last
    if dt < 0:
        dt = 0
    if dt > 10 * 60:
        dt = 0

    if st.get("rendering", False):
        st["render_seconds"] = float(st.get("render_seconds", 0.0)) + dt
    else:
        if _is_user_active(st, now):
            st["work_seconds"] = float(st.get("work_seconds", 0.0)) + dt

    st["last_tick"] = now


def _maybe_autowrite(st: dict, now: float) -> None:
    if AUTOSAVE_MODE != "minute":
        return
    lastw = float(st.get("last_write", 0.0) or 0.0)
    if (now - lastw) >= AUTOSAVE_INTERVAL_SEC:
        save_state(st)
        st["last_write"] = now


def _tick() -> None:
    if not _is_script_saved():
        return
    st = _get_state()
    if not st.get("session_active"):
        return
    if st.get("rendering") and not nuke.executing():
        st["rendering"] = False
    now = _now()
    _commit_tick(st, now)
    _maybe_autowrite(st, now)


def start_session() -> None:
    """OnScriptLoad"""
    if not _is_script_saved():
        return
    st = _get_state()
    now = _now()
    st["shot"] = get_shot_name()
    st["script_path"] = _script_path()

    st.setdefault("created_at", now)

    st["session_active"] = True
    st["last_tick"] = now
    st["last_activity"] = now
    st["last_write"] = 0.0
    save_state(st)
    _start_ticker()
    _attach_app_state()


def on_script_save() -> None:
    """OnScriptSave"""
    if not _is_script_saved():
        return

    st = _get_state()

    if not st.get("session_active", False):
        start_session()
        st = _get_state()

    now = _now()
    _commit_tick(st, now)
    save_state(st)
    st["last_write"] = now


def on_script_close() -> None:
    """OnScriptClose"""
    if not _is_script_saved():
        return

    st = _get_state()
    now = _now()

    if st.get("rendering", False):
        _commit_tick(st, now)
        st["rendering"] = False

    if st.get("session_active"):
        _commit_tick(st, now)
        st["session_active"] = False

    save_state(st)
    _stop_ticker()


# -------------------------
# Render hooks
# -------------------------

def on_before_render() -> None:
    st = _get_state()
    st["rendering"] = True
    mark_activity()


def on_after_render() -> None:
    st = _get_state()
    st["rendering"] = False
    mark_activity()

def on_render_abort() -> None:
    """Called when render is cancelled or aborted."""
    st = _get_state()
    now = _now()

    if st.get("rendering", False):
        _commit_tick(st, now)
        st["rendering"] = False
        save_state(st)

# -------------------------
# App focus tracking
# -------------------------

def _attach_app_state() -> None:
    global _APPSTATE_CONN
    if _APPSTATE_CONN is not None:
        return

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    def _on_state_changed(state):
        st = _get_state()
        st["app_active"] = (state == QtCore.Qt.ApplicationActive)
        if st["app_active"]:
            mark_activity()

    try:
        app.applicationStateChanged.connect(_on_state_changed)
        _APPSTATE_CONN = _on_state_changed
    except Exception:
        _APPSTATE_CONN = None


# -------------------------
# Ticker
# -------------------------

def _start_ticker() -> None:
    global _TICKER
    if _TICKER is not None:
        return
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    t = QtCore.QTimer()
    t.setInterval(TICK_INTERVAL_MS)
    t.timeout.connect(_tick)
    t.start()
    _TICKER = t


def _stop_ticker() -> None:
    global _TICKER
    if _TICKER is None:
        return
    try:
        _TICKER.stop()
    except Exception:
        pass
    _TICKER = None


# -------------------------
# UI helpers
# -------------------------

def human_time(seconds: float) -> str:
    try:
        s = int(seconds)
    except Exception:
        s = 0
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def get_live_work_seconds() -> float:
    st = _get_state()
    return float(st.get("work_seconds", 0.0))


def get_live_render_seconds() -> float:
    st = _get_state()
    return float(st.get("render_seconds", 0.0))


def get_data_file_path() -> str:
    if not _is_script_saved():
        return ""
    _ensure_docs_dir()
    return _data_path()
