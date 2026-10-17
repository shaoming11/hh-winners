"""The fixed step vocabulary of the bench and the deterministic validator (shared contract).

Any process the bench runs, whether the built-in demo or a proposal from the optional language layer, is a list
of ``Step`` objects from this vocabulary. ``validate`` is the only gate before execution: it checks every
parameter against the bench's physical limits and the ordering rules of docs/demo_process.md, and returns
(ok, problems). No step carries actuator commands; the sequencer turns steps into motions.

Vocabulary (type: params):
    TRANSFER        beaker, src, dst              transfer arm, top-down: carousel_pick <-> scale_pan
    POUR_TO_SCALE   reagent, beaker, target_g, tol_g, relative   pourer, closed loop on the scale; relative=True
                                                  means target is added on top of the current scale reading
    POUR_TO_FUNNEL  beaker                        pourer, the beaker on the scale is emptied into the flask
    CAROUSEL        beaker, station               turn the deck so the beaker's pocket is at 'pick' or 'auger'
    DOSE_YEAST      beaker, target_g, tol_g, max_topups   auger into the beaker at the auger station, scale verify later
    VERIFY_MASS     beaker, target_g, tol_g       beaker on the scale; fails if outside tolerance
    WAIT            seconds, reason
    STAGE           position                      WORK | ERUPT
"""
from dataclasses import asdict, dataclass, field

STEP_TYPES = ('TRANSFER', 'POUR_TO_SCALE', 'POUR_TO_FUNNEL', 'CAROUSEL', 'DOSE_YEAST', 'VERIFY_MASS', 'WAIT', 'STAGE')
REAGENTS = {'developer': 'dev', 'water': 'water'}          # reagent -> rack beaker
CAROUSEL_BEAKERS = ('P1', 'P2')
STATIONS = ('carousel_pick', 'scale_pan')
LIMITS = dict(max_pour_g=60.0, max_beaker_ml=80.0, max_yeast_g=12.0, min_tol_g=0.5, max_wait_s=600.0, max_flask_ml=140.0,
              max_topups=2)


@dataclass
class Step:
    type: str
    params: dict = field(default_factory=dict)
    label: str = ''

    def to_dict(self): return asdict(self)

    @staticmethod
    def from_dict(d): return Step(d['type'], dict(d.get('params', {})), d.get('label', ''))


def demo_protocol(recipe=None):
    """docs/demo_process.md section 4, steps 1-10"""
    r = recipe or dict(developer_g=39.0, developer_tol_g=2.0, yeast_g=7.0, yeast_tol_g=0.7, water_g=30.0, water_tol_g=2.0, activate_wait_s=60.0)
    return [
        Step('TRANSFER', dict(beaker='P1', src='carousel_pick', dst='scale_pan'), '1 P1 carousel -> scale'),
        Step('POUR_TO_SCALE', dict(reagent='developer', beaker='P1', target_g=r['developer_g'], tol_g=r['developer_tol_g'], relative=False),
             '2 developer onto P1'),
        Step('POUR_TO_FUNNEL', dict(beaker='P1'), '3 P1 -> funnel'),
        Step('TRANSFER', dict(beaker='P1', src='scale_pan', dst='carousel_pick'), '4 P1 -> carousel'),
        Step('DOSE_YEAST', dict(beaker='P2', target_g=r['yeast_g'], tol_g=r['yeast_tol_g'], max_topups=2), '5 yeast dose into P2'),
        Step('TRANSFER', dict(beaker='P2', src='carousel_pick', dst='scale_pan'), '6 P2 -> scale'),
        Step('VERIFY_MASS', dict(beaker='P2', target_g=r['yeast_g'], tol_g=r['yeast_tol_g']), '6 verify yeast'),
        Step('POUR_TO_SCALE', dict(reagent='water', beaker='P2', target_g=r['water_g'], tol_g=r['water_tol_g'], relative=True), '7 water onto P2'),
        Step('WAIT', dict(seconds=r['activate_wait_s'], reason='yeast activation'), '7 activate'),
        Step('POUR_TO_FUNNEL', dict(beaker='P2'), '8 P2 -> funnel (reaction starts)'),
        Step('TRANSFER', dict(beaker='P2', src='scale_pan', dst='carousel_pick'), '9 P2 -> carousel'),
        Step('STAGE', dict(position='ERUPT'), '10 ERUPT'),
    ]


