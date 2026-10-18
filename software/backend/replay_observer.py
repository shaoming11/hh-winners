"""What a hardware replay is doing, in the bench's own terms.

scripts/replay_plan.py plays joint paths: it knows segment names and phases, not beakers, grams or what a step is
for.  This module gives a replay the same understanding a sequencer run has, without changing how the arms move:

- **step meaning**: each route step ("2 developer pour") is matched to the process step of the same number
  (benchsim.process.steps: POUR_TO_SCALE developer -> P1, 39 g +- 2), so it carries a type, params, a target and
  the dashboard's narration;
- **subgoals**: the step's segments, as played (replay_plan.bench_segments), grouped by phase into named parts -
  "reach P1 at carousel_pick", "grip P1", "lift P1 from carousel_pick", "pour developer into P1", "set P1 down
  at scale_pan" - each with the criterion it has to meet;
- **checks** from the hardware's own readings (servo encoders and the Mega's scale, so they hold on the real bench
  as well as on the emulator): reach error per joint, the transfer jaw stopping on a beaker, the scale falling on
  a lift and rising on a set-down, grams poured against the target, the funnel pour emptying its beaker, and a
  scale reading no beaker can explain (something pressing on the pan).  A failed check never stops the replay - it
  marks the subgoal, raises a warning alert and is reported; stopping stays the operator's call;
- **where the beakers are**, from those same checks (the sequencer's bookkeeping does not run during a replay).

Thresholds come from bench_params.toml ([gripper] scale_delta_min_g, [beaker] empty_mass_g) and from a measured
replay: a held top-down grip stops the transfer jaw 3-15 deg above its close command, an empty one closes onto it.
The pourer's side grip is commanded to its contact angle, so its jaw cannot tell held from empty; that grip is
checked on the scale when it lifts from the pan and is otherwise reported as unchecked.
"""
from __future__ import annotations

import math
import re

import numpy as np

from backend.schemas import Dose, StepState, Subgoal

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
REACH_TOL_DEG = 5.0          # replay_plan.REACH_DEG: a segment end inside this counts as reached
JAW_HELD_DEG = 2.0           # transfer jaw this far above its close command = a beaker between the fingers
FUNNEL_LEFT_G = 2.0          # a funnel pour leaving more than this in the beaker did not empty it
SCALE_SANE_G = (-50.0, 400.0)  # outside this the pan is being pushed on, not weighed
RACK = {"developer": ("dev", "rack_1"), "water": ("water", "rack_3")}
STATION_WORDS = {"carousel_pick": "the carousel", "scale_pan": "the scale", "rack_1": "rack 1", "rack_3": "rack 3",
                 "funnel": "the funnel"}


def carry_verb(name: str) -> str:
    """what a 'carry' segment does, by meaning, not by its exact wording (taught paths renamed them: 'lift straight up',
    'carry, beaker clear above the receiver', 'straight down into the receiver')"""
    n = name.lower()
    if n.startswith("raise"):
        return "raise"
    if n.startswith("lift") or "straight up" in n:
        return "lift"
    if n.startswith("lower") or "straight down" in n or "down into" in n or "down onto" in n:
        return "lower"
    return "carry"


def _where(s):
    return STATION_WORDS.get(s, s)


