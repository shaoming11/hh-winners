"""Host-side helpers for the carousel, the stage and the yeast dose. The sequencer calls these.

Backend independent: everything goes through ``MegaClient`` (benchsim.interfaces), the layout and bench_params.toml.
Nothing here imports MuJoCo; ``python -m benchsim.verify_mechanisms`` checks these helpers against the MuJoCo model.

    mech = Mechanisms(bb.mega)                  # deck at 0 deg, stage at WORK, P1 in pocket 0 (at the pick), P2 in pocket 1
    mech.carousel_to('P2', 'auger')             # turn the deck so P2's pocket is under the auger outlet
    rec = mech.dose_yeast('P2', 7.0, weigh, back)   # 85 % pass, scale verification, <= 2 top-ups -> DoseRecord
    mech.stage_to('ERUPT')

Carousel: pocket k sits at bearing ``pocket_ids_deg[k] + deck`` about the carousel centre, where deck is the carousel
joint angle (counter-clockwise seen from above). The pick and auger bearings come from update13_final. The deck angle
that brings pocket k to a station is the single solution of ``bearing - pocket_ids_deg[k] (mod 360)`` inside
``deck_range_deg``; the range is 290 deg wide, so there is at most one. Commanded travel time is the firmware minimum,
``min_s_per_45deg`` per 45 deg.

Stage: an in-line slider-crank (tools/cad/stage_b.py). The crank of radius r turns about (450, 77), with the angle
measured from +Y, and drives a rod of length L. The sled pin sits at
y = 77 + r cos(theta) + sqrt(L^2 - r^2 sin^2(theta)), so the sled travel toward the audience (-Y) is
s(theta) = (r + L) - r cos(theta) - sqrt(L^2 - r^2 sin^2(theta)). s(150 deg) = 97.3 mm.
"""
import math
from dataclasses import asdict, dataclass, field

from . import layout
from .interfaces import MegaError

STATIONS = ('pick', 'auger')
INITIAL_POCKETS = ('P1', 'P2', None, None)          # demo_process 4 / scene.BEAKERS: P1 pocket 0 (pick), P2 pocket 1


# ======================================================================= carousel geometry
def station_bearings(bench):
    """bearing (deg, counter-clockwise from +X) of the pick and auger stations about the carousel centre (update13_final)"""
    st = bench['stations']; c = st['carousel_centre']['xy']; out = {}
    for s in STATIONS:
        p = st['carousel_' + s]['xy']; out[s] = math.degrees(math.atan2(p[1] - c[1], p[0] - c[0])) % 360.0
    return out


def deck_angle(pocket_deg, station_deg, deck_range):
    """deck angle inside deck_range that puts a pocket at pocket_deg (deck 0) onto station_deg; None if unreachable"""
    a = (station_deg - pocket_deg) % 360.0
    for c in (a - 360.0, a, a + 360.0):
        if deck_range[0] <= c <= deck_range[1]: return c
    return None


def station_table(bench=None):
    """deck angle for every (pocket, station)"""
    bench = bench or layout.load_bench(); C = bench['params']['carousel']; brg = station_bearings(bench)
    return [dict(pocket=k, station=s, pocket_deg=a, station_bearing_deg=round(brg[s], 3),
                 deck_deg=None if deck_angle(a, brg[s], C['deck_range_deg']) is None else round(deck_angle(a, brg[s], C['deck_range_deg']), 3))
            for k, a in enumerate(C['pocket_ids_deg']) for s in STATIONS]


def travel_ms(span_deg, carousel):
    """commanded carousel move time: the >= 2 s per 45 deg rule, rounded up to whole ms"""
    return int(math.ceil(1000.0 * carousel['min_s_per_45deg'] * abs(span_deg) / 45.0 - 1e-9))


# ======================================================================= stage geometry
def slider_crank_travel(theta_deg, r, L):
    """sled travel (mm) from WORK (crank 0 deg, top dead centre) at crank angle theta"""
    t = math.radians(theta_deg)
    return (r + L) - r * math.cos(t) - math.sqrt(L * L - (r * math.sin(t)) ** 2)


