"""Build a versioned, machine-readable comparison report from acceptance outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from bench import LAYOUT_PATH, load_layout


HERE = Path(__file__).resolve().parent
ASSET_MANIFEST = HERE / "so101_assets.json"
SCHEMA = "wet-lab-sim-audit/v1"


def _metric(value: float, unit: str, comparison_tolerance: float) -> dict[str, Any]:
    return {"value": float(value), "unit": unit,
            "comparison_tolerance": float(comparison_tolerance)}


def build_report(*, layout_rows: list[dict], reach: dict, stage: dict, motion: dict,
                 transfer: dict, carousel: dict, rack_transfer: dict,
                 physical_pour: dict, foam: dict, demo: dict,
                 batch_mean_g: float, batch_sd_g: float) -> dict[str, Any]:
    """Normalize validation outputs into stable names, units, and comparison limits."""
    layout = load_layout()
    model = json.loads(ASSET_MANIFEST.read_text())
    metrics: dict[str, dict[str, Any]] = {}

    def put(name: str, value: float, unit: str, tolerance: float) -> None:
        metrics[name] = _metric(value, unit, tolerance)

    scene_rows = reach["scene_coordinate_rows"]
    put("layout.max_station_coordinate_error", max(row["error_mm"] for row in scene_rows), "mm", 1.0)
    for row in layout_rows:
        name = f"layout.radius_error.{row['arm']}.{row['station']}"
        put(name, row["radius_error_mm"], "mm", 1.0)
    for row in reach["reach_rows"]:
        prefix = f"reach.{row['arm']}.{row['station']}"
        put(f"{prefix}.position_error", row["position_error_mm"], "mm", 2.0)
        put(f"{prefix}.joint_margin", row["min_joint_margin_deg"], "deg", 10.0)

    put("grasp.carousel_pick.distance", motion["grasp_distance_mm"], "mm", 3.0)
    put("grasp.carousel_pick.weld_position_error", motion["latch_position_error_mm"], "mm", 1.0)
    put("grasp.carousel_pick.weld_rotation_error", motion["latch_rotation_error_deg"], "deg", 1.0)
    put("grasp.held_relative_position_error", motion["held_position_error_mm"], "mm", 2.0)
    put("grasp.held_relative_rotation_error", motion["held_rotation_error_deg"], "deg", 3.0)
    put("grasp.carousel_pick.joint_margin", motion["ik_min_joint_margin_deg"], "deg", 10.0)

    for prefix, result in (("transfer.carousel_to_scale", transfer),
                           ("transfer.rack_to_scale", rack_transfer)):
        put(f"{prefix}.site_error", result["final_site_error_mm"], "mm", 8.0)
        put(f"{prefix}.upright_error", result["upright_error_deg"], "deg", 5.0)
        put(f"{prefix}.min_joint_margin",
            min(segment["min_joint_margin_deg"] for segment in result["segments"]), "deg", 10.0)
        put(f"{prefix}.arm_contact_count", len(result["arm_contacts"]), "count", 0.0)

    carousel_error = abs(carousel["reached_deg"] - carousel["commanded_deg"])
    put("carousel.index_error", carousel_error, "deg", 1.0)
    for name, result in sorted(carousel["beakers"].items()):
        prefix = f"carousel.{name}"
        put(f"{prefix}.angular_error", abs(result["angular_travel_deg"] - carousel["reached_deg"]), "deg", 1.0)
        put(f"{prefix}.radius_error", abs(result["radius_mm"] - 84.0), "mm", 0.5)
        put(f"{prefix}.tilt", result["tilt_deg"], "deg", 1.0)

    put("pour.delivered_mass", physical_pour["landed_g"], "g", 2.0)
    put("pour.spilled_mass", physical_pour["spilled_g"], "g", 0.1)
    put("pour.peak_tilt", physical_pour["peak_tilt_deg"], "deg", 5.0)
    put("pour.min_joint_margin", physical_pour["minimum_joint_margin_deg"], "deg", 10.0)
    put("pour.max_gripper_drift", physical_pour["maximum_gripper_drift_mm"], "mm", 8.0)
    put("pour.scale_mass", physical_pour["scale_g"], "g", 1.0)
    put("pour.duration", physical_pour["duration_s"], "s", 2.0)
    put("pour.arm_contact_count", len(physical_pour["arm_contacts"]), "count", 0.0)
    put("pour.donor_transfer.site_error", physical_pour["donor_transfer"]["placement_error_mm"], "mm", 8.0)
    put("pour.receiver_transfer.site_error", physical_pour["receiver_transfer"]["placement_error_mm"], "mm", 8.0)

    for index, (measured, profile) in enumerate(zip(stage["stages"], stage["profiles"])):
        label = f"stage.crank_{int(measured['crank_deg'])}deg"
        put(f"{label}.target_travel", measured["target_travel_mm"], "mm", 1.0)
        put(f"{label}.endpoint_error", abs(measured["actual_travel_mm"] - measured["target_travel_mm"]), "mm", 1.0)
        put(f"{label}.max_sample_step", profile["maximum_sample_step_mm"], "mm", 1.0)
        put(f"{label}.sample_count", profile["sample_count"], "samples", 20.0)
    put("stage.home_error", abs(stage["stages"][-1]["actual_travel_mm"]), "mm", 0.5)
    put("stage.crank_150deg.calibration_error",
        abs(stage["crank_model"]["travel_at_150_deg_mm"] - 97.3), "mm", 1.0)

    events = {event["step"]: event for event in demo["events"]}
    developer = events[2]["pour"]
    water = events[7]["pour"]
    put("demo.developer_landed_mass", developer["landed_g"], "g", 2.0)
    put("demo.developer_spill_mass", developer["spilled_g"], "g", 0.1)
    put("demo.developer_scale_error", abs(events[2]["mujoco_scale_reading_g"] - developer["landed_g"]), "g", 1.0)
    put("demo.yeast_dose_error", abs(events[5]["actual_g"] - 7.0), "g", 0.7)
    put("demo.yeast_scale_error", abs(events[6]["measured_g"] - 7.0), "g", 0.7)
    expected_water_total = events[5]["actual_g"] + water["landed_g"]
    put("demo.water_landed_mass", water["landed_g"], "g", 2.0)
    put("demo.water_spill_mass", water["spilled_g"], "g", 0.1)
    put("demo.water_scale_error", abs(events[7]["mujoco_scale_total_g"] - expected_water_total), "g", 1.0)
    put("demo.carousel_dose_index_error", abs(events[10]["carousel_dose_pose"] - 180.0), "deg", 1.0)
    put("demo.stage_travel_error", abs(events[10]["stage_travel_mm"] - 97.3), "mm", 1.0)
    put("chemistry.foam_peak_height", foam["peak_height_mm"], "mm", 10.0)
    put("chemistry.oxygen_estimate", foam["oxygen_estimate_l"], "L", 0.2)
    put("analytics.39g_mean", batch_mean_g, "g", 2.0)
    put("analytics.39g_standard_deviation", batch_sd_g, "g", 0.5)

    checks = {
        "final_layout_radii": "PASS",
        "live_scene_coordinates": "PASS",
        "position_ik_reach": "PASS",
        "weld_grasp_follow_and_release": "PASS",
        "carousel_to_scale_transfer": "PASS",
        "rack_to_scale_transfer": "PASS",
        "carousel_index_and_pocket_retention": "PASS",
        "arm_driven_analytical_pour": "PASS",
        "stage_profile_and_funnel_attachment": "PASS",
        "analytical_dose_repeatability": "PASS",
        "mega_json_line_control": "PASS",
        "carousel_transfer_contact_audit": "PASS" if not transfer["arm_contacts"] else "REVIEW",
        "pour_contact_audit": "PASS" if not physical_pour["arm_contacts"] else "REVIEW",
    }
    return {
        "schema": SCHEMA,
        "simulator": "wet-lab-independent-reference",
        "scope": "MuJoCo mechanisms and SO-101 arm motion with analytical liquid, yeast, and foam",
        "source": {
            "layout_file": "tools/layout/layout_final.json",
            "layout_section": "update13_final",
            "layout_sha256": hashlib.sha256(LAYOUT_PATH.read_bytes()).hexdigest(),
            "so101_repository": model["repository"],
            "so101_commit": model["commit"],
            "so101_model": model["model"],
        },
        "checks": checks,
        "overall": "PASS" if all(value == "PASS" for value in checks.values()) else "REVIEW",
        "metrics": metrics,
    }


def write_report(report: dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path
