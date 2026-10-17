"""Execute a planned arm task (a list of segments from benchsim.poses or a hardware trajectory file) through the
backend interfaces, with grasp classification and observed-state checks. MuJoCo-independent.

Checks: the other arm must be parked before the active arm moves; every close is classified from the jaw angle
(miss / ambiguous fail the task); after a lift the jaw must still be at its contact angle; a beaker lifted off or
placed on the scale must change the scale reading by at least ``scale_delta_min_g``.
"""
import math

from .motion import MotionFault, arm_hold, assert_parked, close_and_classify, follow, gripper_to


class TaskFailed(RuntimeError):
    def __init__(self, code, detail, record):
        super().__init__('%s: %s' % (code, detail)); self.code = code; self.detail = detail; self.record = record


class Executor:
    def __init__(self, arms, clock, gripper_cfg, park_q, scale=None, events=None, speed_deg_s=40.0, on_tick=None, on_segment=None):
        self.arms = arms; self.clock = clock; self.g = gripper_cfg; self.park = park_q; self.scale = scale
        self.events = events if events is not None else []; self.speed = speed_deg_s; self.on_tick = on_tick; self.on_segment = on_segment

    def log(self, kind, **kw):
        self.events.append(dict(t=round(self.clock.now(), 3), kind=kind, **kw))

    def expected_contact(self, grasp):
        return math.radians(self.g['contact_deg_td'] if grasp.startswith('grasp_td') else self.g['contact_deg_side'])

    def run(self, arm_name, segs, scale_station=None, label='', start_holding=None):
        """run all segments; scale_station: 'src' | 'dst' | None tells which end sits on the scale.
        start_holding: grasp site name when the arm already holds a beaker (continuing a task after a pour)"""
        arm = self.arms[arm_name]; rec = dict(task=label, arm=arm_name, segments=[], grasps=[], scale=[])
        for other, a in self.arms.items():
            if other != arm_name: assert_parked(a, self.park)
        expected = None; picked = False
        if start_holding:
            expected = self.expected_contact(start_holding); picked = True; rec['_m_before'] = None
            hold_q6 = expected - math.radians(self.g['squeeze_deg'])
        for k, sg in enumerate(segs):
            t0 = self.clock.now()
            try:
                if sg['kind'] == 'grip' and sg['gripper'] == 'close':
                    expected = self.expected_contact(sg['grasp'])
                    m_before = self.scale() if (self.scale and scale_station == 'src') else None
                    gr = close_and_classify(arm, self.clock, expected, expected - math.radians(self.g['squeeze_deg']),
                                            self.g['contact_tol_deg'], self.g['miss_margin_deg'])
                    rec['grasps'].append(gr.__dict__); self.log('grasp', arm=arm_name, outcome=gr.outcome, jaw_deg=gr.jaw_deg, expected_deg=gr.expected_deg)
                    if gr.outcome != 'grasped':
                        self._abort_open(arm, segs[:k]); raise TaskFailed('GRASP_MISS' if gr.outcome == 'miss' else 'GRASP_AMBIGUOUS', gr.detail, rec)
                    picked = True; rec['_m_before'] = m_before; hold_q6 = expected - math.radians(self.g['squeeze_deg'])
                elif sg['kind'] == 'grip' and sg['gripper'] == 'open':
                    m_before = rec.pop('_m_air', None)
                    jaw = gripper_to(arm, sg['qs'][-1][5], self.clock)
                    if math.degrees(abs(jaw - sg['qs'][-1][5])) > 2.0: raise TaskFailed('JAW_STUCK', 'jaw at %.1f deg' % math.degrees(jaw), rec)
                    self.log('release', arm=arm_name, jaw_deg=round(math.degrees(jaw), 2))
                    if m_before is not None:
                        self.clock.sleep(0.5); m_after = self.scale(); rec['scale'].append(dict(event='place', before_g=round(m_before, 2), after_g=round(m_after, 2)))
                        if m_after - m_before < self.g['scale_delta_min_g']: raise TaskFailed('PLACE_NOT_SEEN', 'scale rose %.2f g' % (m_after - m_before), rec)
                    picked = False
                else:
                    qs = sg['qs']
                    if picked:                           # keep the jaw at the grasp command, not the plan's nominal value
                        qs = [q.copy() for q in qs]
                        for q in qs: q[5] = hold_q6
                    if picked and self.scale and scale_station == 'dst' and sg['name'].startswith('lower'):
                        rec['_m_air'] = self.scale()
                    follow(arm, qs, self.clock, speed_deg_s=self.speed, on_tick=self.on_tick)
                    if picked and sg['phase'] == 'carry' and sg['name'].startswith('lift'):
                        jaw = arm.read_positions()[5]
                        if math.degrees(abs(jaw - expected)) > self.g['contact_tol_deg']:
                            raise TaskFailed('DROPPED', 'jaw moved to %.1f deg after the lift' % math.degrees(jaw), rec)
                        if rec.get('_m_before') is not None:
                            self.clock.sleep(0.5); m_after = self.scale(); rec['scale'].append(dict(event='lift', before_g=round(rec['_m_before'], 2), after_g=round(m_after, 2)))
                            if rec['_m_before'] - m_after < self.g['scale_delta_min_g']: raise TaskFailed('LIFT_NOT_SEEN', 'scale fell %.2f g' % (rec['_m_before'] - m_after), rec)
            except MotionFault as e:
                raise TaskFailed(e.code, e.detail, rec)
            rec['segments'].append(dict(name=sg['name'], kind=sg['kind'], t_start=round(t0, 3), t_end=round(self.clock.now(), 3)))
            if self.on_segment: self.on_segment(arm_name, sg, k)
        rec.pop('_m_before', None)
        return rec

    def _abort_open(self, arm, done_segs):
        """a failed grasp: open the jaw and back out along the executed approach, then park"""
        gripper_to(arm, self.expected_contact('grasp_td') + math.radians(12), self.clock)
        back = [q for sg in reversed(done_segs) for q in reversed(sg['qs'])]
        if back:
            back = [q.copy() for q in back]
            for q in back: q[5] = arm.read_positions()[5]
            try: follow(arm, back, self.clock, speed_deg_s=self.speed * 0.5, on_tick=self.on_tick)
            except MotionFault: arm_hold(arm)
        self.log('abort_retreat', arm=getattr(arm, 'name', ''))