# ====================================================================== the static model (no hardware needed)
class ReplayModel:
    """route steps -> process meaning and subgoal templates; built before the replay starts"""

    def __init__(self, rp, plans: dict, keys: list[str], params: dict, narrate=None):
        from benchsim.process import steps as S
        self.rp, self.plans, self.keys, self.P = rp, plans, keys, params
        R = dict(params.get("recipe") or {})
        proto = []
        if R.get("yeast_in_flask"):
            proto += S.flask_demo_protocol(dict(developer_g=R.get("developer_g", 39.0), developer_tol_g=R.get("developer_tol_g", 2.0)))
        full = dict(developer_g=39.0, developer_tol_g=2.0, yeast_g=7.0, yeast_tol_g=0.7, water_g=30.0, water_tol_g=2.0,
                    activate_wait_s=60.0)
        full.update({k: v for k, v in R.items() if k in full})
        proto += S.demo_protocol(full)
        by_token = {}
        for st in proto:
            by_token.setdefault(st.label.split(" ")[0], st)
        self.meta, self.groups, self.narration = {}, {}, {}
        for k in keys:
            st = by_token.get(k.split(" ")[0])
            self.meta[k] = st
            self.narration[k] = narrate(st) if (narrate and st is not None) else None
            self.groups[k] = self._groups(k, st)

    def _played(self, k):
        """the segments replay_plan actually plays for step k (taught poses and corrections applied); the signature
        has grown (segs) -> (segs, key) -> (segs, key, arm), so try the richest first"""
        segs, arm = self.plans[k]["segments"], self.plans[k]["arm"]
        for args in ((segs, k, arm), (segs, k), (segs,)):
            try:
                return self.rp.bench_segments(*args)
            except TypeError:
                continue
        raise TypeError("replay_plan.bench_segments: unknown signature")

    # ---------------------------------------------------------------- what each step moves where
    def roles(self, k, st):
        """(object gripped, where it is picked, where it is set down, what it pours into, reagent)"""
        p = dict(st.params) if st is not None else {}
        if st is not None and st.type == "TRANSFER":
            return p["beaker"], p["src"], p["dst"], None, None
        if st is not None and st.type == "POUR_TO_SCALE":
            bk, rack = RACK.get(p["reagent"], (p["reagent"], "rack"))
            return bk, rack, rack, p["beaker"], p["reagent"]
        if st is not None and st.type == "POUR_TO_FUNNEL":
            return p["beaker"], "scale_pan", "scale_pan", "funnel", None
        segs = self.plans[k]["segments"]             # not in the process vocabulary: read it off the segment names
        obj = next((m.group(1) for sg in segs for m in [re.match(r"close on (\w+)", sg["name"])] if m), "?")
        return obj, "?", "?", None, None

    def _groups(self, k, st):
        """contiguous same-phase segments of the PLAYED path (bench_segments), named and given their criterion"""
        segs = self._played(k)
        obj, src, dst, into, reagent = self.roles(k, st)
        arm = self.plans[k]["arm"]
        out, seen = [], {}
        for i, sg in enumerate(segs):
            ph = sg["phase"]
            # the plan's "carry" phase is lift + carry across + lower: three things with different checks
            verb = carry_verb(sg["name"]) if ph == "carry" else ph
            if out and out[-1]["phase"] == ph and out[-1]["verb"] == verb:
                out[-1]["segs"].append(i); continue
            n = seen[(ph, verb)] = seen.get((ph, verb), 0) + 1
            name, expect = ph, ""
            if ph == "approach":
                name, expect = f"reach {obj} at {_where(src)}", f"arm within {REACH_TOL_DEG:.0f} deg of the planned pose"
            elif ph == "pick":
                name = f"grip {obj}"
                expect = ("the jaw stops on the beaker, above its close command" if arm == "transfer" else
                          "confirmed on the scale when it lifts" if src == "scale_pan" else
                          "a side grip closes to its contact angle; the jaw cannot confirm it")
            elif verb == "lift":
                name = f"lift {obj} from {_where(src)}"
                expect = (f"the scale falls by at least {self.P['gripper']['scale_delta_min_g']:.0f} g" if src == "scale_pan"
                          else "the jaw stays closed on the beaker" if arm == "transfer" else "")
            elif verb == "carry":
                name = (f"carry {obj} to the pour pose" if into and n == 1 else
                        f"carry {obj} back to {_where(dst)}" if into else f"carry {obj} to {_where(dst)}")
            elif verb == "lower":
                name = f"lower {obj} to the pour pose" if into and n == 1 else f"lower {obj} onto {_where(dst)}"
            elif verb == "raise":
                name = "raise from the pour"
            elif ph == "pour" and n == 1:
                if into == "funnel":
                    name, expect = f"pour {obj} into the funnel", "the beaker comes back empty"
                else:
                    tgt = (st.params.get("target_g"), st.params.get("tol_g")) if st is not None else (None, None)
                    name = f"pour {reagent or obj} into {into}"
                    expect = (f"{tgt[0]:.0f} +- {tgt[1]:.1f} g on the scale" if tgt[0] is not None else "")
            elif ph == "pour":
                name = "untilt to the pre-pour pose"
            elif ph == "drain":
                name = "hold while it drains"
            elif ph == "pour_back":
                name = "tilt back"
            elif ph == "place":
                name = f"set {obj} down at {_where(dst)}"
                if dst == "scale_pan":
                    expect = f"the scale rises by at least {self.P['gripper']['scale_delta_min_g']:.0f} g"
                    if into == "funnel":
                        expect += f", and the beaker holds <= {FUNNEL_LEFT_G:.0f} g"
            elif ph == "retreat":
                name = f"back away from {obj}"
            elif ph == "park":
                name = "return to park"
            out.append(dict(phase=ph, verb=verb, n=n, name=name, expect=expect, segs=[i]))
        return out

    # ---------------------------------------------------------------- the rows a run starts with
    def rows(self) -> list[StepState]:
        rows = []
        for i, k in enumerate(self.keys):
            st = self.meta[k]
            subs = [Subgoal(index=j + 1, name=g["name"], phase=g["phase"], expect=g["expect"])
                    for j, g in enumerate(self.groups[k])]
            rows.append(StepState(index=i + 1, name=k, type=st.type if st is not None else None,
                                  params=dict(st.params) if st is not None else {}, narration=self.narration[k],
                                  detail=f"{self.plans[k]['arm']} arm, {len(subs)} subgoals", subgoals=subs))
        return rows


