"""Check the final layout's published radius/bearing table against its coordinates."""
from __future__ import annotations

import math

from bench import load_layout


def bearing(dx: float, dy: float) -> float:
    return ((math.degrees(math.atan2(dx, -dy)) + 180) % 360) - 180


def run() -> list[dict]:
    layout = load_layout()
    results = []
    arms = {
        "pourer": tuple(layout["pourer_base"]["xy"]),
        "transfer": tuple(layout["transfer_base"]["xy"]),
    }
    targets = {
        "pourer": [
            ("rack_1", tuple(layout["rack_stands"][0]["xy"]), *layout["r_bearing"]["pourer"]["rack"][:1],
             layout["r_bearing"]["pourer"]["rack"][1][0]),
            ("rack_2", tuple(layout["rack_stands"][1]["xy"]), 290, -65),
            ("rack_3", tuple(layout["rack_stands"][2]["xy"]), 290, -85),
            ("scale", tuple(layout["scale"]["pan"][:2]), *layout["r_bearing"]["pourer"]["scale"]),
            ("funnel", tuple(layout["funnel"]["xy"]), *layout["r_bearing"]["pourer"]["funnel"]),
        ],
        "transfer": [
            ("carousel_pick", tuple(layout["carousel"]["pick"]), *layout["r_bearing"]["transfer"]["carousel_pick"]),
            ("scale", tuple(layout["scale"]["pan"][:2]), *layout["r_bearing"]["transfer"]["scale"]),
        ],
    }
    for arm, entries in targets.items():
        bx, by = arms[arm]
        for name, point, expected_r, expected_b in entries:
            dx, dy = point[0] - bx, point[1] - by
            actual_r, actual_b = math.hypot(dx, dy), bearing(dx, dy)
            bearing_err = abs(((actual_b - expected_b + 180) % 360) - 180)
            radius_pass = abs(actual_r - expected_r) <= 1.0
            warning = None
            if bearing_err > 1.0:
                warning = (f"stored bearing {expected_b:+g}° disagrees with coordinates; "
                           f"coordinate bearing is {actual_b:+.2f}°")
            results.append({"arm": arm, "station": name, "radius_mm": actual_r,
                            "bearing_deg": actual_b, "radius_error_mm": actual_r - expected_r,
                            "bearing_error_deg": bearing_err, "pass": radius_pass,
                            "source_note": warning})
    return results


if __name__ == "__main__":
    rows = run()
    for row in rows:
        print(f"{row['arm']:8s} {row['station']:14s} r={row['radius_mm']:7.2f} mm "
              f"bearing={row['bearing_deg']:7.2f}° {'PASS' if row['pass'] else 'FAIL'}")
        if row["source_note"]:
            print(f"  NOTE: {row['source_note']}")
    if not all(row["pass"] for row in rows):
        raise SystemExit(1)
