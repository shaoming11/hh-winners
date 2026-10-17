"""Access the final bench layout without copying its coordinates."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAYOUT_PATH = ROOT / "tools" / "layout" / "layout_final.json"


def load_layout() -> dict:
    data = json.loads(LAYOUT_PATH.read_text())
    layout = data["update13_final"]
    if layout.get("status") != "ALL 8 STEPS PASS":
        raise ValueError(f"Unexpected final layout status: {layout.get('status')}")
    return layout


def station_table(layout: dict | None = None) -> dict[str, tuple[float, float, float]]:
    """Return station centers in metres, with Z at the beaker floor."""
    layout = layout or load_layout()
    carousel = layout["carousel"]
    stations = {
        "pourer_base": (*layout["pourer_base"]["xy"], 20.0),
        "transfer_base": (*layout["transfer_base"]["xy"], 20.0),
        "scale": tuple(layout["scale"]["pan"]),
        "funnel": (*layout["funnel"]["xy"], layout["funnel"]["rim_z"]),
        "carousel_pick": (*carousel["pick"], carousel["beaker_bottom_z"]),
        "carousel_auger": (*carousel["auger"], carousel["beaker_bottom_z"]),
    }
    stations.update({
        f"rack_{i + 1}": (*item["xy"], layout["rack_beaker_bottom_z"])
        for i, item in enumerate(layout["rack_stands"])
    })
    return {name: tuple(float(v) / 1000 for v in xyz) for name, xyz in stations.items()}
