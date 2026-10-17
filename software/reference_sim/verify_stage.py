"""Check the stage command profile, endpoint, and attached funnel motion."""
from __future__ import annotations

from hal.protocol import decode_line, encode_line
from hal.sim import SimMegaLink
from world import BenchWorld


def _command_stage(mega: SimMegaLink, world: BenchWorld, degrees: float,
                   *, duration_ms: int = 2500) -> dict:
    command = {"cmd": "stage", "deg": degrees, "ms": duration_ms}
    response = decode_line(mega.handle_line(encode_line(command)))
    if not response.get("ok") or response.get("state") != "BUSY":
        raise AssertionError(f"stage command did not enter BUSY through JSON-line HAL: {response}")

    samples = []
    completion = None
    for event in mega.samples():
        if "f" in event:
            raise AssertionError(f"stage command faulted: {event['f']}")
        if "w" in event:
            samples.append({"time_ms": event["w"][0],
                            "travel_mm": world.status()["stage_travel_mm"]})
        if "done" in event:
            completion = event
            break
        if len(samples) > duration_ms // 5 + 400:
            raise AssertionError("stage command failed to complete within its bounded sample window")
    if completion is None:
        raise AssertionError("stage sample stream ended without a completion record")
    return {"samples": samples, "completion": completion}


def _assert_profile(samples: list[dict], *, increasing: bool) -> dict:
    values = [row["travel_mm"] for row in samples]
    deltas = [b - a for a, b in zip(values, values[1:])]
    wrong_way = [delta for delta in deltas if delta < -0.5] if increasing else [
        delta for delta in deltas if delta > 0.5]
    if wrong_way:
        raise AssertionError(f"stage profile reversed by {max(abs(x) for x in wrong_way):.2f} mm")
    maximum_step = max((abs(delta) for delta in deltas), default=0.0)
    if maximum_step > 3.0:
        raise AssertionError(f"stage moved {maximum_step:.2f} mm in one 80 Hz sample")
    return {"sample_count": len(samples), "maximum_sample_step_mm": maximum_step,
            "start_mm": values[0], "end_mm": values[-1]}


def run() -> dict:
    world = BenchWorld()
    mega = SimMegaLink(world)
    start_funnel, _ = world.body_pose("funnel")
    profiles = []
    stages = []
    for degrees, increasing in ((75.0, True), (150.0, True), (0.0, False)):
        result = _command_stage(mega, world, degrees)
        profile = _assert_profile(result["samples"], increasing=increasing)
        target = world.stage_travel_mm(degrees)
        actual = world.status()["stage_travel_mm"]
        if abs(actual - target) > 0.25:
            raise AssertionError(f"stage at {degrees:g}° ended {actual:.2f} mm, expected {target:.2f} mm")
        reported = result["completion"].get("actual_travel_mm")
        if reported is None or abs(reported - target) > 0.25:
            raise AssertionError(f"stage completion did not report the measured endpoint: {reported}")
        funnel, _ = world.body_pose("funnel")
        travel_since_start = float(start_funnel[1] - funnel[1])
        if abs(travel_since_start - actual / 1000) > 0.001:
            raise AssertionError("funnel did not follow the stage sled's linear travel")
        if abs(funnel[0] - start_funnel[0]) > 1e-6 or abs(funnel[2] - start_funnel[2]) > 1e-6:
            raise AssertionError("stage moved the funnel off its X/Z guide line")
        stages.append({"crank_deg": degrees, "target_travel_mm": target,
                       "actual_travel_mm": actual, "funnel_y_delta_mm":
                       float((funnel[1] - start_funnel[1]) * 1000)})
        profiles.append(profile)

    end_mm = world.status()["stage_travel_mm"]
    if abs(end_mm) > 0.25:
        raise AssertionError(f"stage failed to return home: {end_mm:.2f} mm")
    return {"stages": stages, "profiles": profiles,
            "crank_model": {"radius_mm": 50.0, "rod_mm": 80.0,
                            "travel_at_150_deg_mm": world.stage_travel_mm(150.0)}}


if __name__ == "__main__":
    report = run()
    for stage, profile in zip(report["stages"], report["profiles"]):
        print(f"PASS: JSON stage {stage['crank_deg']:g}° -> "
              f"{stage['actual_travel_mm']:.2f}/{stage['target_travel_mm']:.2f} mm; "
              f"{profile['sample_count']} samples, max step {profile['maximum_sample_step_mm']:.2f} mm")
    print("PASS: attached funnel followed the sled and returned to home")
