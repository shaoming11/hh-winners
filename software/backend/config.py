"""The backend's view of the bench constants, read from benchsim's `bench_params.toml`.

`bench.config.Config` exposed them as dotted paths (`cfg.at("recipe.yeast_tol_g")`), and the watchdog and the
tests are written against that shape, so this keeps the accessor and changes only where the numbers come from.
A path that benchsim spells differently is listed in ALIASES rather than being hard-coded at each call site.
"""
from __future__ import annotations

import sys
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
if str(SOFTWARE / "benchsim") not in sys.path:
    sys.path.insert(0, str(SOFTWARE / "benchsim"))

# backend path -> benchsim path
ALIASES = {
    "control.scale.min_rate_hz": "scale.min_rate_hz",
    "recipe.activate_s": "recipe.activate_wait_s",
}

DEFAULTS = {
    "scale.min_rate_hz": 40.0,       # closed-loop pours need a settled rate; electrical.md 5 runs the cell at 80 Hz
}


class Config:
    """dotted-path read-only view of benchsim's bench params"""

    def __init__(self, params: dict):
        self.params = params

    def at(self, path: str, default=None):
        key = ALIASES.get(path, path)
        node = self.params
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                if key in DEFAULTS:
                    return DEFAULTS[key]
                if default is not None:
                    return default
                raise KeyError(f"no bench parameter {path!r} (looked up {key!r})")
            node = node[part]
        return node

    def get(self, path: str, default=None):
        try:
            return self.at(path, default)
        except KeyError:
            return default


def load() -> Config:
    from benchsim.layout import load_params
    return Config(load_params())
