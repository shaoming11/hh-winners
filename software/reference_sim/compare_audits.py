"""Compare two wet-lab-sim-audit/v1 JSON reports metric by metric."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_report import SCHEMA


def compare(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if reference.get("schema") != SCHEMA or candidate.get("schema") != SCHEMA:
        raise ValueError(f"both reports must use schema {SCHEMA}")
    ref_metrics, candidate_metrics = reference.get("metrics", {}), candidate.get("metrics", {})
    ref_keys, candidate_keys = set(ref_metrics), set(candidate_metrics)
    missing = sorted(ref_keys - candidate_keys)
    extra = sorted(candidate_keys - ref_keys)
    source_keys = ("layout_sha256", "so101_commit")
    source_differences = {
        key: {"reference": reference.get("source", {}).get(key),
              "candidate": candidate.get("source", {}).get(key)}
        for key in source_keys
        if reference.get("source", {}).get(key) != candidate.get("source", {}).get(key)
    }
    check_keys = set(reference.get("checks", {})) | set(candidate.get("checks", {}))
    check_differences = {
        key: {"reference": reference.get("checks", {}).get(key),
              "candidate": candidate.get("checks", {}).get(key)}
        for key in sorted(check_keys)
        if reference.get("checks", {}).get(key) != "PASS" or
        candidate.get("checks", {}).get(key) != "PASS"
    }

    rows = []
    for key in sorted(ref_keys & candidate_keys):
        left, right = ref_metrics[key], candidate_metrics[key]
        if left.get("unit") != right.get("unit"):
            rows.append({"metric": key, "status": "UNIT_MISMATCH",
                         "reference_unit": left.get("unit"), "candidate_unit": right.get("unit")})
            continue
        left_tolerance = left.get("comparison_tolerance")
        right_tolerance = right.get("comparison_tolerance")
        if left_tolerance != right_tolerance:
            rows.append({"metric": key, "status": "TOLERANCE_MISMATCH",
                         "reference_tolerance": left_tolerance,
                         "candidate_tolerance": right_tolerance})
            continue
        ref_value, candidate_value = float(left["value"]), float(right["value"])
        delta = abs(ref_value - candidate_value)
        tolerance = float(left_tolerance)
        rows.append({"metric": key, "unit": left["unit"],
                     "reference_value": ref_value, "candidate_value": candidate_value,
                     "absolute_delta": delta, "comparison_tolerance": tolerance,
                     "status": "PASS" if delta <= tolerance else "DIFFERENCE"})

    pass_count = sum(row["status"] == "PASS" for row in rows)
    differences = [row for row in rows if row["status"] != "PASS"]
    structurally_comparable = not missing and not extra and not source_differences and not check_differences
    return {
        "schema": "wet-lab-sim-comparison/v1",
        "reference_simulator": reference.get("simulator"),
        "candidate_simulator": candidate.get("simulator"),
        "structurally_comparable": structurally_comparable,
        "missing_candidate_metrics": missing,
        "extra_candidate_metrics": extra,
        "source_differences": source_differences,
        "checks_not_passed": check_differences,
        "metrics_compared": len(rows),
        "metrics_within_tolerance": pass_count,
        "compatible": structurally_comparable and not differences,
        "metrics": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path,
                        help="write the detailed comparison JSON to this path")
    args = parser.parse_args()
    result = compare(json.loads(args.reference.read_text()), json.loads(args.candidate.read_text()))
    print(f"Comparable sources and checks: {'yes' if result['structurally_comparable'] else 'no'}")
    print(f"Metrics within tolerance: {result['metrics_within_tolerance']}/{result['metrics_compared']}")
    if result["missing_candidate_metrics"]:
        print(f"Missing candidate metrics: {', '.join(result['missing_candidate_metrics'])}")
    if result["extra_candidate_metrics"]:
        print(f"Extra candidate metrics: {', '.join(result['extra_candidate_metrics'])}")
    for row in result["metrics"]:
        if row["status"] != "PASS":
            print(f"{row['status']}: {row['metric']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        print(f"Wrote {args.output}")
    print(f"Comparison: {'COMPATIBLE' if result['compatible'] else 'DIFFERENCES FOUND'}")
    if not result["compatible"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
