"""Run the chemistry and mechanism reference scenario without hardware."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from chemistry import FoamReaction, PourPlant
from hal.protocol import decode_line, encode_line
from hal.sim import make_sim_bench
from motion.pick_place import transfer_beaker


def run(*, physical_p1_transfer: bool = False) -> dict:
    world, pourer, transfer, mega = make_sim_bench()
    world.step(2.0)
    plant = PourPlant(seed=2026)

    def scale_sample() -> dict:
        for sample in mega.samples():
            if "w" in sample:
                return {"time_ms": sample["w"][0], "grams": sample["w"][1]}
            if "f" in sample:
                raise RuntimeError(f"Simulated Mega fault: {sample['f']}")
        raise RuntimeError("weight stream ended unexpectedly")

    def mega_command(command: dict) -> dict:
        """Round-trip through the same JSON-line codec used for serial messages."""
        response = decode_line(mega.handle_line(encode_line(command)))
        if response.get("state") == "BUSY":
            completion = mega.wait_until_idle()
            if not completion.get("ok"):
                raise RuntimeError(f"Simulated Mega command failed: {completion}")
            response["completion"] = completion
        if not response.get("ok"):
            raise RuntimeError(f"Simulated Mega rejected command: {response}")
        return response

    arm_snapshot = {"pourer": pourer.read_positions(), "transfer": transfer.read_positions()}
    arm_start_deg = arm_snapshot["pourer"]["wrist_roll"]
    arm_target_deg = arm_start_deg + 5.0
    pourer.write_goals({"wrist_roll": arm_target_deg})
    world.step(0.25)
    arm_reached_deg = pourer.read_positions()["wrist_roll"]
    pourer.write_goals({"wrist_roll": arm_start_deg})
    world.step(0.25)
    arm_returned_deg = pourer.read_positions()["wrist_roll"]
    tare_response = mega_command({"cmd": "tare"})

    events = []
    # Empty P1 is carried to the scale by the documented transfer arm sequence.
    if physical_p1_transfer:
        transfer_result = transfer_beaker(
            world, "transfer", "carousel_beaker_1", (0.620, 0.407, 0.0957))
        events.append({"step": 1, "action": "P1 carousel to scale",
                       "physical_arm_motion": True, "transfer": transfer_result})
    else:
        events.append({"step": 1, "action": "P1 carousel to scale",
                       "physical_arm_motion": False})
    dev = plant.pour(80.0, 39.0, receiver_radius_mm=20.0, receiver_drop_mm=20.0)
    world.set_scale_payload_g(dev.landed_g)
    world.step(1.0)
    dev_scale = scale_sample()
    dev_scale_g = dev_scale["grams"]
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
    auger = mega_command({"cmd": "auger", "revs": auger_revs, "ms": 7000})
    yeast_mass = round(auger_revs * grams_per_rev, 3)
    world.step(1.0)
    yeast_scale = scale_sample()
    yeast_scale_g = yeast_scale["grams"]
    world.set_scale_payload_g(0)
    world.step(1.0)
    events.append({"step": 5, "action": "dose yeast into P2", "target_g": 7.0,
                   "revolutions": auger_revs, "actual_g": yeast_mass,
                   "mega_command": auger})
    events.append({"step": 6, "action": "P2 to scale and verify yeast", "measured_g": yeast_scale_g,
                   "scale_sample": yeast_scale})
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

    carousel_cmd = mega_command({"cmd": "carousel", "deg": 180, "ms": 8000})
    carousel_dose = world.status()
    mega_command({"cmd": "carousel", "deg": 0, "ms": 8000})
    stage_cmd = mega_command({"cmd": "stage", "deg": 150, "ms": 2500})
    stage_target_mm = stage_cmd["completion"]["travel_mm"]
    stage_mm = world.status()["stage_travel_mm"]
    foam_model = FoamReaction()
    h2o2_g = funnel_dev.landed_g * 0.12
    foam_samples = []
    for sample_index in range(1, 44):
        time_s = sample_index / 10
        sample = foam_model.sample(time_s, h2o2_g=h2o2_g, yeast_g=yeast_mass)
        world.set_foam_height_mm(sample.height_mm)
        world.step(0.1)
        foam_samples.append({"time_s": sample.time_s, "height_mm": sample.height_mm})
    foam_peak = foam_samples[-1]["height_mm"]
    events.append({"step": 10, "action": "move stage to ERUPT", "stage_travel_mm": stage_mm,
                   "carousel_dose_pose": carousel_dose["carousel_deg"],
                   "carousel_command": carousel_cmd, "stage_command": stage_cmd,
                   "stage_target_mm": stage_target_mm,
                   "foam": {"h2o2_g": h2o2_g, "yeast_g": yeast_mass,
                            "oxygen_estimate_l": foam_model.oxygen_l_at_reference *
                            h2o2_g / foam_model.reference_h2o2_g,
                            "induction_delay_s": foam_model.induction_delay_s,
                            "growth_duration_s": foam_model.growth_duration_s,
                            "peak_height_mm": foam_peak,
                            "samples": foam_samples}})
    return {
        "simulator": "independent-reference-analytical-chemistry",
        "model_scope": "MuJoCo geometry and mechanisms; analytical liquid, yeast, and foam models",
        "hardware_used": False,
        "process_arm_trajectory_playback": physical_p1_transfer,
        "arm_bus_initial_positions_deg": arm_snapshot,
        "arm_control_smoke": {
            "joint": "pourer.wrist_roll", "start_deg": arm_start_deg,
            "target_deg": arm_target_deg, "reached_deg": arm_reached_deg,
            "returned_deg": arm_returned_deg,
        },
        "mega_tare_response": tare_response,
        "mega_json_line_codec_exercised": True,
        "events": events,
        "final_mujoco": world.status(),
        "notes": [
            ("P1 carousel-to-scale uses joint-limited MuJoCo arm motion. Other process transfers "
             "remain logical events." if physical_p1_transfer else
             "The scenario exercises the process targets, not a calibrated arm trajectory replay."),
            "Liquid flow and landing are equations, not CFD or particle physics.",
            "Foam growth duration and peak height are visual defaults, not measured reaction data.",
            "Weir coefficient and auger grams per revolution are uncalibrated defaults.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physical-p1-transfer", action="store_true",
                        help="move empty P1 from the carousel to the scale with the transfer arm")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "build" / "reference_run.json")
    args = parser.parse_args()
    result = run(physical_p1_transfer=args.physical_p1_transfer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for event in result["events"]:
        desc = event["action"]
        pour = event.get("pour")
        if pour:
            print(f"{event['step']:02d}. {desc}: landed {pour['landed_g']:.2f} g, "
                  f"spill {pour['spilled_g']:.2f} g, peak flow {pour['peak_flow_g_s']:.2f} g/s")
        elif "transfer" in event:
            transfer = event["transfer"]
            print(f"{event['step']:02d}. {desc}: arm transfer, "
                  f"{transfer['final_site_error_mm']:.2f} mm placement error, "
                  f"{transfer['upright_error_deg']:.2f}° tilt, "
                  f"{len(transfer['arm_contacts'])} modeled arm contacts")
        elif "stage_travel_mm" in event:
            print(f"{event['step']:02d}. {desc}: {event['stage_travel_mm']:.2f} mm")
            if "foam" in event:
                foam = event["foam"]
                print(f"    foam: {foam['peak_height_mm']:.1f} mm peak, "
                      f"{foam['oxygen_estimate_l']:.2f} L oxygen estimate")
        else:
            print(f"{event['step']:02d}. {desc}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
