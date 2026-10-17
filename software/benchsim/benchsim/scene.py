"""Build the bench MuJoCo model from the layout config (MjSpec). All inputs in mm; ``units.m`` converts.

Every bench part is registered in ``FIDELITY`` with how it is represented: an imported CAD mesh (``cad-mesh``),
an imported upstream mesh (``upstream-mesh``), procedural geometry (``procedural``) or an analytic model
(``analytic``). Collision geometry is always primitive or a convex hull and is listed separately.

Collision classes (contype/conaffinity bits): 1 static bench, 2 stage, 4 carousel, 8 scale pan; arms, fingers
and beakers use 15 so they touch everything while the moving fixtures do not fight the static frame.
"""
import json
import math

import mujoco
import numpy as np

from . import assets, cadmap, layout, meshes, paths
from .units import m

ARMS = ('pourer', 'transfer')
BEAKERS = {                                        # name -> initial station (demo_process 5.2)
    'P1': 'carousel_pocket_0', 'P2': 'carousel_pocket_1', 'dev': 'rack_1', 'water': 'rack_3',
}
STATIC, STAGE, CAROUSEL, PAN, ALL = 1, 2, 4, 8, 15
FRAME_RGBA = (0.62, 0.64, 0.67, 1)
PLA = (0.93, 0.93, 0.93, 1)
PLA_DARK = (0.25, 0.27, 0.30, 1)
TPU = (0.15, 0.55, 0.85, 1)
GLASS = (0.75, 0.88, 0.95, 0.35)
PP = (0.92, 0.95, 0.97, 0.45)


def quat_z(deg):
    a = math.radians(deg) / 2
    return [math.cos(a), 0, 0, math.sin(a)]


def mat_to_quat(R):
    q = np.zeros(4); mujoco.mju_mat2Quat(q, np.asarray(R, float).reshape(9)); return q


class Fidelity:
    def __init__(self): self.rows = []

    def add(self, part, visual, collision, source, note=''):
        self.rows.append(dict(part=part, visual=visual, collision=collision, source=source, note=note))


