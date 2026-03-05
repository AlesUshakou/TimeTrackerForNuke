# settings.py
# Centralized settings for TimeTracker tool.

from __future__ import annotations

import json
import os
from typing import Any, Dict


def _here() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _settings_path() -> str:
    return os.path.join(_here(), "settings.json")


def default_settings() -> Dict[str, Any]:
    ttk_dir = os.path.join(os.path.expanduser("~"), ".nuke", ".ttk")
    return {
        "ttk_dir": ttk_dir,
        "always_on_top": False,
    }


def load_settings() -> Dict[str, Any]:
    path = _settings_path()
    if not os.path.exists(path):
        st = default_settings()
        save_settings(st)
        return st

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        data = {}

    st = default_settings()
    st.update({k: v for k, v in data.items() if v is not None})

    # normalize
    st["ttk_dir"] = str(st.get("ttk_dir") or default_settings()["ttk_dir"])  # type: ignore

    # Secret feature: only react if key exists in settings.json.
    if "ales" in data:
        st["ales"] = "on" if str(data.get("ales", "")).lower() == "on" else "off"

    return st


def save_settings(st: Dict[str, Any]) -> None:
    path = _settings_path()
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload: Dict[str, Any] = {
        "ttk_dir": st.get("ttk_dir"),
        "always_on_top": bool(st.get("always_on_top", False)),
    }

    # Write secret flag ONLY when enabled (and only if present in st).
    if str(st.get("ales", "")).lower() == "on":
        payload["ales"] = "on"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    try:
        os.replace(tmp, path)
    except Exception:
        # fallback
        try:
            os.remove(path)
        except Exception:
            pass
        os.rename(tmp, path)


def get_ttk_dir() -> str:
    return load_settings().get("ttk_dir") or default_settings()["ttk_dir"]


def is_ales_on() -> bool:
    st = load_settings()
    return st.get("ales") == "on"


def set_ales(on: bool) -> None:
    st = load_settings()
    if on:
        st["ales"] = "on"
    else:
        # Turning off should REMOVE the key entirely (keep it secret).
        st.pop("ales", None)
    save_settings(st)
