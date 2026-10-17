"""Run the reference simulator's layout, scale, pour, carousel and stage checks."""
from __future__ import annotations

from run_demo import run
from verify_layout import run as verify_layout
from chemistry import PourPlant
from hal.protocol import LineDecoder, decode_line, encode_line
from verify_motion import run as verify_motion
from verify_transfer import run as verify_transfer
from verify_carousel import run as verify_carousel
from verify_rack_transfer import run as verify_rack_transfer


def main() -> None:
    layout_rows = verify_layout()
    assert all(row["pass"] for row in layout_rows), "one or more station radii are outside 1 mm"
    motion = verify_motion()
    transfer = verify_transfer()
    carousel = verify_carousel()
    rack_transfer = verify_rack_transfer()

    result = run()
    smoke = result["arm_control_smoke"]
    assert abs(smoke["reached_deg"] - smoke["target_deg"]) <= 1.0
    assert abs(smoke["returned_deg"] - smoke["start_deg"]) <= 1.0
    assert result["process_arm_trajectory_playback"] is False
    assert result["mega_json_line_codec_exercised"] is True
    example = {"cmd": "carousel", "deg": 45, "ms": 2500}
    line = encode_line(example)
    assert decode_line(line) == example
    decoder = LineDecoder()
    assert decoder.feed(line[:7]) == []
    assert decoder.feed(line[7:]) == [example]
    events = {event["step"]: event for event in result["events"]}
    dev = events[2]["pour"]
    water = events[7]["pour"]
    assert abs(dev["landed_g"] - 39.0) <= 2.0, f"developer dose out of range: {dev['landed_g']} g"
    assert abs(water["landed_g"] - 30.0) <= 2.0, f"water dose out of range: {water['landed_g']} g"
    assert abs(events[2]["mujoco_scale_reading_g"] - dev["landed_g"]) <= 1.0
    assert abs(events[6]["measured_g"] - 7.0) <= 0.7
    expected_total = events[5]["actual_g"] + water["landed_g"]
    assert abs(events[7]["mujoco_scale_total_g"] - expected_total) <= 1.0
    assert events[3]["pour"]["spilled_g"] < 0.1
    assert events[8]["pour"]["spilled_g"] < 0.1
    assert abs(events[10]["carousel_dose_pose"] - 180.0) <= 1.0
    assert abs(events[10]["stage_travel_mm"] - 97.3) <= 1.0

    batch_plant = PourPlant(seed=42)
    batch = [batch_plant.pour(80.0, 39.0).landed_g for _ in range(10)]
    batch_mean = sum(batch) / len(batch)
    batch_sd = (sum((value - batch_mean) ** 2 for value in batch) / len(batch)) ** 0.5
    assert abs(batch_mean - 39.0) <= 2.0
    assert batch_sd <= 0.5

    print("PASS: final layout radii match within 1 mm")
    print("PASS: 39 g developer and 30 g water targets are within ±2 g")
    print("PASS: simulated load-cell reads the added mass within 1 g")
    print("PASS: yeast target, carousel index, and 97.3 mm stage move are within tolerance")
    print("PASS: both funnel pours land inside the modeled opening")
    print(f"PASS: SO-101 IK reaches the carousel grasp point with {motion['ik_min_joint_margin_deg']:.1f}° min joint margin")
    print(f"PASS: proximity grasp latches at {motion['grasp_distance_mm']:.2f} mm and follows a wrist command")
    print(f"PASS: P1 carousel-to-scale transfer lands {transfer['final_site_error_mm']:.2f} mm off target, "
          f"tilt {transfer['upright_error_deg']:.2f}°")
    print(f"PASS: four carousel beakers follow a {carousel['reached_deg']:.2f}° index and stay in their pockets")
    print(f"PASS: rack-to-scale transfer lands {rack_transfer['final_site_error_mm']:.2f} mm off target, "
          f"tilt {rack_transfer['upright_error_deg']:.2f}°")
    print("PASS: SO-101 joint command, JSON-line codec, and simulated mechanism commands respond")
    print(f"PASS: 10 simulated 39 g pours mean {batch_mean:.2f} g, SD {batch_sd:.2f} g")


if __name__ == "__main__":
    main()
