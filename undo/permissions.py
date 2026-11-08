"""macOS permissions Undo needs, checked without triggering any prompt. Missing ones fail silently otherwise (⇧ ⇧ does nothing)."""
from __future__ import annotations

import ctypes
import platform
from typing import Callable

_APP_SERVICES = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
_IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"


def _ask_bool(symbol: str) -> bool:
    fn = getattr(ctypes.CDLL(_APP_SERVICES), symbol)
    fn.restype = ctypes.c_bool  # these return a one-byte Boolean: the default int would read undefined upper bits
    return fn()


def _accessibility() -> bool:
    return _ask_bool("AXIsProcessTrusted")


def _screen_recording() -> bool:
    return _ask_bool("CGPreflightScreenCaptureAccess")


def _input_monitoring() -> bool:
    return ctypes.CDLL(_IOKIT).IOHIDCheckAccess(1) == 0  # kIOHIDRequestTypeListenEvent; 0 = granted


CHECKS: dict[str, Callable[[], bool]] = {
    "Screen Recording": _screen_recording,
    "Accessibility": _accessibility,
    "Input Monitoring": _input_monitoring,
}


def missing_permissions() -> list[str]:
    """Names of the permissions not granted. A check that cannot run counts as granted: this is only a hint."""
    if platform.system() != "Darwin":
        return []
    missing = []
    for name, check in CHECKS.items():
        try:
            if not check():
                missing.append(name)
        except Exception:
            pass
    return missing
