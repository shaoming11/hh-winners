import sys, signal; sys.path.insert(0,'.'); signal.alarm(900)
import numpy as np
from bench.config import load
from bench.hal.sim import make_sim_bench
from bench.process.sequencer import Sequencer
cfg=load(); b=make_sim_bench(cfg); b.connect(); w=b.sim
w.fill("developer","developer",70.0); w.fill("water","water",65.0)
def state(tag):
    pos={nm:tuple(np.round(w.beaker_pose(nm)[0],0)) for nm in ("P1","P2","water")}
    print("   [%s] on_scale=%s under_auger=%s spilled=%.1f  P1 %s P2 %s water %s  P2 contents %s"%(tag,w.beaker_on_scale(),w.beaker_under_auger(),w.chem.spilled_total_g,pos['P1'],pos['P2'],pos['water'],{k:round(v,1) for k,v in w.chem.vessels['P2'].contents.items()}),flush=True)
seq=Sequencer(b,cfg,log=lambda s:print("[%6.1f] %s"%(b.clock.now(),s),flush=True),on_step=lambda n,st: state(n+" "+st))
seq.run(only=["5","6","7","8"])
state("end")
