"""Run the chemistry and mechanism reference scenario without hardware."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from chemistry import PourPlant
from world import BenchWorld


def run() -> dict:
    world = BenchWorld()
    world.step(2.0)
    world.tare_scale()
    plant = PourPlant(seed=2026)

    events = []
    # Empty P1 is carried to the scale by the documented transfer arm sequence.
    events.append({"step": 1, "action": "P1 carousel to scale", "virtual_arm_motion": False})
    dev = plant.pour(80.0, 39.0, receiver_radius_mm=20.0, receiver_drop_mm=20.0)
    world.set_scale_payload_g(dev.landed_g)
    world.step(1.0)
    dev_scale_g = world.scale_grams()
    events.append({"step": 2, "action": "developer onto P1", "pour": dev.__dict__,
                   "mujoco_scale_reading_g": dev_scale_g})
    world.set_scale_payload_g(0)
    world.step(1.0)
    funnel_dev = plant.pour(dev.landed_g, dev.landed_g, receiver_radius_mm=40.0,
                            receiver_drop_mm=50.0, flow_target_g_s=6.0)
    events.append({"step": 3, "action": "P1 into funnel", "pour": funnel_dev.__dict__})
    events.append({"step": 4, "action": "P1 back to carousel", "virtual_arm_motion": False})

    # Powder dosing has a simple calibrated revolutions model; no discrete yeast particles.
    grams_per_rev = 0.50
    auger_revs = 7.0 / grams_per_rev
    yeast_mass = round(auger_revs * grams_per_rev, 3)
    world.set_scale_payload_g(yeast_mass)
    world.step(1.0)
    yeast_scale_g = world.scale_grams()
    world.set_scale_payload_g(0)
    world.step(1.0)
    events.append({"step": 5, "action": "dose yeast into P2", "target_g": 7.0,
                   "revolutions": auger_revs, "actual_g": yeast_mass})
    events.append({"step": 6, "action": "P2 to scale and verify yeast", "measured_g": yeast_scale_g})
    water = plant.pour(80.0, 30.0, receiver_radius_mm=20.0, receiver_drop_mm=20.0)
    world.set_scale_payload_g(yeast_mass + water.landed_g)
    world.step(1.0)
    water_scale_g = world.scale_grams()
    world.set_scale_payload_g(0)
    world.step(1.0)
    events.append({"step": 7, "action": "water onto P2", "pour": water.__dict__,
                   "mujoco_scale_total_g": water_scale_g})
    funnel_slurry = plant.pour(yeast_mass + water.landed_g, yeast_mass + water.landed_g,
                               receiver_radius_mm=40.0, receiver_drop_mm=50.0,
                               flow_target_g_s=6.0)
    events.append({"step": 8, "action": "P2 slurry into funnel", "pour": funnel_slurry.__dict__})
    events.append({"step": 9, "action": "P2 back to carousel", "virtual_arm_motion": False})

    world.move_carousel(180, duration=8.0)
    carousel_dose = world.status()
    world.move_carousel(0, duration=8.0)
    stage_mm = world.move_stage(150, duration=2.5)
    events.append({"step": 10, "action": "move stage to ERUPT", "stage_travel_mm": stage_mm,
                   "carousel_dose_pose": carousel_dose["carousel_deg"]})
    return {
        "simulator": "independent-reference-analytical-chemistry",
        "model_scope": "MuJoCo geometry and mechanisms; analytical liquid and yeast models",
        "hardware_used": False,
        "arm_motion_simulated": False,
        "events": events,
        "final_mujoco": world.status(),
        "notes": [
            "The scenario exercises the process targets, not a calibrated arm trajectory replay.",
            "Liquid flow and landing are equations, not CFD or particle physics.",
            "Weir coefficient and auger grams per revolution are uncalibrated defaults.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "build" / "reference_run.json")
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for event in result["events"]:
        desc = event["action"]
        pour = event.get("pour")
        if pour:
            print(f"{event['step']:02d}. {desc}: landed {pour['landed_g']:.2f} g, "
                  f"spill {pour['spilled_g']:.2f} g, peak flow {pour['peak_flow_g_s']:.2f} g/s")
        elif "stage_travel_mm" in event:
            print(f"{event['step']:02d}. {desc}: {event['stage_travel_mm']:.2f} mm")
        else:
            print(f"{event['step']:02d}. {desc}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