class Builder:
    def __init__(self, bench=None):
        self.bench = bench or layout.load_bench()
        self.P = self.bench['params']; self.st = self.bench['stations']
        self.spec = mujoco.MjSpec(); self.spec.modelname = 'wet_lab_bench'
        self.fid = Fidelity(); self.meta = {'beakers': {}, 'arms': {}, 'stations': {}}
        self._mesh_n = 0

    # ---------------------------------------------------------------- primitives (mm in)
    def geom(self, body, kind, size_mm, pos_mm=(0, 0, 0), quat=(1, 0, 0, 0), rgba=PLA, name=None, cls=STATIC,
             collide=True, group=0, **kw):
        g = body.add_geom(type=kind, size=list(m(np.asarray(size_mm, float))) + [0] * (3 - len(size_mm)), pos=m(pos_mm),
                          quat=list(quat), rgba=list(rgba), group=group)
        if name: g.name = name
        g.contype = cls if collide else 0; g.conaffinity = cls if collide else 0
        for k, v in kw.items(): setattr(g, k, v)
        return g

    def box(self, body, c, half, **kw): return self.geom(body, mujoco.mjtGeom.mjGEOM_BOX, half, c, **kw)

    def cyl(self, body, c, r, half_h, **kw): return self.geom(body, mujoco.mjtGeom.mjGEOM_CYLINDER, [r, half_h], c, **kw)

    def mesh(self, body, V_mm, F, rgba=PLA, name=None, collide=False, cls=STATIC, pos=(0, 0, 0), quat=(1, 0, 0, 0), spec=None, group=1):
        spec = spec or self.spec; self._mesh_n += 1
        mname = name or 'mesh%d' % self._mesh_n
        spec.add_mesh(name=mname, uservert=list(m(np.asarray(V_mm, float)).reshape(-1)), userface=list(np.asarray(F, int).reshape(-1)))
        g = body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=mname, rgba=list(rgba), pos=m(pos), quat=list(quat), group=group)
        g.contype = cls if collide else 0; g.conaffinity = cls if collide else 0
        return g

    def ring_walls(self, body, c, r_in, r_out, z0, z1, n=24, cls=STATIC, rgba=PLA, collide=True, name=None):
        """hollow cylinder wall from n boxes (collision for pockets, cups and beaker walls)"""
        rm = (r_in + r_out) / 2; t = (r_out - r_in) / 2; w = rm * math.tan(math.pi / n) + 0.3
        for i in range(n):
            a = 2 * math.pi * i / n
            self.box(body, (c[0] + rm * math.cos(a), c[1] + rm * math.sin(a), (z0 + z1) / 2), (t, w, (z1 - z0) / 2),
                     quat=quat_z(math.degrees(a)), cls=cls, rgba=rgba, collide=collide, name=None if name is None else '%s_w%d' % (name, i))

    # ---------------------------------------------------------------- bench
    def world(self):
        s = self.spec; s.option.timestep = self.P['world']['timestep_s']
        s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        s.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC; s.option.noslip_iterations = 2
        s.visual.global_.offwidth = 1280; s.visual.global_.offheight = 720
        s.visual.headlight.ambient = [0.35, 0.35, 0.35]; s.visual.headlight.diffuse = [0.5, 0.5, 0.5]
        s.stat.center = list(m([500, 420, 120])); s.stat.extent = 0.9
        wb = s.worldbody
        x0, y0, x1, y1 = self.P['world']['table_xy']
        self.box(wb, ((x0 + x1) / 2, (y0 + y1) / 2, -10), ((x1 - x0) / 2, (y1 - y0) / 2, 10), rgba=(0.55, 0.45, 0.35, 1), name='table')
        wb.add_light(pos=m([500, 300, 1500]), dir=[0, 0.2, -1], diffuse=[0.6, 0.6, 0.6], castshadow=True)
        wb.add_light(pos=m([200, -400, 900]), dir=[0.3, 0.6, -0.6], diffuse=[0.3, 0.3, 0.3], castshadow=False)
        self.fid.add('table', 'procedural', 'box', 'bench_params.toml world.table_xy (assumed extent)')

    def frame(self):
        F = self.P['frame']; wb = self.spec.worldbody; h = F['section'] / 2; z = F['rail_top_z'] - h
        for name, (xa, ya, xb, yb) in F['rails'].items():
            self.box(wb, ((xa + xb) / 2, (ya + yb) / 2, z), ((xb - xa) / 2, (yb - ya) / 2, h), rgba=FRAME_RGBA, name='rail_' + name)
        self.fid.add('frame rails (X-front, X-back, Y-left, Y-right, E6, S1, S2)', 'procedural', 'box per rail',
                     'update13_final X_rails + demo_process 2.2 + tools/cad/stage_a.py', 'solid 20x20 boxes, no T-slots; E5 omitted (placement not recorded)')

    def scale(self):
        S = self.P['scale']; st = self.st['scale_pan']; wb = self.spec.worldbody
        cx, cy = st['xy']; floor = st['z']
        bx0, bx1 = S['saddle_x']; by = 430.0 - S['base_size'][1] / 2          # WS-01 on the E6 south face
        self.box(wb, ((bx0 + bx1) / 2, by + 10, S['base_size'][2] / 2), ((bx1 - bx0) / 2, S['base_size'][1] / 2 - 10, S['base_size'][2] / 2),
                 rgba=PLA, name='ws01_base')
        self.box(wb, (cx, (cy + by) / 2 + 12, floor - S['pan_height'] + 4 - 8), (6.35, (by - cy) / 2 + 6, 6.35), rgba=(0.7, 0.7, 0.72, 1),
                 name='load_cell', collide=False)
        pan = wb.add_body(name='scale_pan', pos=m([cx, cy, 0]))
        j = pan.add_joint(name='scale_flex', type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0, 0, 1])
        k = S['stiffness_n_per_m']; mass = S['pan_mass_g'] / 1000
        j.stiffness = [k, 0, 0]; j.damping = [2 * S['damping_ratio'] * math.sqrt(k * 0.15), 0, 0]; j.range = [-0.003, 0.003]; j.armature = 0.0
        pan.mass = mass; pan.inertia = [2e-5, 2e-5, 3e-5]; pan.explicitinertial = True
        t = 6.0
        self.cyl(pan, (0, 0, floor - t / 2), S['pan_od'] / 2, t / 2, cls=PAN, rgba=PLA, name='scale_pan_floor')
        self.ring_walls(pan, (0, 0), S['ring_id'] / 2, S['ring_id'] / 2 + 2.0, floor, floor + S['pan_height'] - t, n=20, cls=PAN, name='scale_ring')
        pan.add_site(name='scale_centre', pos=m([0, 0, floor]))
        self.spec.add_sensor(name='scale_flex', type=mujoco.mjtSensor.mjSENS_JOINTPOS, objtype=mujoco.mjtObj.mjOBJ_JOINT, objname='scale_flex')
        self.fid.add('scale WS-01 base, load cell', 'procedural', 'box', 'update13_final scale.mount (saddle X 547-664) + WS-01 STL extent')
        self.fid.add('scale pan WS-02 v3', 'procedural', 'cylinder floor + 20-box locating ring', 'update13_final scale.pan, WS-02 STL extent')
        self.fid.add('load cell signal', 'analytic', '-', 'slide-joint flexure (k, zeta) + HX711 noise/quantisation', 'see benchsim.backends.sim')
        self.meta['stations']['scale'] = dict(xy=[cx, cy], bottom_z=floor)

    def carousel(self):
        C = self.P['carousel']; c = self.st['carousel_centre']['xy']; wb = self.spec.worldbody
        bx, by, bz = C['base_size']
        self.box(wb, (c[0], c[1], bz / 2), (bx / 2.6, by / 2.6, bz / 2), rgba=PLA_DARK, name='tt01_base')
        self.cyl(wb, (c[0], c[1], (bz + C['deck_z'][0]) / 2), 60.0, (C['deck_z'][0] - bz) / 2, rgba=(0.3, 0.3, 0.3, 1), name='lazy_susan', collide=False)
        deck = wb.add_body(name='carousel', pos=m([c[0], c[1], 0]))
        j = deck.add_joint(name='carousel', type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, 1], damping=[0.5, 0, 0], armature=0.01)
        j.range = list(np.radians(C['deck_range_deg']))
        deck.mass = 0.35; deck.inertia = [2e-3, 2e-3, 4e-3]; deck.explicitinertial = True
        z0, z1 = C['deck_z']
        self.cyl(deck, (0, 0, (z0 + z1) / 2), C['deck_od'] / 2, (z1 - z0) / 2, cls=CAROUSEL, rgba=PLA, name='tt02_deck')
        rz0, rz1 = C['ring_z']; floor = self.st['carousel_pick']['z']
        self.cyl(deck, (0, 0, (rz0 + floor) / 2), C['ring_od'] / 2, (floor - rz0) / 2, cls=CAROUSEL, rgba=(0.95, 0.75, 0.2, 1), name='tt04_floor')
        pockets = []
        for k, a in enumerate(C['pocket_ids_deg']):
            p = (C['pitch_r'] * math.cos(math.radians(a)), C['pitch_r'] * math.sin(math.radians(a)))
            self.ring_walls(deck, p, C['pocket_inner_r'], C['pocket_wall_r'], floor, rz1, n=20, cls=CAROUSEL, rgba=(0.95, 0.75, 0.2, 1),
                            name='pocket%d' % k)
            deck.add_site(name='pocket%d' % k, pos=m([p[0], p[1], floor]))
            pockets.append(dict(angle_deg=a, local_xy=p))
        a = self.spec.add_actuator(name='carousel', target='carousel', trntype=mujoco.mjtTrn.mjTRN_JOINT)
        a.set_to_position(kp=8.0, kv=1.0); a.forcerange = [-4.4, 4.4]; a.forcelimited = True    # M45CHW ~45 kg.cm
        a.ctrlrange = list(np.radians(C['deck_range_deg'])); a.ctrllimited = True
        self.meta['stations']['carousel'] = dict(centre=c, pockets=pockets, floor_z=floor)
        self.fid.add('carousel TT-01/TT-02/TT-04 v4', 'procedural', 'cylinders + 20-box pocket walls',
                     'update13_final carousel + layout_final.py pocket walls r28.3-30.3', 'deck on a hinge with a position servo')

    def auger(self):
        A = self.P['auger']; C = self.P['carousel']; c = self.st['carousel_centre']['xy']; p = self.st['carousel_auger']['xy']
        wb = self.spec.worldbody
        u = np.array([p[0] - c[0], p[1] - c[1]]); u /= np.linalg.norm(u)
        ang = math.degrees(math.atan2(u[1], u[0]))
        post = np.array(p) + u * (C['pocket_wall_r'] + 22 + A['post_size'][0] / 2 + 30)
        pw, pd, ph = A['post_size']
        self.box(wb, (post[0], post[1], ph / 2), (pw / 2, pd / 2, ph / 2), quat=quat_z(ang), rgba=PLA, name='ps01_post')
        hl = np.linalg.norm(post - np.array(p)) + 25; hc = (post + np.array(p)) / 2 + u * 12
        self.box(wb, (hc[0], hc[1], A['outlet_z'] + 22), (hl / 2, 24, 22), quat=quat_z(ang), rgba=(0.9, 0.5, 0.2, 1), name='dh01_head')
        self.cyl(wb, (p[0], p[1], A['outlet_z'] + 4), A['outlet_d'] / 2 + 2, 4, rgba=(0.9, 0.5, 0.2, 1), name='dh01_outlet')
        wb.add_site(name='auger_outlet', pos=m([p[0], p[1], A['outlet_z']]))
        self.fid.add('auger PS-01 post + DH-01 head', 'procedural', 'box', 'outlet over update13_final carousel.auger at Z 169.5 (demo_process step 5)',
                     'post/head placement radial from the pocket, not from CAD; screw not modelled')
        self.fid.add('auger dosing', 'analytic', '-', 'g/rev x revolutions with CV, stall rule (electrical.md 6)')

    def rack(self):
        R = self.P['rack']; B = self.P['beaker']; wb = self.spec.worldbody; z0 = self.st['rack_1']['z']
        cups = [self.st['rack_%d' % i]['xy'] for i in (1, 2, 3)]
        rin = R['cup_inner_r']; rout = rin + R['cup_wall']; base = z0 - 3.0
        for i, c in enumerate(cups):
            self.cyl(wb, (c[0], c[1], base / 2 + 1.5), rout, (base + 3) / 2, rgba=PLA, name='rk03_cup%d_post' % (i + 1))
            self.ring_walls(wb, c, rin, rout, z0, z0 + 22.0, n=20, name='rk03_cup%d' % (i + 1))
            wb.add_site(name='rack_%d' % (i + 1), pos=m([c[0], c[1], z0]))
        for a, b in zip(cups[:-1], cups[1:]):
            d = np.subtract(b, a); L = np.linalg.norm(d); mid = (np.add(a, b)) / 2
            self.box(wb, (mid[0], mid[1], z0 - 6), (L / 2 - rout + 2, 4, 5), quat=quat_z(math.degrees(math.atan2(d[1], d[0]))), name=None)
        self.box(wb, (240.0, (cups[0][1] + cups[2][1]) / 2, 30), (5, (cups[2][1] - cups[0][1]) / 2 + 30, 30), name='rk03_spine')
        self.fid.add('reagent rack RK-03', 'procedural', 'cup posts + 20-box cup walls + webs + spine',
                     'update13_final rack_stands + rack_beaker_bottom_z', 'cup walls 22 mm tall around the beaker; spine on the Y-left west face')

    def stage(self):
        S = self.P['stage']; Fl = self.P['flask']; Fu = self.P['funnel']; wb = self.spec.worldbody
        cc = S['crank_centre']; r = S['crank_r']; L = S['rod_l']; fun = self.st['funnel']
        pin_work = cc[1] + r + L
        self.box(wb, (450, 65, 23.6), (93, 30.5, 3.6), rgba=PLA, name='st12_bridge', cls=STAGE)
        crank = wb.add_body(name='crank', pos=m([cc[0], cc[1], 51]))
        jc = crank.add_joint(name='crank', type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, 1], damping=[0.2, 0, 0], armature=0.005)
        jc.range = [math.radians(-5), math.radians(160)]
        self.box(crank, (0, r / 2, 0), (7, r / 2 + 6, 3), rgba=PLA_DARK, cls=STAGE, collide=False, name='st13_crank')
        rod = crank.add_body(name='rod', pos=m([0, r, 7]))
        rod.add_joint(name='rod', type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, 1], damping=[0.01, 0, 0])
        self.box(rod, (0, L / 2, 0), (7, L / 2 + 8, 3), rgba=PLA_DARK, collide=False, name='st14_rod')
        sled = wb.add_body(name='sled', pos=m([fun['xy'][0], fun['xy'][1], 0]))
        js = sled.add_joint(name='sled', type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0, 1, 0], damping=[5.0, 0, 0])
        js.range = [-0.115, 0.005]
        sled.mass = 0.6; sled.inertia = [3e-3, 3e-3, 3e-3]; sled.explicitinertial = True
        z0, z1 = S['sled_plate_z']; sx, sy = S['sled_size_xy']
        self.box(sled, (0, 0, (z0 + z1) / 2), (sx / 2, sy / 2, (z1 - z0) / 2), cls=STAGE, rgba=PLA, name='st11_sled')
        pin_local = (0.0, pin_work - fun['xy'][1], 58.0 - 51.0 + 51.0 - 0.0)
        sled.add_site(name='sled_pin', pos=m([0, pin_work - fun['xy'][1], 58]))
        eq = self.spec.add_equality(type=mujoco.mjtEq.mjEQ_CONNECT, name='rod_to_sled', objtype=mujoco.mjtObj.mjOBJ_BODY)
        eq.name1 = 'rod'; eq.name2 = 'sled'; eq.data[0:3] = m([0, L, 0])
        cw_od, cw_h = Fl['catch_well']; co_od, co_h = Fl['collar']
        V, F = meshes.tube(cw_od / 2 - 2.5, cw_od / 2, cw_h - 2, n=48, z0=z1 + 2); self.mesh(sled, V, F, rgba=(0.85, 0.9, 0.95, 0.5), name='st07_catch_well_vis')
        self.cyl(sled, (0, 0, z1 + 1), cw_od / 2, 1, cls=STAGE, rgba=(0.85, 0.9, 0.95, 0.6), name='st07_floor')
        V, F = meshes.tube(Fl['base_od'] / 2 + 0.5, co_od / 2, co_h, n=48, z0=z1 + 2); self.mesh(sled, V, F, rgba=PLA, name='st05_collar_vis')
        fz = z1 + 2.0; fb = Fl['base_od'] / 2; body_h = Fl['height'] - Fl['neck_h']
        V, F = meshes.frustum(fb, Fl['neck_od'] / 2, body_h, n=48, z0=fz); self.mesh(sled, V, F, rgba=GLASS, name='flask_body', collide=True, cls=STAGE)
        V, F = meshes.frustum(Fl['neck_od'] / 2, Fl['neck_od'] / 2, Fl['neck_h'], n=32, z0=fz + body_h); self.mesh(sled, V, F, rgba=GLASS, name='flask_neck', collide=True, cls=STAGE)
        rim_z = fun['z']; stem_top = rim_z - Fu['cone_h']
        V, F = meshes.frustum(Fu['stem_od'] / 2, Fu['rim_d'] / 2, Fu['cone_h'], n=48, z0=stem_top)
        self.mesh(sled, V, F, rgba=(0.9, 0.9, 0.92, 0.55), name='funnel_cone', collide=True, cls=STAGE)
        V, F = meshes.frustum(Fu['stem_od'] / 2, Fu['stem_od'] / 2 - 2, Fu['stem_h'], n=24, z0=stem_top - Fu['stem_h'])
        self.mesh(sled, V, F, rgba=(0.9, 0.9, 0.92, 0.55), name='funnel_stem')
        sled.add_site(name='funnel_rim', pos=m([0, 0, rim_z]))
        sled.add_site(name='flask_neck_top', pos=m([0, 0, fz + Fl['height']]))
        # foam column: a capsule-free cylinder whose length and position the foam model updates at run time
        self.cyl(sled, (0, 0, fz + Fl['height'] + 1), Fl['neck_od'] / 2 - 1, 0.5, rgba=(1.0, 0.45, 0.6, 0.95), collide=False, name='foam', group=1)
        self.cyl(sled, (0, 0, fz + 10), fb - 6, 1, rgba=(0.4, 0.9, 0.5, 0.6), collide=False, name='flask_liquid', group=1)
        a = self.spec.add_actuator(name='crank', target='crank', trntype=mujoco.mjtTrn.mjTRN_JOINT)
        a.set_to_position(kp=6.0, kv=0.6); a.forcerange = [-4.4, 4.4]; a.forcelimited = True
        a.ctrlrange = [math.radians(-5), math.radians(160)]; a.ctrllimited = True
        self.spec.add_sensor(name='sled_pos', type=mujoco.mjtSensor.mjSENS_JOINTPOS, objtype=mujoco.mjtObj.mjOBJ_JOINT, objname='sled')
        self.spec.add_sensor(name='crank_pos', type=mujoco.mjtSensor.mjSENS_JOINTPOS, objtype=mujoco.mjtObj.mjOBJ_JOINT, objname='crank')
        self.meta['stations']['stage'] = dict(pin_work_y=pin_work, flask_floor_z=fz, flask_height=Fl['height'])
        self.fid.add('stage ST-11 sled, ST-13 crank, ST-14 rod', 'procedural', 'sled plate box; crank/rod no collision',
                     'tools/cad/stage_b.py (crank r50 at (450,77), rod 80)', 'closed slider-crank: hinge + hinge + connect equality + slide')
        self.fid.add('flask 250 mL, ST-05 collar, ST-07 catch well', 'procedural', 'convex frustum hull (flask)', 'assumed Erlenmeyer dims; ST-05/ST-07 STL extents')
        self.fid.add('funnel', 'procedural', 'convex frustum hull', 'update13_final funnel (rim Z 233); 100 mm rim assumed', 'solid hull: conservative for clearance below the rim')
        self.fid.add('foam column', 'analytic', '-', 'benchsim.chem.foam: induction + logistic growth from reagent masses')

    # ---------------------------------------------------------------- beakers
    def beakers(self):
        B = self.P['beaker']; wb = self.spec.worldbody; C = self.meta['stations']['carousel']
        r = B['od'] / 2; h = B['height']
        for name, where in BEAKERS.items():
            if where.startswith('carousel_pocket_'):
                k = int(where.rsplit('_', 1)[1]); lp = C['pockets'][k]['local_xy']
                xy = (C['centre'][0] + lp[0], C['centre'][1] + lp[1]); z = C['floor_z']
            else:
                xy = self.st[where]['xy']; z = self.st[where]['z']
            b = wb.add_body(name='beaker_' + name, pos=m([xy[0], xy[1], z + 0.05]))
            b.add_freejoint(name='beaker_' + name)
            b.mass = B['empty_mass_g'] / 1000; b.ipos = m([0, 0, h * 0.45])
            Ixx = b.mass * (3 * (r / 1000) ** 2 + (h / 1000) ** 2) / 12 * 0.8; b.inertia = [Ixx, Ixx, b.mass * (r / 1000) ** 2]
            b.explicitinertial = True
            self.cyl(b, (0, 0, B['floor'] / 2), r, B['floor'] / 2, cls=ALL, rgba=PP, name='beaker_%s_floor' % name, friction=[0.9, 0.01, 0.001])
            self.ring_walls(b, (0, 0), r - B['wall'], r, 0, h, n=20, cls=ALL, rgba=(0.92, 0.95, 0.97, 0.0), name='beaker_%s' % name)
            V, F = meshes.tube(r - B['wall'], r, h, n=48)
            self.mesh(b, V, F, rgba=PP, name='beaker_%s_vis' % name)
            self.cyl(b, (0, 0, B['floor'] + 0.5), r - B['wall'] - 0.3, 0.5, rgba=(0.2, 0.5, 0.95, 0.8), collide=False, name='liquid_' + name, group=1)
            b.add_site(name='beaker_%s_bottom' % name, pos=[0, 0, 0])
            b.add_site(name='beaker_%s_lip' % name, pos=m([0, 0, h]))
            self.meta['beakers'][name] = dict(start=where, xy=list(map(float, xy)), bottom_z=float(z))
        self.fid.add('beakers EISCO 100 mL PP (56 x 74)', 'procedural', 'floor cylinder + 20-box hollow wall', 'demo_process 3 + DUMMY-BEAKER STL',
                     'free bodies; liquid weight applied as an external force by the chemistry model')
        self.fid.add('liquid in vessels', 'analytic', '-', 'benchsim.chem.liquid: tilted-cylinder volume, weir flow, ballistic stream')

    # ---------------------------------------------------------------- arms
    def _gripper_geometry(self):
        """fin-ray gripper meshes and finger collision boxes in the MJCF gripper and moving-jaw frames"""
        fit = cadmap.load_fit(); gd = json.loads(paths.GRIPPER_DESIGN.read_text()); gf = json.loads(paths.GRIP_FRAMES.read_text())['A']
        gp = np.array(gf['gp']); e1 = np.array(gf['e1']); e2 = np.array(gf['e2']); g = np.array(gf['g'])
        def w(P2, z):                                    # grip-plane (e1, e2, g) coordinates -> as-built world
            P2 = np.atleast_2d(P2); return gp + P2[:, :1] * e1 + P2[:, 1:2] * e2 + np.atleast_1d(z)[:, None] * g
        def plane(Pw):
            v = np.asarray(Pw) - gp; return np.c_[v @ e1, v @ e2], v @ g
        b43, qc43 = math.radians(12.5), math.radians(-60.0)
        Mir = np.array([[math.cos(2 * b43), math.sin(2 * b43)], [math.sin(2 * b43), -math.cos(2 * b43)]])
        Rq = np.array([[math.cos(-qc43), -math.sin(-qc43)], [math.sin(-qc43), math.cos(-qc43)]])
        to_moving = lambda P2: P2 @ Mir.T @ Rq.T          # gripper_design.to_moving_q0
        out = {'gripper': [], 'moving_jaw_so101_v1': []}
        for fname, body, xform, rgba in (('GR-01_gripper-body_qty2_SUPPORTS.stl', 'gripper', None, PLA_DARK),
                                         ('GR-03_fin-ray-finger_qty4_TPU.stl', 'gripper', None, TPU),
                                         ('GR-02_moving-jaw_qty2_SUPPORTS.stl', 'moving_jaw_so101_v1', None, PLA_DARK),
                                         ('GR-03_fin-ray-finger_qty4_TPU.stl', 'moving_jaw_so101_v1', 'mirror', TPU)):
            V, F = meshes.read_stl(paths.PRINTS_V2 / fname)
            if xform == 'mirror':
                P2, z = plane(V); V = w(to_moving(P2), z); F = meshes.flip(F)
            out[body].append(dict(file=fname, V=cadmap.to_body_frame(V, body, fit), F=F, rgba=rgba, mirrored=xform == 'mirror'))
        # finger contact boxes: 4 mm deep behind the contact line, over the finger's extent along the hinge
        PHI = math.radians(gd['PHI']); d = np.array([math.cos(PHI), math.sin(PHI)]); nb = np.array([math.sin(PHI), -math.cos(PHI)])
        BF = np.array(gd['B_F']); L = gd['L']; z0, z1 = gd['Z']; t = 4.0
        boxes = []
        for body, f in (('gripper', lambda P: P), ('moving_jaw_so101_v1', to_moving)):
            c2 = f((BF + d * L / 2 + nb * t / 2)[None])[0]; a2 = f((BF + d)[None])[0] - f(BF[None])[0]
            cw = w(c2, (z0 + z1) / 2)[0]; ax = a2[0] * e1 + a2[1] * e2; ax /= np.linalg.norm(ax)
            R_world = np.c_[ax, np.cross(g, ax), g]
            Rb, pb = cadmap.ArmFK(fit['pan_xy'], fit['base_z']).body_pose(body, cadmap.asbuilt_q(fit))
            boxes.append(dict(body=body, pos=(cw - pb) @ Rb, R=Rb.T @ R_world, half=[L / 2, t / 2, (z1 - z0) / 2]))
        # grasp sites in the gripper frame
        c2 = np.array(gd['grip']['56']['centre2d']); zmid = (z0 + z1) / 2
        c0 = w(c2, zmid)[0]; u0 = (c0 - gp) @ e1; palm = gd['grip']['56']['clear_palm']
        bottom_td = c0 + (palm + self.P['beaker']['height'] - u0) * e1
        Rb, pb = cadmap.ArmFK(fit['pan_xy'], fit['base_z']).body_pose('gripper', cadmap.asbuilt_q(fit))
        Rside = np.c_[e1, e2, g]; zb = -e1; xb = g - zb * (g @ zb); xb /= np.linalg.norm(xb); Rtd = np.c_[xb, np.cross(zb, xb), zb]
        sites = dict(grasp_side=((c0 - pb) @ Rb, Rb.T @ Rside), grasp_td=((bottom_td - pb) @ Rb, Rb.T @ Rtd))
        hinge = dict(pos=(gp - pb) @ Rb, axis=Rb.T @ g)
        return out, boxes, sites, hinge

    def arms(self):
        A = self.P['arm']; geo, boxes, sites, hinge = self._gripper_geometry()
        self.meta['gripper'] = dict(hinge_in_gripper_mm=np.round(hinge['pos'], 2).tolist(), hinge_axis=np.round(hinge['axis'], 4).tolist())
        q_off = math.radians(self.P['gripper']['cad_to_mj_offset_deg'])
        for arm in ARMS:
            c = mujoco.MjSpec.from_file(str(assets.model_xml()))
            for bname in ('gripper', 'moving_jaw_so101_v1'):
                b = c.body(bname)
                for gg in list(b.geoms):
                    if gg.meshname in ('wrist_roll_follower_so101_v1', 'moving_jaw_so101_v1'): c.delete(gg)
                for k, item in enumerate(geo[bname]):
                    mg = self.mesh(b, item['V'], item['F'], rgba=item['rgba'], name='%s_%s_%d' % (arm, bname, k), spec=c, group=2)
                    if item['file'].startswith(('GR-01', 'GR-02')):
                        mg2 = self.mesh(b, item['V'], item['F'], rgba=item['rgba'], name='%s_%s_%dc' % (arm, bname, k), spec=c, group=3, collide=True, cls=ALL)
            for bx in boxes:
                gg = self.box(c.body(bx['body']), bx['pos'], bx['half'], quat=mat_to_quat(bx['R']), cls=ALL, rgba=(0.1, 0.5, 0.9, 0.0),
                              name='finger_%s' % ('fixed' if bx['body'] == 'gripper' else 'moving'), group=3)
                gg.friction = [1.2, 0.02, 0.002]; gg.solref = [0.006, 1.0]; gg.solimp = [0.9, 0.98, 0.002, 0.5, 2]
            gb = c.body('gripper')
            for sname, (p, R) in sites.items():
                gb.add_site(name=sname, pos=m(p), quat=list(mat_to_quat(R)), size=[0.004, 0, 0], group=4)
            for gg in self._iter_geoms(c.worldbody):
                if gg.contype != 0 and gg.classname.name != 'visual': gg.contype = ALL; gg.conaffinity = ALL
            c.actuator('gripper').forcerange = [-A['grip_force_limit_nm'], A['grip_force_limit_nm']]
            base = self.st['%s_base' % arm]['xy']
            R = cadmap.base_rotation(A['base_yaw_deg'])
            o = np.r_[np.asarray(base) - R[:2, :2] @ np.asarray(A['pan_axis_in_base']), A['base_z']]
            fr = self.spec.worldbody.add_frame(pos=m(o), quat=quat_z(A['base_yaw_deg']))
            fr.attach_body(c.body('base'), arm + '/', '')
            self.meta['arms'][arm] = dict(base_origin_mm=o.tolist(), pan_axis_xy=list(base), yaw_deg=A['base_yaw_deg'])
        self.meta['gripper']['cad_to_mj_offset_rad'] = q_off
        self.fid.add('SO-101 arms (2x)', 'upstream-mesh', 'upstream link meshes (convex hulls)', 'TheRobotStudio/SO-ARM100 %s so101_new_calib.xml'
                     % json.loads(assets.LOCK.read_text())['revision'][:12], 'stock jaw meshes removed; actuators as upstream (kp 998, 3.35 N m)')
        self.fid.add('fin-ray gripper GR-01 body, GR-02 jaw, GR-03 fingers', 'cad-mesh',
                     'GR-01/GR-02 convex hulls + one 4 mm box per finger contact face',
                     'exports/prints_v2 GR-0x STLs (assembly coordinates, arm A as built) placed by the CAD as-built fit',
                     'moving finger = GR-03 mirrored about the 43 mm bisector and rotated (gripper_design.to_moving_q0)')

    @staticmethod
    def _iter_geoms(body):
        for g in body.geoms: yield g
        for b in body.bodies: yield from Builder._iter_geoms(b)

    def grasp_welds(self):
        for arm in ARMS:
            for bk in BEAKERS:
                e = self.spec.add_equality(type=mujoco.mjtEq.mjEQ_WELD, name='hold_%s_%s' % (arm, bk), objtype=mujoco.mjtObj.mjOBJ_BODY)
                e.name1 = '%s/gripper' % arm; e.name2 = 'beaker_' + bk; e.active = False
                e.solref = [0.004, 1.0]

    def cameras(self):
        wb = self.spec.worldbody
        def cam(name, pos, target, fovy=45):
            p = np.asarray(pos, float); f = np.asarray(target, float) - p; f /= np.linalg.norm(f)
            up = np.array([0, 0, 1.0]); x = np.cross(f, up); x /= np.linalg.norm(x); y = np.cross(x, f)
            R = np.c_[x, y, -f]
            wb.add_camera(name=name, pos=m(pos), quat=list(mat_to_quat(R)), fovy=fovy)
        cam('overview', [520, -420, 620], [520, 420, 80], 55)
        cam('top', [520, 400, 1500], [520, 401, 0], 45)
        st = self.st
        cam('foam_cam', [700, 120, 260], [450, st['funnel']['xy'][1] - 97.3, 230], 40)
        cam('bench_cam', [900, 250, 420], [680, 440, 70], 50)
        self.fid.add('cameras', 'analytic', '-', 'no documented viewpoint; poses assumed in scene.cameras')

    def build(self):
        self.world(); self.frame(); self.scale(); self.carousel(); self.auger(); self.rack(); self.stage()
        self.beakers(); self.arms(); self.grasp_welds(); self.cameras()
        self.spec.compiler.autolimits = True
        model = self.spec.compile()
        return model


def build(bench=None):
    b = Builder(bench); model = b.build()
    return model, b


if __name__ == '__main__':
    model, b = build()
    print('compiled: nbody %d njnt %d nu %d ngeom %d neq %d' % (model.nbody, model.njnt, model.nu, model.ngeom, model.neq))
    for r in b.fid.rows: print(' - %-55s %-13s %s' % (r['part'], r['visual'], r['collision']))
