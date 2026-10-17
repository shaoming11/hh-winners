import sys, signal, time; sys.path.insert(0,'.')
signal.alarm(420)
import mujoco, numpy as np
from bench.config import load
from bench.hal.sim import make_sim_bench
from bench.motion.player import MotionLock, TrackingError
from bench.motion.stations import load_or_plan, StationPlanner
from bench.process.transfer import ArmTask
from bench.process.scale import Scale
from bench.process.pour import PourController
cfg=load(); plans=load_or_plan(cfg); b=make_sim_bench(cfg); b.connect(); w=b.sim
w.fill("developer","developer",70.0)
def gn(i): return mujoco.mj_id2name(w.m,mujoco.mjtObj.mjOBJ_GEOM,i)
lock=MotionLock(); t0=time.time()
def log(s): print("[sim %6.1f | wall %5.1f] %s"%(w.t,time.time()-t0,s), flush=True)
tr=ArmTask(b,'transfer',plans,lock,cfg,log=log); tr.transfer('carousel_pick','scale')
po=ArmTask(b,'pourer',plans,lock,cfg,log=log); po.pick('rack_developer')
plan=plans['pourer:pour_scale']; planner=StationPlanner(cfg); sc=Scale(b,cfg)
ctl=PourController(b,po.player,sc,plan,cfg,log,planner,via=[plans['pourer:scale'].carry.q])
try:
    ctl.enter(); log("ENTER OK theta=%.0f beaker z %.1f"%(ctl.theta,w.beaker_pose('developer')[0][2]))
    sc.tare(0.3); lg=ctl.pour_to(39.0,"developer"); log("POUR: %s delivered %.2f g err %+.2f theta_first %.1f cut %.1f spilled %.1f"%(lg.outcome,lg.settled_g,lg.error_g,lg.theta_first,lg.theta_cut,w.chem.spilled_total_g))
    ctl.leave(); log("LEAVE OK")
    po.place('rack_developer'); po.park(); log("DONE P1 contents %s"%{k:round(v,2) for k,v in w.chem.vessels['P1'].contents.items()})
except TrackingError as e:
    log("TRACKING ERROR %s"%e); log("contacts: %s"%[(gn(c.geom1),gn(c.geom2),round(c.dist*1000,1)) for c in w.d.contact[:w.d.ncon] if 'pourer' in gn(c.geom1)+gn(c.geom2) or 'developer' in gn(c.geom1)+gn(c.geom2)][:6])
