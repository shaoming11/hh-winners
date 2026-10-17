import sys, signal, time; sys.path.insert(0,'.')
signal.alarm(300)
import numpy as np
from bench.config import load
from bench.hal.sim import make_sim_bench
from bench.motion.player import MotionLock
from bench.motion.stations import load_or_plan, StationPlanner
from bench.process.transfer import ArmTask
from bench.process.scale import Scale
from bench.process.pour import PourController
cfg=load(); plans=load_or_plan(cfg); b=make_sim_bench(cfg); b.connect(); w=b.sim
w.fill("developer","developer",70.0)
lock=MotionLock(); q=lambda s:None
tr=ArmTask(b,'transfer',plans,lock,cfg,log=q); tr.transfer('carousel_pick','scale')
po=ArmTask(b,'pourer',plans,lock,cfg,log=q); po.pick('rack_developer')
sc=Scale(b,cfg); plan=plans['pourer:pour_scale']
ctl=PourController(b,po.player,sc,plan,cfg,q,StationPlanner(cfg),via=[plans['pourer:scale'].carry.q])
ctl.enter()
print("tare ->", round(sc.tare(0.3),2), " raw now", round(w.scale_grams_raw(),2))
# manual tilt ramp, watching the signals
last=-1
for th in np.arange(55,106,1.0):
    ctl.ramp_to(th, 10.0)
    for _ in range(8): s=sc.next()
    if int(w.t)!=last:
        last=int(w.t)
        print("t %5.1f theta %5.1f | raw %6.2f  m_f %6.2f q_hat %5.2f sigma %.3f n %d | P1 true %6.2f g  flow %.2f g/s  landing %s | samples n=%d consumed=%d"%(
            w.t,th,w.scale_grams_raw()-sc.tare_g,s.m_f,s.q_hat,s.sigma,s.n,w.chem.vessels['P1'].total_g,w.chem.last_flow_gps.get('developer',0),str(w.chem.last_landing.get('developer'))[:40],w.n_samples,b.mega._consumed))
    if w.chem.vessels['P1'].total_g>45: break
