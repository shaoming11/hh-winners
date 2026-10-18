import os
# Fixed move set from the current angle; logs the encoder at ~12 Hz; reports reach time (within 2 deg), overshoot,
# final error at done, and drift 1.5 s after done (no drive). Usage: tttune.py ms_per_45
import time, json, sys, statistics
from benchsim.backends import real
mp45=float(sys.argv[1])
mega, t = real.open_mega(os.environ.get('WLB_MEGA', '/dev/cu.usbserial-1130'), dry_run=False)
time.sleep(2.5); t.read_lines(); mega.command('CLR', home=True)
def tt(): return float(mega.command('PING')['tt'])
start=tt(); base=min(max(start,-20.0),140.0)
res=[]
for d in (90,-90,45,-45,90,-90):
    cur=tt(); tgt=base+ (d if d>0 else 0) if False else None
    tgt = (base+90 if d==90 else base) if abs(d)==90 else (base+45 if d==45 else base)
    ms=int(max(1, abs(tgt-cur))/45*mp45)+100
    try: mega.command('CLR')
    except Exception: pass
    seq=mega.send('TT', deg=tgt, ms=ms); t0=time.time(); log=[]; done=None
    while time.time()-t0 < ms/1000+6 and done is None:
        for l in t.read_lines():
            if '"done"' in l: done=time.time()-t0
            if 'fault' in l or '"err"' in l: print('FAULT/ERR', l.strip()); done=-1
        log.append((time.time()-t0, tt()))
    reach=next((x for x,a in log if abs(a-tgt)<=2.0), None)
    over=max(((a-tgt)*(1 if tgt>cur else -1) for _,a in log), default=0)
    fin=log[-1][1]; time.sleep(1.5); after=tt()
    res.append(dict(move=round(tgt-cur), cmd_s=ms/1000, reach_s=reach and round(reach,2), done_s=done and round(done,2), overshoot=round(max(over,0),1), err_done=round(fin-tgt,1), drift=round(after-fin,1)))
    print(res[-1], flush=True)
ok=[r for r in res if r['done_s'] and r['done_s']>0]
print('SUMMARY done %d/6, mean done-cmd %.2f s, max overshoot %.1f, max |drift| %.1f' % (len(ok), statistics.mean([r['done_s']-r['cmd_s'] for r in ok]) if ok else -1, max(r['overshoot'] for r in res), max(abs(r['drift']) for r in res)), flush=True)
