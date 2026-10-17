"""Check final-layout coordinates and point reach for each arm's assigned stations.

Reach rows are position-only IK checks. Transfer execution, grasp following,
collision observations, and the arm-driven pour are checked by separate scripts.
"""
from __future__ import annotations

import numpy as np

from bench import load_layout, station_table
from motion.kinematics import ArmKinematics
from motion.pick_place import _position_candidates
from world import BenchWorld


COORDINATE_TOLERANCE_MM = 1.0
MIN_JOINT_MARGIN_DEG = 5.0
IK_SAMPLES = 48


def _error_mm(actual: np.ndarray, expected: tuple[float, float, float] | np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float)) * 1000)


def run() -> dict:
    layout = load_layout()
    expected = station_table(layout)
    world = BenchWorld()
    world.step(1.0)

    scene_rows = []
    for name in ("pourer_base", "transfer_base"):
        actual, _ = world.body_pose(name)
        error = _error_mm(actual, expected[name])
        scene_rows.append({"station": name, "error_mm": error})
    scale_pan, _ = world.body_pose("scale_pan")
    scale_top = scale_pan + np.array([0.0, 0.0, 0.006])
    scene_rows.append({"station": "scale", "error_mm": _error_mm(scale_top, expected["scale"])})
    carousel, _ = world.body_pose("carousel")
    carousel_xy_expected = np.array([*layout["carousel"]["centre"], 54.6]) / 1000
    scene_rows.append({"station": "carousel_centre",
                       "error_mm": _error_mm(carousel, carousel_xy_expected)})
    funnel, _ = world.body_pose("funnel")
    scene_rows.append({"station": "funnel_rim_axis",
                       "error_mm": _error_mm(funnel, expected["funnel"])})
    for name in ("carousel_pick", "rack_1", "rack_2", "rack_3"):
        actual, _ = world.site_pose(f"{'carousel_beaker_1' if name == 'carousel_pick' else 'rack_beaker_' + name[-1]}_grasp")
        floor = expected[name]
        expected_grasp = np.asarray(floor) + np.array([0.0, 0.0, 0.032])
        scene_rows.append({"station": f"{name}_grasp_site",
                           "error_mm": _error_mm(actual, expected_grasp)})
    bad_scene_rows = [row for row in scene_rows if row["error_mm"] > COORDINATE_TOLERANCE_MM]
    if bad_scene_rows:
        raise AssertionError(f"scene differs from Update-13 coordinates by more than 1 mm: {bad_scene_rows}")

    scale_grasp = np.asarray(expected["scale"]) + np.array([0.0, 0.0, 0.032])
    funnel_approach = np.asarray(expected["funnel"]) + np.array([0.0, 0.0, 0.032])
    targets = {
        "pourer": {
            **{f"rack_{i}": world.site_pose(f"rack_beaker_{i}_grasp")[0] for i in (1, 2, 3)},
            "scale_place": scale_grasp,
            "funnel_approach": funnel_approach,
        },
        "transfer": {
            "carousel_pick": world.site_pose("carousel_beaker_1_grasp")[0],
            "scale_place": scale_grasp,
        },
    }
    reach_rows = []
    for arm, stations in targets.items():
        kinematics = ArmKinematics(world, arm)
        rng = np.random.default_rng(917 if arm == "pourer" else 918)
        for station, target in stations.items():
            candidates = _position_candidates(kinematics, np.asarray(target), rng,
                                              samples=IK_SAMPLES)
            if not candidates:
                raise AssertionError(f"{arm} SO-101 has no position IK solution for {station}")
            q = max(candidates, key=lambda candidate:
                    float(kinematics.joint_margins_deg(candidate).min()))
            position, _ = kinematics.forward(q)
            row = {
                "arm": arm,
                "station": station,
                "position_error_mm": _error_mm(position, target),
                "min_joint_margin_deg": float(kinematics.joint_margins_deg(q).min()),
                "ik_candidates": len(candidates),
            }
            if row["position_error_mm"] > 2.0:
                raise AssertionError(f"{arm} missed {station} by {row['position_error_mm']:.2f} mm")
            if row["min_joint_margin_deg"] < MIN_JOINT_MARGIN_DEG:
                raise AssertionError(f"{arm} reaches {station} only {row['min_joint_margin_deg']:.1f}° from a joint limit")
            reach_rows.append(row)

    return {"scene_coordinate_rows": scene_rows, "reach_rows": reach_rows,
            "scene_coordinate_tolerance_mm": COORDINATE_TOLERANCE_MM,
            "reach_min_joint_margin_deg": MIN_JOINT_MARGIN_DEG,
            "ik_samples_per_target": IK_SAMPLES}


if __name__ == "__main__":
    report = run()
    for row in report["scene_coordinate_rows"]:
        print(f"PASS: scene {row['station']:20s} matches Update-13 within {row['error_mm']:.2f} mm")
    for row in report["reach_rows"]:
        print(f"PASS: {row['arm']:8s} reaches {row['station']:16s}; "
              f"error {row['position_error_mm']:.2f} mm, "
              f"joint margin {row['min_joint_margin_deg']:.1f}° "
              f"({row['ik_candidates']} IK solutions)")