def crank_for_travel(s, r, L):
    """inverse of slider_crank_travel on 0..180 deg (monotonic there), by bisection"""
    lo, hi = 0.0, 180.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if slider_crank_travel(mid, r, L) < s: lo = mid
        else: hi = mid
    return (lo + hi) / 2


def stage_table(stage, step_deg=10.0):
    r, L = stage['crank_r'], stage['rod_l']; n = int(round(stage['erupt_deg'] / step_deg))
    return [dict(crank_deg=i * step_deg, travel_mm=round(slider_crank_travel(i * step_deg, r, L), 4)) for i in range(n + 1)]


# ======================================================================= dosing arithmetic
def round_rev(x, res):
    return round(round(x / res) * res, 6)


def first_pass_rev(target_g, g_per_rev, auger, model):
    """electrical.md 6: first pass ~85 % of the target by revolutions"""
    return round_rev(auger['first_pass_frac'] * target_g / g_per_rev, model['rev_resolution'])


def topup_rev(target_g, measured_g, g_per_rev, model):
    """architecture 6: round((target - m) / g_per_rev, 0.1) rev"""
    return round_rev((target_g - measured_g) / g_per_rev, model['rev_resolution'])


@dataclass
class DoseRecord:
    beaker: str
    target_g: float
    tol_g: float
    g_per_rev: float
    passes: list = field(default_factory=list)       # {kind, rev_cmd, rev_done, stalls, t_start, t_end, mass_g}
    measured_g: float = None                          # last scale verification (yeast only)
    error_g: float = None
    topups: int = 0
    status: str = 'running'                           # ok | short | over | fault
    fault: str = None
    detail: str = ''

    @property
    def ok(self): return self.status == 'ok'

    @property
    def revs(self): return sum(p['rev_done'] or 0.0 for p in self.passes)

    def to_dict(self): return dict(asdict(self), ok=self.ok, revs=round(self.revs, 3))


