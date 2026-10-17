"""Load bench.yaml, the single source of truth shared by the sim and the hardware backends."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BENCH_YAML = Path(__file__).resolve().parent / "bench.yaml"

MM = 0.001  # mm -> metres, the one place the unit boundary lives


class Config(dict):
    """dict with attribute access and a dotted `get` for nested keys."""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Config(v) if isinstance(v, dict) else v

    def at(self, path: str, default: Any = ...) -> Any:
        node: Any = self
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is ...:
                    raise KeyError(f"bench.yaml has no key {path!r}")
                return default
            node = node[part]
        return Config(node) if isinstance(node, dict) else node


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> Config:
    p = path or BENCH_YAML
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing - run `python3 software/scripts/make_bench_config.py` first"
        )
    return Config(yaml.safe_load(p.read_text()))


def joint_limits_deg(cfg: Config | None = None, margin: bool = True) -> dict[str, tuple[float, float]]:
    """Joint limits in degrees, optionally shrunk by the CDR-31 5 deg margin per side."""
    cfg = cfg or load()
    m = cfg.at("arms.limit_margin_deg") if margin else 0.0
    return {k: (lo + m, hi - m) for k, (lo, hi) in cfg.at("arms.joint_limits_deg").items()}


def margin_to_limit_deg(q_deg: dict[str, float], cfg: Config | None = None) -> tuple[float, str]:
    """Smallest distance from any joint to its (margined) limit, and which joint binds."""
    lims = joint_limits_deg(cfg)
    worst, who = math.inf, ""
    for name, q in q_deg.items():
        if name not in lims:
            continue
        lo, hi = lims[name]
        d = min(q - lo, hi - q)
        if d < worst:
            worst, who = d, name
    return worst, who
