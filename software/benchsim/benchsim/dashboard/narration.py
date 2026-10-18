"""Judge-facing words for each step: what is happening, which chemical goes where, and why. Pure functions of a
Step dict ({type, params, label}); no simulator or backend access.

Clearances are the tightest verified margin of the step (docs/demo_process.md section 4, Update 13). The twin panel
compares the live arm error against them.
"""

REAGENT = {
    'developer': dict(name='hydrogen peroxide', formula='H₂O₂', note='12 % "developer"', species='developer'),
    'water': dict(name='warm water', formula='H₂O', note='activates the yeast', species='water'),
}
YEAST = dict(name='dry yeast', note='the catalyst: its catalase enzyme splits the peroxide', species='yeast')
STATION = {'carousel_pick': 'carousel', 'scale_pan': 'scale', 'pick': 'pick pocket', 'auger': 'auger'}
ARM_OF = {'TRANSFER': 'transfer', 'POUR_TO_SCALE': 'pourer', 'POUR_TO_FUNNEL': 'pourer'}

# (mm, what it is between) per step type / reagent, demo_process 4
CLEARANCE = {
    'TRANSFER': (7.9, 'transfer arm vs scale pan'),
    ('POUR_TO_SCALE', 'developer'): (6.2, 'pourer vs reagent rack'),
    ('POUR_TO_SCALE', 'water'): (5.8, 'pourer vs reagent rack'),
    'POUR_TO_FUNNEL': (5.3, 'held beaker vs funnel'),
    'DOSE_YEAST': (18.9, 'parked arms vs frame'),
    'CAROUSEL': (18.9, 'parked arms vs frame'),
}
REACTION = dict(equation='2 H₂O₂ → 2 H₂O + O₂',
                text='Catalase in the yeast splits the hydrogen peroxide into water and oxygen. The soap traps the oxygen '
                     'as foam, and the reaction gives off heat.')


def clearance(step):
    t = step['type']; p = step.get('params', {})
    c = CLEARANCE.get((t, p.get('reagent'))) or CLEARANCE.get(t)
    return None if c is None else dict(mm=c[0], between=c[1])


def describe(step):
    """-> dict(title, detail, arm, chemical, amount_g, tol_g, science, clearance)"""
    t = step['type']; p = step.get('params', {}); out = dict(arm=ARM_OF.get(t), chemical=None, amount_g=None, tol_g=p.get('tol_g'),
                                                            science=None, clearance=clearance(step))
    if t == 'TRANSFER':
        out['title'] = 'Moving beaker %s to the %s' % (p['beaker'], STATION.get(p['dst'], p['dst']))
        out['detail'] = ('Transfer arm, top-down grasp. The gripper closes until the fingers stop on the beaker, and '
                         'the jaw angle shows whether it really holds it.')
    elif t == 'POUR_TO_SCALE':
        r = REAGENT.get(p['reagent'], dict(name=p['reagent'], formula='', note='', species=p['reagent']))
        out.update(title='Weighing out %g g of %s' % (p['target_g'], r['name']), chemical=r, amount_g=p['target_g'])
        out['detail'] = ('Pourer arm tilts the %s beaker over %s on the scale. Closed loop: the 80 Hz load cell steers '
                         'the tilt and cuts the stream just before the target.' % (r['name'], p['beaker']))
    elif t == 'POUR_TO_FUNNEL':
        if p['beaker'] == 'P2':
            out['title'] = 'Pouring the activated yeast into the flask: the reaction starts'
            out['science'] = REACTION; out['chemical'] = YEAST
        else:
            out['title'] = 'Pouring the hydrogen peroxide into the flask'
            out['chemical'] = REAGENT['developer']
        out['detail'] = 'Pourer arm empties %s through the funnel. Soap and dye are already in the flask.' % p['beaker']
        if p.get('erupt') and p['beaker'] != 'P2':
            # the live-demo plan (steps.flask_demo_protocol): the yeast went into the flask by hand, so the peroxide starts it
            out['science'] = REACTION
            out['detail'] = 'Pourer arm empties %s through the funnel. Soap, dye and the yeast mixed with warm water are already in the flask.' % p['beaker']
        if p.get('erupt'):
            out['title'] = out['title'].split(':')[0] + ', then ERUPTION: the sled carries the flask toward you'
            out['detail'] += (' As soon as the arm has lifted the beaker clear, a crank slides the flask 97 mm toward the audience; '
                              'the arm carries the beaker back after that.')
    elif t == 'DOSE_YEAST':
        out.update(title='Dosing %g g of dry yeast with the auger' % p['target_g'], chemical=YEAST, amount_g=p['target_g'])
        out['detail'] = ('The carousel turns %s under the auger. The screw turns a counted number of revolutions, and the '
                         'scale checks the mass afterwards (up to %d top-ups).' % (p['beaker'], p.get('max_topups', 0)))
    elif t == 'VERIFY_MASS':
        what = 'empty' if p['target_g'] == 0 else '%g ± %g g' % (p['target_g'], p['tol_g'])
        out.update(title='Checking %s on the scale: %s' % (p['beaker'], what), amount_g=p['target_g'])
        out['detail'] = 'The scale reading minus the beaker tare must be within tolerance, or the run stops safely.'
    elif t == 'WAIT':
        out['title'] = 'Waiting %g s: %s' % (p['seconds'], p.get('reason', ''))
        out['detail'] = 'Warm water wakes the yeast up so the catalase is active before it meets the peroxide.'
    elif t == 'STAGE':
        if p['position'] == 'ERUPT':
            out['title'] = 'ERUPTION: the sled carries the flask toward you'; out['science'] = REACTION
            out['detail'] = 'A crank on the stage servo slides the flask 97 mm toward the audience.'
        else:
            out['title'] = 'Stage back to the work position'; out['detail'] = 'Crank to its dead centre at 0 deg.'
    elif t == 'CAROUSEL':
        out['title'] = 'Turning the carousel: %s to the %s' % (p['beaker'], STATION.get(p['station'], p['station']))
        out['detail'] = 'The Arduino Mega drives the carousel servo along a smooth profile.'
    else:
        out['title'] = step.get('label') or t; out['detail'] = ''
    return out