# ====================================================================== the live observer (on the bench thread)
class ReplayObserver:
    """hooks for replay_plan (STEP_HOOKS / SEG_HOOKS): runs the checks and writes the run into the store"""

    def __init__(self, model: ReplayModel, store, run_id: str, hw, now):
        self.m, self.store, self.run_id, self.hw, self.now = model, store, run_id, hw, now
        G = model.P["gripper"]
        self.delta_min = float(G["scale_delta_min_g"])
        self.empty_g = float(model.P["beaker"]["empty_mass_g"])
        self.locations = {"P1": "carousel_pick", "P2": "carousel_aux", "dev": "rack_1", "water": "rack_3"}
        self.held = {"pourer": None, "transfer": None}
        self.content = {}                       # beaker -> grams the scale has seen in it
        self.index = {k: i for i, k in enumerate(model.keys)}
        self.cur = None                          # (step key, group index)
        self.seg_i = {}
        self.m_prev = None                       # scale at the end of the previous subgoal
        self.m_clear = None                      # last reading with no arm pressing on the pan (lowering and gripping excluded)
        self.m_approach = None                   # the pan just before a grip
        self.scale_bad = None                    # where the scale stopped making sense (reported once, until it recovers)
        self.m_step0 = None
        self.pour0 = None
        self.failures = []
        self.mega = getattr(hw, "mega", None)

    # ---------------------------------------------------------------- readings
    def scale(self):
        if self.mega is None:
            return None
        try:
            return round(float(self.mega.read_mass(16)), 2)
        except Exception:  # noqa: BLE001 - a silent scale is reported as no reading, never a crash
            return None

    def start(self):
        """stream the scale and zero it if the pan is empty (it is at the start of every default route)"""
        if self.mega is None:
            return
        try:
            self.mega.command("STREAM", on=True)
            first = self.m.keys[0]
            if self.m.roles(first, self.m.meta[first])[1] != "scale_pan":
                self.mega.command("TARE")
                self._event("scale streaming, tared with the pan empty")
        except Exception as e:  # noqa: BLE001
            self._event(f"scale not available ({type(e).__name__}: {e}); scale checks will be unchecked", "warning")
        self.m_prev = self.m_clear = self.scale()

    def close(self):
        if self.mega is not None:
            try:
                self.mega.command("STREAM", on=False)
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- store helpers
    def _event(self, msg, level="info", **data):
        self.store.event("step", msg, level=level, run_id=self.run_id, bench_t=round(self.now(), 2), data=data or None)

    def _upd(self, fn):
        def u(s):
            if s.run is not None and s.run.run_id == self.run_id:
                fn(s.run)
        self.store.update(u)

    def _set_sub(self, k, gi, **kw):
        i = self.index[k]

        def f(run):
            sub = run.steps[i].subgoals[gi]
            for a, v in kw.items():
                setattr(sub, a, v)
        self._upd(f)

    # ---------------------------------------------------------------- hooks
    def on_step(self, k, phase):
        i = self.index[k]
        st = self.m.meta[k]
        if phase == "start":
            self.seg_i[k] = -1
            self.m_step0 = self.m_prev
            def f(run):
                run.steps[i].status, run.steps[i].t0, run.current_step = "running", round(self.now(), 2), i
                run.bench_seconds = round(self.now(), 2)
            self._upd(f)
            self._event(f"{k}: start", step=k)
            return
        # done: the dose of a pour onto the scale is the scale's rise over the whole pour
        if st is not None and st.type == "POUR_TO_SCALE" and self.pour0 is not None:
            self._dose(k, st)
        self.pour0 = None
        run = self.store.state.run
        subs = run.steps[i].subgoals if run and run.run_id == self.run_id else []
        bad = [s for s in subs if s.status == "failed"]
        warn = [s for s in subs if s.status == "warning"]
        status = "fault" if bad else "ok"
        detail = "; ".join(f"{s.name}: {s.result}" for s in (bad or warn)) or f"{len(subs)} subgoals ok"

        def f(run):
            run.steps[i].status, run.steps[i].detail, run.steps[i].t1 = status, detail, round(self.now(), 2)
            run.bench_seconds = round(self.now(), 2)
            run.progress = round(sum(x.status in ("ok", "fault") for x in run.steps) / len(run.steps), 3)
        self._upd(f)
        self._event(f"{k}: {status}", "warning" if bad else "info", step=k, detail=detail)

    def on_seg(self, k, seg, phase):
        groups = self.m.groups[k]
        if phase == "start":
            self.seg_i[k] += 1
            gi = next(j for j, g in enumerate(groups) if self.seg_i[k] in g["segs"])
            if self.cur != (k, gi):
                self.cur = (k, gi)
                g = groups[gi]
                if g["phase"] == "pour" and g["n"] == 1:
                    self.pour0 = self.m_clear          # the receiver's weight just before the stream starts
                self._set_sub(k, gi, status="running", t0=round(self.now(), 2))
                self._upd(lambda run: setattr(run, "current_subgoal", f"{k} / {g['name']}"))
            return
        gi = self.cur[1]
        g = groups[gi]
        if self.seg_i[k] != g["segs"][-1]:
            return
        status, result, code = self._check(k, g, seg)
        self._set_sub(k, gi, status=status, result=result, code=code, t1=round(self.now(), 2))
        lvl = "warning" if status in ("failed", "warning") else "info"
        self._event(f"{k} / {g['name']}: {status} - {result}", lvl, step=k, subgoal=g["name"], status=status, code=code)
        if status == "failed" or code in ("DOSE_ERROR", "SCALE_DISTURBED"):
            self.failures.append(f"{k}: {g['name']}: {result}")
            self.store.alert(code or "REPLAY_CHECK", "warning", f"hardware replay, {k}: {g['name']} - {result}",
                             step=k, data=dict(subgoal=g["name"], code=code))

    # ---------------------------------------------------------------- the checks
    def _check(self, k, g, seg):
        arm_name = self.m.plans[k]["arm"]
        arm = self.hw.arms[arm_name]
        obj, src, dst, into, reagent = self.m.roles(k, self.m.meta[k])
        try:
            q = np.degrees(np.asarray(arm.read_positions(), float))
        except Exception:  # noqa: BLE001
            q = None
        cmd = np.degrees(np.asarray(seg["qs"][-1], float))
        m_before, m = self.m_clear, self.scale()
        self.m_prev = m
        ph, verb = g["phase"], g["verb"]
        pressing_ok = verb == "lower" or ph == "pick"     # a held beaker pushed onto the pan / a grip on it: not a weight
        sane = m is None or SCALE_SANE_G[0] <= m <= SCALE_SANE_G[1]
        if not pressing_ok and m is not None and sane:
            self.m_clear = m
            self.scale_bad = None
        if ph == "approach":
            self.m_approach = m
        notes = []
        reach_bad = None
        if q is not None:
            err = np.abs(q - cmd)[:5]
            j = int(np.argmax(err))
            if err[j] > REACH_TOL_DEG:
                reach_bad = f"{JOINTS[j]} {err[j]:.0f} deg short of the planned pose"
        if not pressing_ok and not sane:
            if self.scale_bad:                   # already reported: the scale checks are off until it reads sanely again
                return "unchecked", f"scale unusable since {self.scale_bad} ({m:.0f} g)" + (f"; {reach_bad}" if reach_bad else ""), None
            self.scale_bad = f"{k.split(' ')[0]} / {g['name']}"
            why = (f"the scale reads {m:.0f} g, which no beaker explains: "
                   + ("something is pressing on the pan" if m > 0 else "the pan is jammed or being lifted"))
            return "failed", why + (f" ({reach_bad})" if reach_bad else ""), "SCALE_DISTURBED"
        holding = self.held.get(arm_name)

        if ph == "pick":
            if arm_name == "transfer" and q is not None:
                over = q[5] - cmd[5]
                if over > JAW_HELD_DEG:
                    self._take(arm_name, obj)
                    return "ok", f"jaw stopped at {q[5]:.0f} deg on {obj} (close command {cmd[5]:.0f} deg)", None
                self.held[arm_name] = None
                return "failed", f"jaw closed to {q[5]:.0f} deg: nothing between the fingers", "GRASP_MISS"
            self._take(arm_name, obj)                # side grip: assumed until a scale says otherwise
            return "unchecked", f"jaw at {q[5]:.0f} deg" if q is not None else "no jaw reading", None

        if verb == "lift":
            if holding is None:
                return "skipped", "nothing was gripped", None
            if src == "scale_pan" and m is not None and self.m_approach is not None:
                fell = self.m_approach - m
                if fell >= self.delta_min:
                    return ("warning" if reach_bad else "ok"), f"scale fell {fell:.1f} g" + (f"; {reach_bad}" if reach_bad else ""), \
                        ("REACH_SHORT" if reach_bad else None)
                self.held[arm_name] = None
                self.locations[obj] = "scale_pan"
                return "failed", f"scale fell only {fell:.1f} g: {obj} is still on the pan" + (f" ({reach_bad})" if reach_bad else ""), "LIFT_NOT_SEEN"
            if arm_name == "transfer" and q is not None and q[5] - cmd[5] <= JAW_HELD_DEG:
                self.held[arm_name] = None
                return "failed", f"jaw closed to {q[5]:.0f} deg after the lift: {obj} dropped", "DROPPED"

        if ph == "place":
            if holding is None:
                return "skipped", f"nothing to set down ({obj} was not held)", None
            self.held[arm_name] = None
            self.locations[obj] = dst
            if dst == "scale_pan" and m is not None and m_before is not None:
                rose = m - m_before
                if rose < self.delta_min:
                    return "failed", f"scale rose only {rose:.1f} g: {obj} did not land on the pan", "PLACE_NOT_SEEN"
                notes.append(f"scale rose {rose:.1f} g")
                if into == "funnel":
                    left = max(0.0, m - self.empty_g)
                    before = self.content.get(obj)
                    self.content[obj] = round(left, 2)
                    went = f"{before - left:.1f} g went into the funnel" if before is not None else ""
                    if left > FUNNEL_LEFT_G:
                        return "failed", f"{left:.1f} g still in {obj}" + (f" ({went})" if went else ""), "FUNNEL_NOT_EMPTIED"
                    notes.append(f"{obj} empty ({left:.1f} g left{', ' + went if went else ''})")
                    self._pour_result(k, "ok", went or "beaker came back empty")
                else:
                    self.content[obj] = round(max(0.0, m - self.empty_g), 2)
            elif dst != "scale_pan":
                notes.append(f"released at {_where(dst)}")

        if ph in ("pour", "drain", "pour_back") and holding is None:
            return "skipped", "nothing held to pour", None
        if ph == "pour" and g["n"] == 1:
            return ("warning" if reach_bad else "running" if into != "funnel" else "ok"), \
                (reach_bad or ("measuring on the scale" if into not in (None, "funnel") else "poured")), \
                ("REACH_SHORT" if reach_bad else None)

        if reach_bad:
            return "warning", "; ".join(notes + [reach_bad]), "REACH_SHORT"
        return "ok", "; ".join(notes) or "done", None

    def _take(self, arm_name, obj):
        self.held[arm_name] = obj
        self.locations[obj] = arm_name

    def _pour_result(self, k, status, result, code=None):
        gi = next((j for j, g in enumerate(self.m.groups[k]) if g["phase"] == "pour" and g["n"] == 1), None)
        if gi is not None:
            self._set_sub(k, gi, status=status, result=result, code=code)

    def _dose(self, k, st):
        p = st.params
        m = self.m_prev
        if m is None or self.pour0 is None:
            self._pour_result(k, "unchecked", "no scale reading")
            return
        added = round(m - self.pour0, 2)
        content0 = self.content.get(p["beaker"], 0.0)
        target = p["target_g"] if p.get("relative") else p["target_g"] - content0
        err = round(added - target, 2)
        self.content[p["beaker"]] = round(content0 + added, 2)
        res = f"{added:.1f} g on the scale (target {target:.0f} +- {p['tol_g']:.1f} g)"
        if abs(err) <= p["tol_g"]:
            self._pour_result(k, "ok", res)
        else:
            self._pour_result(k, "warning", res + f": {abs(err):.1f} g {'over' if err > 0 else 'under'}", "DOSE_ERROR")
            self.failures.append(f"{k}: {res}")
            self.store.alert("DOSE_ERROR", "warning", f"hardware replay, {k}: {res}", step=k,
                             data=dict(added_g=added, target_g=target, tol_g=p["tol_g"]))
        key = f"{p['reagent']}_g"
        self._upd(lambda run: run.doses.__setitem__(key, Dose(target=round(target, 2), actual=added, error=err)))
