"""Bench test of the closed-loop carousel: relative TT moves from wherever it is. Usage: python scripts/tt_moves.py 90 -90 45
Port from $WLB_MEGA (default /dev/cu.usbserial-1130). Opening the port resets the Mega."""
import os
import time, json, sys
from benchsim.backends import real
mega, t = real.open_mega(os.environ.get('WLB_MEGA', '/dev/cu.usbserial-1130'), dry_run=False)
time.sleep(2.5); t.read_lines()
p=mega.command('PING'); print('PING tt %s adc %s' % (p.get('tt'), p.get('tt_adc')), flush=True)
mega.command('CLR', home=True)
cur=float(mega.command('PING')['tt'])
moves=[float(x) for x in sys.argv[1:]]
for d in moves:
    tgt=max(-105.0,min(245.0,cur+d)); ms=int(max(1000, abs(tgt-cur)/45*1000)+100)
    t0=time.time()
    try: r=mega.motion('TT', done_timeout=ms/1000+6, deg=tgt, ms=ms); print('move %+.0f: target %.1f done at %.2f deg in %.2f s (cmd %.2f s)' % (d,tgt,r['deg'],time.time()-t0,ms/1000), flush=True)
    except Exception as e: print('move failed', e, flush=True); break
    time.sleep(0.8); p=mega.command('PING'); print('   after settle: tt %.2f adc %s' % (p['tt'], p.get('tt_adc')), flush=True); cur=p['tt']
