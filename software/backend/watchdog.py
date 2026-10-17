"""QA rules: turn the raw snapshot into Health + Alerts.  Deterministic, no AI.  Runs inside the
runner's publish path (a few Hz) and on run events; the Photon agent reads the result and
decides who to tell.  Thresholds come from benchsim's bench_params.toml so sim and hardware agree."""
from __future__ import annotations

import re

from backend.config import Config
from backend.schemas import ExperimentState, now_iso
from backend.store import Store

SPILL_G = 0.5
LATE_RE = re.compile(r"did not settle: ([\d.]+) deg off after ([\d.]+) s")


class Watchdog:
    def __init__(self, store: Store, cfg: Config):
        self.store = store
        self.cfg = cfg
        self.overruns = 0
        self.stalls = 0
        self.min_rate = float(cfg.at("control.scale.min_rate_hz"))
        self.tol = {"developer": float(cfg.at("recipe.developer_tol_g")),
                    "yeast": float(cfg.at("recipe.yeast_tol_g")),
                    "water": float(cfg.at("recipe.water_tol_g"))}

    def reset(self) -> None:
        self.overruns = 0
        self.stalls = 0

    # called by the runner with the freshly-built snapshot (under no lock)
    def evaluate(self, s: ExperimentState) -> None:
        st = self.store
        h = s.health
        if s.mega.estop:
            st.alert("ESTOP", "critical", "e-stop is pressed: carousel, stage and auger are unpowered")
        else:
            st.resolve_alerts("ESTOP")
        if s.mega.fault and s.mega.fault != "ESTOP":
            st.alert("FAULT", "critical", f"Mega latched fault {s.mega.fault}; needs `clr` after the cause is fixed")
        if s.mega.hx_hz is not None and s.mega.hx_hz < self.min_rate:
            st.alert("SCALE_RATE", "warning", f"load cell at {s.mega.hx_hz:.0f} Hz, closed-loop pours need >= {self.min_rate:.0f} Hz")
        if s.chemistry and s.chemistry.spilled_total_g > SPILL_G:
            st.alert("SPILL", "critical", f"{s.chemistry.spilled_total_g:.1f} g landed outside a vessel",
                     step=_cur_step(s), data={"spilled_g": s.chemistry.spilled_total_g})
        if h.servo_temp_max_c is not None and h.servo_temp_max_c > 60:
            st.alert("TEMP", "warning", f"servo at {h.servo_temp_max_c:.0f} C")
        for p in s.pending_approvals:
            st.alert("NEEDS_APPROVAL", "info", f"waiting for a decision: {p.summary}", data={"request_id": p.id})
        if not s.pending_approvals:
            st.resolve_alerts("NEEDS_APPROVAL")

        def upd(state: ExperimentState) -> None:
            hh = state.health
            hh.arm_settle_overruns = self.overruns
            hh.stalls = self.stalls
            hh.scale_rate_hz = state.mega.hx_hz
            hh.spilled_g = state.chemistry.spilled_total_g if state.chemistry else 0.0
            hh.spill_detected = hh.spilled_g > SPILL_G
            hh.last_check_ts = now_iso()
            crit = any(a.severity == "critical" and not a.resolved for a in st.alerts.values())
            hh.ok = not crit and not state.mega.estop and not state.mega.fault
        st.update(upd)

    # sequencer log lines: pick out the precursors of the faults we have actually seen
    def on_log(self, line: str, step: str | None) -> None:
        m = LATE_RE.search(line)
        if m:
            self.overruns += 1
            self.store.alert("OVERRUN", "warning",
                             f"arm {m.group(1)} deg off target after {m.group(2)} s (overrun #{self.overruns})",
                             step=step, dedupe=False)
        if "stall" in line.lower() or "missed pick" in line.lower() or "close onto nothing" in line.lower():
            self.stalls += 1
            self.store.alert("STALL", "warning", line.strip(), step=step, dedupe=False)

    def on_dose(self, name: str, target: float, actual: float, step: str | None) -> None:
        tol = self.tol.get(name, 2.0)
        err = actual - target
        if abs(err) > tol:
            self.store.alert("DOSE_ERROR", "warning",
                             f"{name}: {actual:.2f} g vs target {target:.1f} g ({err:+.2f} g, tol {tol} g)",
                             step=step, data={"dose": name, "target": target, "actual": actual}, dedupe=False)

    def on_fault(self, msg: str, step: str | None) -> None:
        self.store.alert("FAULT", "critical", f"SAFE_STOP: {msg}", step=step, dedupe=False)

    def on_beaker_check(self, camera: str, present: bool, step: str | None) -> None:
        def upd(state: ExperimentState) -> None:
            state.health.camera_ok = True
            state.health.beaker_check[step or camera] = present
        self.store.update(upd)
        if not present:
            self.store.alert("BEAKER_MISSING", "warning", f"camera {camera} does not see a beaker before {step}",
                             step=step, dedupe=False)


def _cur_step(s: ExperimentState) -> str | None:
    if s.run and s.run.current_step is not None and s.run.current_step < len(s.run.steps):
        return s.run.steps[s.run.current_step].name
    return None