# ======================================================================= the helpers the sequencer calls
class Mechanisms:
    """carousel, stage and auger on top of a MegaClient, with the pocket -> beaker bookkeeping"""

    def __init__(self, mega, bench=None, deck_deg=0.0, stage='WORK', pockets=INITIAL_POCKETS):
        self.mega = mega; self.clock = mega.clock; self.bench = bench or layout.load_bench(); P = self.bench['params']
        self.C, self.S, self.A, self.M = P['carousel'], P['stage'], P['auger'], P['auger_model']
        self.bearing = station_bearings(self.bench); self.deck = float(deck_deg); self.stage = stage
        self.pockets = list(pockets); self.moves = []

    # ---------------------------------------------------------- carousel
    def deck_for(self, pocket, station):
        a = deck_angle(self.C['pocket_ids_deg'][pocket], self.bearing[station], self.C['deck_range_deg'])
        if a is None: raise ValueError('pocket %d cannot reach %s inside deck range %s' % (pocket, station, self.C['deck_range_deg']))
        return a

    def nearest_pocket(self, station):
        """(pocket, angular error deg) of the pocket nearest the station at the current deck angle"""
        errs = [((a + self.deck - self.bearing[station] + 180.0) % 360.0) - 180.0 for a in self.C['pocket_ids_deg']]
        k = min(range(len(errs)), key=lambda i: abs(errs[i])); return k, errs[k]

    def pocket_at(self, station): return self.nearest_pocket(station)[0]

    def pocket_of(self, beaker):
        if beaker not in self.pockets: raise KeyError('%s is not in the carousel (pockets %s)' % (beaker, self.pockets))
        return self.pockets.index(beaker)

    def beaker_at(self, station): return self.pockets[self.pocket_at(station)]

    def remove(self, beaker):
        """the transfer arm took ``beaker`` out of the pick pocket"""
        k = self.pocket_of(beaker)
        if k != self.pocket_at('pick'): raise ValueError('%s is in pocket %d, not at the pick (pocket %d)' % (beaker, k, self.pocket_at('pick')))
        self.pockets[k] = None; return k

    def insert(self, beaker, station='pick'):
        """the transfer arm put ``beaker`` into the pocket now at ``station``"""
        k = self.pocket_at(station)
        if self.pockets[k] is not None: raise ValueError('pocket %d at %s holds %s' % (k, station, self.pockets[k]))
        if beaker in self.pockets: raise ValueError('%s is already in pocket %d' % (beaker, self.pockets.index(beaker)))
        self.pockets[k] = beaker; return k

    def turn_deck(self, deg):
        """TT to ``deg`` at the minimum allowed duration; returns a move record (host-timed)"""
        span = abs(deg - self.deck); ms = travel_ms(span, self.C)
        rec = dict(from_deg=round(self.deck, 3), to_deg=round(deg, 3), span_deg=round(span, 3), cmd_ms=ms)
        if ms == 0: rec.update(skipped=True, travel_s=0.0, reported_deg=self.deck); self.moves.append(rec); return rec
        t0 = self.clock.now()
        r = self.mega.motion('TT', done_timeout=ms / 1000.0 + 2 * self.C['timeout_extra_s'], deg=round(deg, 3), ms=ms)
        self.deck = float(r.get('deg', deg))
        rec.update(skipped=False, t_start=round(t0, 3), travel_s=round(self.clock.now() - t0, 3), reported_deg=self.deck); self.moves.append(rec)
        return rec

    def carousel_to(self, beaker, station):
        """turn the deck so ``beaker``'s pocket (or pocket index) is at 'pick' or 'auger'"""
        if station not in STATIONS: raise ValueError('station must be one of %s' % (STATIONS,))
        k = beaker if isinstance(beaker, int) else self.pocket_of(beaker)
        rec = self.turn_deck(self.deck_for(k, station)); rec.update(pocket=k, station=station, beaker=self.pockets[k]); return rec

    # ---------------------------------------------------------- stage
    def stage_to(self, position):
        """ST to WORK (crank 0 deg) or ERUPT (crank 150 deg) in [stage] move_s"""
        if position not in ('WORK', 'ERUPT'): raise ValueError('position must be WORK or ERUPT')
        deg = self.S['work_deg'] if position == 'WORK' else self.S['erupt_deg']; ms = int(round(self.S['move_s'] * 1000))
        t0 = self.clock.now()
        r = self.mega.motion('ST', done_timeout=self.S['move_s'] + 2 * self.S['timeout_extra_s'], deg=deg, ms=ms)
        self.stage = position
        return dict(position=position, cmd_deg=deg, cmd_ms=ms, reported_deg=r.get('deg'), t_start=round(t0, 3), travel_s=round(self.clock.now() - t0, 3))

    # ---------------------------------------------------------- auger
    def auger(self, rev, kind='dose'):
        """one AUG forward; the Mega reverses 1/4 turn after it and applies the stall rule"""
        t0 = self.clock.now(); p = dict(kind=kind, rev_cmd=rev, rev_done=None, stalls=None, t_start=round(t0, 3), mass_g=None)
        r = self.mega.motion('AUG', done_timeout=self.A['dose_timeout_s'] + self.M['host_reply_margin_s'], rev=rev, dir=1)
        p.update(rev_done=r.get('rev'), stalls=r.get('stalls'), t_end=round(self.clock.now(), 3)); return p

    def calibrate(self, beaker, weigh, back):
        """architecture 6 (calibrate_auger.py): cal_runs x cal_revs into a tared cup -> g/rev. ``weigh`` returns the
        cumulative yeast in the cup; hooks as in dose_yeast. The cup ends back in its pocket."""
        runs = []; last = 0.0
        for _ in range(int(self.M['cal_runs'])):
            self.carousel_to(beaker, 'auger'); p = self.auger(self.M['cal_revs'], 'calibration')
            self.carousel_to(beaker, 'pick'); self.remove(beaker); m = float(weigh(beaker)); back(beaker); self.insert(beaker)
            p.update(mass_g=m, added_g=m - last, g_per_rev=(m - last) / p['rev_done']); runs.append(p); last = m
        revs = sum(p['rev_done'] for p in runs)
        return dict(g_per_rev=last / revs, runs=runs, revs=revs, grams=last)

    def dose_yeast(self, beaker, target_g, weigh, back, tol_g=None, max_topups=None, g_per_rev=None, initial_g=0.0):
        """Yeast dose into ``beaker`` (electrical.md 6, architecture 6, demo_process steps 5-6).

        Turn its pocket to the auger, run a first pass of first_pass_frac * target by revolutions, turn it to the
        pick and verify on the scale. While the mass is below target - tol, run at most ``max_topups`` top-ups of
        round((target - m) / g_per_rev, rev_resolution) rev, each from the auger station and verified the same way.

        Hooks; the transfer-arm moves belong to the sequencer:
            weigh(beaker) -> grams of yeast   called with the beaker in its pocket at the pick. Take it to the scale
                                              and return its yeast mass (reading minus the beaker's tare). The
                                              beaker stays on the scale afterwards (step 7 pours water onto it).
            back(beaker)                      called before a top-up: put the beaker back into the pick pocket.
        Pocket bookkeeping is done here: remove() before weigh, insert() after back.

        Host hopper-empty rule: once >= hopper_window_rev revolutions have run in this dose, a gain under
        hopper_empty_g_per_10rev per window ends the dose with fault HOPPER_EMPTY. This is the scale-side form of the rule.
        Mega faults (AUGER_JAM, HOPPER_EMPTY, *_TIMEOUT) and errors end the dose with status 'fault'; a host-side
        TimeoutError (the Mega went silent) propagates.
        """
        tol = self.bench['params']['recipe']['yeast_tol_g'] if tol_g is None else tol_g
        topups = self.A['max_topups'] if max_topups is None else max_topups
        gpr = self.A['g_per_rev_nominal'] if g_per_rev is None else g_per_rev
        R = DoseRecord(beaker=beaker, target_g=target_g, tol_g=tol, g_per_rev=gpr)
        try:
            self.carousel_to(beaker, 'auger')
            R.passes.append(self.auger(first_pass_rev(target_g - initial_g, gpr, self.A, self.M), 'first'))
            m = self._verify(R, beaker, weigh, initial_g)
            while R.status == 'running' and m < target_g - tol and R.topups < topups:
                rev = topup_rev(target_g, m, gpr, self.M)
                if rev < self.M['rev_resolution']: break
                back(beaker); self.insert(beaker); self.carousel_to(beaker, 'auger')
                R.topups += 1; R.passes.append(self.auger(rev, 'topup')); m = self._verify(R, beaker, weigh, initial_g)
        except MegaError as e:
            R.status = 'fault'; R.fault = e.code
            R.detail = 'Mega %s %s' % ('error' if 'err' in e.reply else 'fault', {k: v for k, v in e.reply.items() if k not in ('crc', 'fault', 'err')}); return R
        if R.status == 'running':
            R.status = 'ok' if abs(m - target_g) <= tol else ('short' if m < target_g else 'over')
        return R

    def _verify(self, R, beaker, weigh, initial_g):
        self.carousel_to(beaker, 'pick'); self.remove(beaker)
        m = float(weigh(beaker)); R.passes[-1]['mass_g'] = round(m, 4); R.measured_g = m; R.error_g = m - R.target_g
        win = self.M['hopper_window_rev']; revs = R.revs
        if revs >= win and (m - initial_g) / revs * win < self.A['hopper_empty_g_per_10rev'] * win / 10.0:
            R.status = 'fault'; R.fault = 'HOPPER_EMPTY'
            R.detail = 'host scale check: %.2f g over %.1f rev' % (m - initial_g, revs)
        return m
