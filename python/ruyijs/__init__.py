"""ruyijs: persistent SpiderMonkey contexts for Python 3.10+ on Windows x64."""

from ._context import Context
from ._values import JSError, UNDEFINED
from ._callbacks import ReentrantError
from ._jsvalue import JSObject, JSFunction
from ._runtime_paths import get_runtime_path
from ._version import __version__

__all__ = ["Context", "JSError", "UNDEFINED", "ReentrantError", "JSObject", "JSFunction",
           "get_runtime_path", "__version__", "TurnstileError", "TurnstileSolution",
           "solve_turnstile", "solve_turnstile_details"]


def __getattr__(name):
    if name in ("TurnstileError", "TurnstileSolution", "solve_turnstile",
                "solve_turnstile_details"):
        from . import turnstile
        return getattr(turnstile, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
