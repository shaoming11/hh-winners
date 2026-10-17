"""The run: the 10 steps of docs/demo_process.md 4 as a state machine with PAUSE / SAFE_STOP.

    PRECHECK -> P1_TO_SCALE -> POUR_DEVELOPER -> P1_TO_FUNNEL -> P1_TO_CAROUSEL
             -> INDEX_TO_AUGER -> AUGER_DOSE -> INDEX_TO_PICK -> P2_TO_SCALE -> VERIFY_YEAST
             -> POUR_WATER -> WAIT_ACTIVATE -> P2_TO_FUNNEL -> P2_TO_CAROUSEL -> ERUPT -> DONE

Every step is a method; `run()` walks the list, logging to the notebook record.  Any
BenchFault goes to SAFE_STOP (torque stays on, grippers never open), after which the operator
decides.  The same object runs on the sim and on hardware - it only sees the Bench HAL.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

import numpy as np

from bench.config import Config, load
from bench.hal.base import Bench, BenchFault
from bench.motion.player import MotionLock
from bench.motion.stations import load_or_plan, StationPlanner
from bench.process.mechanisms import Mechanisms
from bench.process.pour import PourController, PourLog
from bench.process.scale import Scale
from bench.process.transfer import ArmTask


@dataclass
class StepRecord:
    name: str
    t_start: float
    t_end: float = 0.0
    status: str = "running"
    detail: dict = field(default_factory=dict)


@dataclass
class RunRecord:
    recipe: dict
    steps: list[StepRecord] = field(default_factory=list)
    doses: dict = field(default_factory=dict)       # name -> {"target", "actual", "error"}
    faults: list[str] = field(default_factory=list)
    outcome: str = "not started"
    wall_s: float = 0.0


class Sequencer:
    def __init__(self, bench: Bench, cfg: Config | None = None, recipe: dict | None = None,
                 speed: float = 1.0, log=print, on_step=None):
        self.b = bench
        self.cfg = cfg or load()
        r = self.cfg.at("recipe")
        self.recipe = recipe or {"developer_g": r["developer_g"], "yeast_g": r["yeast_g"],
                                 "water_g": r["water_g"], "activate_s": r["activate_s"]}
        self.log = log
        self.on_step = on_step
        self.lock = MotionLock()
        self.plans = load_or_plan(self.cfg)
        self.planner = StationPlanner(self.cfg)
        self.pourer = ArmTask(bench, "pourer", self.plans, self.lock, self.cfg, speed, log)
        self.transfer = ArmTask(bench, "transfer", self.plans, self.lock, self.cfg, speed, log)
        self.scale = Scale(bench, self.cfg)
        self.mech = Mechanisms(bench, self.cfg, log)
        self.rec = RunRecord(dict(self.recipe))
        self.yeast_actual = 0.0
        # P1 starts in the pick pocket, P2 in the next pocket (+90 deg). The auger station is
        # opposite the pick, so +90 deg of deck rotation puts P2 under the auger and -90 deg
        # brings P2 to the pick pocket (P1's pocket then sits at +180, out of the way).
        self.carousel_pick_deg = -90.0
        self.carousel_auger_deg = 90.0

    # ---------------------------------------------------------------- steps
    def precheck(self):
        v = self.b.mega.command({"cmd": "ver"})
        if not v.get("ok"):
            raise BenchFault("Mega did not answer VER")
        if float(v.get("hx_hz", 0)) < self.cfg.at("control.scale.min_rate_hz"):
            raise BenchFault(f"HX711 rate {v.get('hx_hz')} Hz is below the closed-loop minimum")
        st = self.mech.status()
        if st.get("estop") or st.get("fault"):
            raise BenchFault(f"Mega not ready: {st}")
        for role, arm in self.b.arms.items():
            q = arm.read_positions()
            if any(abs(v) > 175 for v in q.values()):
                raise BenchFault(f"{role} reports an impossible position {q}")
        tare = self.scale.tare()
        s = self.scale.wait_settled()
        self.log(f"  precheck ok: firmware {v.get('fw')}, scale {v.get('hx_hz')} Hz, tare {tare:.1f} g, "
                 f"noise {self.scale.state.sigma:.3f} g")
        self.rec.doses["tare_g"] = round(tare, 2)

    def p1_to_scale(self):
        self.transfer.transfer("carousel_pick", "scale")
        self.scale.tare()                              # tare with the empty beaker on the pan
        self.log(f"  tared with P1 on the pan ({self.scale.tare_g:.1f} g gross)")

    def _pour_onto_scale(self, src_station: str, target: float, label: str) -> PourLog:
        self.pourer.pick(src_station)
        ctl = PourController(self.b, self.pourer.player, self.scale, self.plans["pourer:pour_scale"],
                             self.cfg, self.log, self.planner,
                             via=[self.plans["pourer:scale"].carry.q])     # cross at carry height
        ctl.enter()
        lg = ctl.pour_to(target, label)
        ctl.leave()
        self.pourer.place(src_station)
        self.pourer.park()
        return lg

    def pour_developer(self):
        lg = self._pour_onto_scale("rack_developer", self.recipe["developer_g"], "developer")
        self.rec.doses["developer"] = {"target": self.recipe["developer_g"],
                                       "actual": round(lg.settled_g, 2), "error": round(lg.error_g, 2),
                                       "theta_first": round(lg.theta_first, 1), "topups": lg.topups}
        if lg.outcome.startswith("PAUSE"):
            raise BenchFault(lg.outcome)

    def _pour_into_funnel(self, label: str):
        self.pourer.pick("scale")
        ctl = PourController(self.b, self.pourer.player, self.scale, self.plans["pourer:pour_funnel"],
                             self.cfg, self.log, self.planner,
                             via=[self.plans["pourer:scale"].carry.q])
        ctl.enter()
        ctl.pour_all()
        ctl.leave()
        self.pourer.place("scale")
        self.pourer.park()
        reading = self.scale.read_settled()          # net of the tare taken with the full beaker
        poured = -reading
        self.log(f"  {label}: {poured:.2f} g poured into the flask")
        return poured

    def p1_to_funnel(self):
        self.scale.tare()                               # net of the beaker: now reads its contents
        self.rec.doses["developer_to_flask_g"] = round(self._pour_into_funnel("P1 -> funnel"), 2)

    def p1_to_carousel(self):
        self.transfer.transfer("scale", "carousel_pick")

    def index_to_auger(self):
        self.mech.carousel_to(self.carousel_auger_deg)

    def auger_dose(self):
        a = self.cfg.at("control.auger")
        gpr = float(self.cfg.at("calibration.g_per_rev"))
        rev = self.recipe["yeast_g"] * a["first_pass_frac"] / gpr
        self.log(f"  auger: {rev:.2f} rev for {self.recipe['yeast_g'] * a['first_pass_frac']:.1f} g")
        self.mech.auger(rev)
        self.mech.auger(-a["reverse_rev"])             # stop the dribble
        self.rec.doses.setdefault("yeast", {})["rev_first_pass"] = round(rev, 2)

    def index_to_pick(self):
        self.mech.carousel_to(self.carousel_pick_deg)

    def p2_to_scale(self):
        self.scale.tare()                               # empty pan
        self.transfer.transfer("carousel_pick", "scale")

    def verify_yeast(self):
        a = self.cfg.at("control.auger"); gpr = float(self.cfg.at("calibration.g_per_rev"))
        empty = float(self.cfg.at("beaker.mass_empty_g"))
        gross = self.scale.read_settled()
        m = gross - empty
        self.log(f"  yeast on the scale: {m:.2f} g (target {self.recipe['yeast_g']} +- {self.cfg.at('recipe.yeast_tol_g')})")
        topups = 0
        while m < self.recipe["yeast_g"] - self.cfg.at("recipe.yeast_tol_g") and topups < a["max_topups"]:
            need = self.recipe["yeast_g"] - m
            rev = round(need / gpr, 1)
            self.log(f"  yeast short by {need:.2f} g: top-up {rev} rev")
            self.transfer.transfer("scale", "carousel_pick")
            self.mech.carousel_to(self.carousel_auger_deg)
            self.mech.auger(rev); self.mech.auger(-a["reverse_rev"])
            self.mech.carousel_to(self.carousel_pick_deg)
            self.scale.tare()
            self.transfer.transfer("carousel_pick", "scale")
            m = self.scale.read_settled() - empty
            topups += 1
            self.log(f"  yeast now {m:.2f} g")
        self.yeast_actual = m
        self.rec.doses["yeast"].update({"target": self.recipe["yeast_g"], "actual": round(m, 2),
                                        "error": round(m - self.recipe["yeast_g"], 2), "topups": topups})
        self.scale.tare()                               # the water pour is +30 g on top of this

    def pour_water(self):
        lg = self._pour_onto_scale("rack_water", self.recipe["water_g"], "water")
        self.rec.doses["water"] = {"target": self.recipe["water_g"], "actual": round(lg.settled_g, 2),
                                   "error": round(lg.error_g, 2), "theta_first": round(lg.theta_first, 1),
                                   "topups": lg.topups}

    def wait_activate(self):
        t = float(self.recipe.get("activate_s", 60.0))
        self.log(f"  waiting {t:.0f} s for the yeast slurry to activate")
        self.b.clock.sleep(t)

    def p2_to_funnel(self):
        self.scale.tare()
        self.rec.doses["slurry_to_flask_g"] = round(self._pour_into_funnel("P2 -> funnel"), 2)

    def p2_to_carousel(self):
        self.transfer.transfer("scale", "carousel_pick")

    def erupt(self):
        # the pourer must be clear of the stage before the sled moves
        q = self.b.arms["pourer"].read_positions()
        self.mech.stage_to("ERUPT")
        self.b.clock.sleep(float(self.cfg.at("control.eruption.foam_wait_s")))

    STEPS = [
        ("PRECHECK", "precheck"),
        ("1 P1 carousel -> scale", "p1_to_scale"),
        ("2 developer pour to 39 g", "pour_developer"),
        ("3 P1 -> funnel", "p1_to_funnel"),
        ("4 P1 -> carousel", "p1_to_carousel"),
        ("5a index P2 to the auger", "index_to_auger"),
        ("5b auger dose", "auger_dose"),
        ("5c index P2 to the pick pocket", "index_to_pick"),
        ("6a P2 -> scale", "p2_to_scale"),
        ("6b verify yeast", "verify_yeast"),
        ("7 water pour to +30 g", "pour_water"),
        ("7b wait for activation", "wait_activate"),
        ("8 P2 -> funnel", "p2_to_funnel"),
        ("9 P2 -> carousel", "p2_to_carousel"),
        ("10 ERUPT", "erupt"),
    ]

    # ---------------------------------------------------------------- driver
    def run(self, only: list[str] | None = None) -> RunRecord:
        t_wall = time.time()
        self.rec.outcome = "running"
        try:
            for name, method in self.STEPS:
                if only and not any(name.startswith(o) for o in only):
                    continue
                self.log(f"== {name}")
                sr = StepRecord(name, self.b.clock.now())
                self.rec.steps.append(sr)
                if self.on_step:
                    self.on_step(name, "start")
                getattr(self, method)()
                sr.t_end = self.b.clock.now(); sr.status = "ok"
                if self.on_step:
                    self.on_step(name, "ok")
            self.rec.outcome = "complete"
        except BenchFault as e:
            self.rec.faults.append(str(e))
            self.rec.steps[-1].status = f"fault: {e}"
            self.rec.outcome = "SAFE_STOP"
            self.log(f"!! SAFE_STOP: {e}")
            self.safe_stop()
        except Exception as e:  # noqa: BLE001 - anything else is also a safe stop
            self.rec.faults.append(f"{type(e).__name__}: {e}")
            self.rec.steps[-1].status = f"error: {e}"
            self.rec.outcome = "SAFE_STOP"
            self.log("!! SAFE_STOP (exception):\n" + traceback.format_exc())
            self.safe_stop()
        self.rec.wall_s = time.time() - t_wall
        return self.rec

    def safe_stop(self) -> None:
        """Hold everything where it is: torque on, grippers closed, servos stopped."""
        try:
            self.b.mega.command({"cmd": "stop"})
        except Exception:  # noqa: BLE001
            pass
        for task in (self.pourer, self.transfer):
            try:
                task.player.hold()
            except Exception:  # noqa: BLE001
                pass