def validate(steps, initial=None):
    """deterministic check of a step list. Simulates where each beaker is and what it holds (estimated masses) and
    returns (ok, problems: list of str). ``initial``: dict beaker -> location (default demo loading)."""
    loc = dict(initial or {'P1': 'carousel_pick', 'P2': 'carousel_aux', 'dev': 'rack_1', 'water': 'rack_3'})
    content = {b: 0.0 for b in loc}; flask_ml = 15.0; problems = []; stage = 'WORK'; on_scale = None; yeast_in = {}
    for i, st in enumerate(steps):
        p = st.params; tag = 'step %d (%s)' % (i + 1, st.type)
        if st.type not in STEP_TYPES: problems.append('%s: unknown step type' % tag); continue
        if stage == 'ERUPT': problems.append('%s: nothing may run after ERUPT' % tag)
        def need(*keys):
            miss = [k for k in keys if k not in p]
            if miss: problems.append('%s: missing %s' % (tag, ', '.join(miss)))
            return not miss
        if st.type == 'TRANSFER':
            if not need('beaker', 'src', 'dst'): continue
            if p['beaker'] not in CAROUSEL_BEAKERS: problems.append('%s: only P1/P2 can be transferred' % tag)
            if {p['src'], p['dst']} != set(STATIONS): problems.append('%s: transfers run carousel_pick <-> scale_pan only' % tag)
            if loc.get(p['beaker']) != p['src']: problems.append('%s: %s is at %s, not %s' % (tag, p['beaker'], loc.get(p['beaker']), p['src']))
            if p['dst'] == 'scale_pan' and on_scale not in (None, p['beaker']): problems.append('%s: scale occupied by %s' % (tag, on_scale))
            if p['dst'] == 'carousel_pick' and any(l == 'carousel_pick' for b, l in loc.items() if b != p['beaker']):
                problems.append('%s: pick pocket occupied' % tag)
            loc[p['beaker']] = p['dst']; on_scale = p['beaker'] if p['dst'] == 'scale_pan' else (None if on_scale == p['beaker'] else on_scale)
        elif st.type == 'POUR_TO_SCALE':
            if not need('reagent', 'beaker', 'target_g', 'tol_g'): continue
            if p['reagent'] not in REAGENTS: problems.append('%s: unknown reagent %s' % (tag, p['reagent']))
            if on_scale != p['beaker']: problems.append('%s: %s is not on the scale' % (tag, p['beaker']))
            if not 1.0 <= p['target_g'] <= LIMITS['max_pour_g']: problems.append('%s: target %.1f g outside 1..%.0f' % (tag, p['target_g'], LIMITS['max_pour_g']))
            if p['tol_g'] < LIMITS['min_tol_g']: problems.append('%s: tolerance below %.1f g' % (tag, LIMITS['min_tol_g']))
            content[p['beaker']] = content.get(p['beaker'], 0.0) + p['target_g']
            if content[p['beaker']] > LIMITS['max_beaker_ml']: problems.append('%s: %s would hold %.0f g (> %.0f)' % (tag, p['beaker'], content[p['beaker']], LIMITS['max_beaker_ml']))
            if p['reagent'] == 'water' and p['beaker'] in yeast_in and not p.get('relative', False):
                problems.append('%s: water onto yeast must be relative to the yeast mass' % tag)
        elif st.type == 'POUR_TO_FUNNEL':
            if not need('beaker'): continue
            if on_scale != p['beaker']: problems.append('%s: the funnel pour picks %s from the scale' % (tag, p['beaker']))
            if stage != 'WORK': problems.append('%s: the stage must be at WORK' % tag)
            flask_ml += content.get(p['beaker'], 0.0); content[p['beaker']] = 0.0
            if flask_ml > LIMITS['max_flask_ml']: problems.append('%s: flask would hold %.0f mL (> %.0f)' % (tag, flask_ml, LIMITS['max_flask_ml']))
        elif st.type == 'CAROUSEL':
            if not need('beaker', 'station'): continue
            if p['station'] not in ('pick', 'auger'): problems.append('%s: station must be pick or auger' % tag)
            if loc.get(p['beaker'], '').startswith('scale'): problems.append('%s: %s is on the scale' % (tag, p['beaker']))
        elif st.type == 'DOSE_YEAST':
            if not need('beaker', 'target_g', 'tol_g'): continue
            if p['beaker'] not in CAROUSEL_BEAKERS or loc.get(p['beaker']) == 'scale_pan': problems.append('%s: %s must be in the carousel' % (tag, p['beaker']))
            if not 0.5 <= p['target_g'] <= LIMITS['max_yeast_g']: problems.append('%s: yeast %.1f g outside 0.5..%.0f' % (tag, p['target_g'], LIMITS['max_yeast_g']))
            if p.get('max_topups', 0) > LIMITS['max_topups']: problems.append('%s: at most %d top-ups' % (tag, LIMITS['max_topups']))
            content[p['beaker']] = content.get(p['beaker'], 0.0) + p['target_g']; yeast_in[p['beaker']] = p['target_g']
            loc[p['beaker']] = 'carousel_pick'
            for b, l in loc.items():
                if b != p['beaker'] and l == 'carousel_pick': loc[b] = 'carousel_aux'
        elif st.type == 'VERIFY_MASS':
            if not need('beaker', 'target_g', 'tol_g'): continue
            if on_scale != p['beaker']: problems.append('%s: %s is not on the scale' % (tag, p['beaker']))
        elif st.type == 'WAIT':
            if not need('seconds'): continue
            if not 0 <= p['seconds'] <= LIMITS['max_wait_s']: problems.append('%s: wait outside 0..%.0f s' % (tag, LIMITS['max_wait_s']))
        elif st.type == 'STAGE':
            if not need('position'): continue
            if p['position'] not in ('WORK', 'ERUPT'): problems.append('%s: position must be WORK or ERUPT' % tag)
            if p['position'] == 'ERUPT' and flask_ml <= 15.0: problems.append('%s: ERUPT with nothing poured into the flask' % tag)
            stage = p['position']
    return (not problems), problems
