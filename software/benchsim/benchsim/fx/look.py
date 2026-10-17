"""The bench look: a lab room, softer light, glossy glass, liquids coloured by what is in them, pour streams that
follow the liquid model's ballistic arc, falling yeast and an elephant-toothpaste eruption that follows the foam model.

``assets(spec)`` adds the textures and materials (all ``fx_*``) when the scene is built; nothing in the model uses them,
so plain renders (vision, verify_mechanisms) look as before. ``Look(ctx)`` is called with each frame's scene copy,
after ``update_scene`` and before ``render``, and only adds or restyles geoms in that copy.
"""
import math
import time

import mujoco
import numpy as np

from ..chem.vessels import BEAKERS
from .draw import Canvas, hash01, hash01v, lerp

# rgba of each species and how strongly it tints a mixture (per gram): a pinch of dye colours the whole flask
SPECIES = {'developer': ((0.55, 0.83, 1.00, 0.58), 1.0), 'water': ((0.30, 0.58, 1.00, 0.62), 1.0),
           'yeast': ((0.80, 0.63, 0.40, 0.96), 3.0), 'soap': ((0.96, 0.94, 0.80, 0.60), 0.3), 'dye': ((0.90, 0.10, 0.36, 1.0), 80.0)}
FOAM = (1.0, 0.99, 0.97, 1.0)
FOAM_YEAST = (1.0, 0.97, 0.91, 1.0)
FOAM_GLOW = 0.28                      # foam scatters light: a little emission keeps it bright white in the shade
DYE_STREAK = (0.99, 0.40, 0.60, 1.0)
GLASS = dict(rgba=(0.84, 0.93, 0.98, 0.28), specular=1.0, shininess=0.95)
PP = dict(rgba=(0.95, 0.97, 0.98, 0.22), specular=0.6, shininess=0.7)
FLOOR_Z = -900.0                      # the bench top is 900 mm above the lab floor


def assets(spec):
    """textures and materials for the room (fx_* only; unused unless the look is on)"""
    T = mujoco.mjtTexture.mjTEXTURE_2D; B = mujoco.mjtBuiltin; M = mujoco.mjtMark
    def tex(name, builtin, rgb1, rgb2, mark=M.mjMARK_NONE, markrgb=(0, 0, 0), random=0.0, size=512):
        spec.add_texture(name=name, type=T, builtin=builtin, rgb1=list(rgb1), rgb2=list(rgb2), mark=mark, markrgb=list(markrgb), random=random,
                         width=size, height=size)
    def mat(name, texture, repeat, specular=0.2, shininess=0.2, reflectance=0.0, rgba=(1, 1, 1, 1)):
        m = spec.add_material(name=name); tx = list(m.textures); tx[int(mujoco.mjtTextureRole.mjTEXROLE_RGB)] = texture; m.textures = tx
        m.texrepeat = list(repeat); m.texuniform = True; m.specular = specular; m.shininess = shininess; m.reflectance = reflectance; m.rgba = list(rgba)
    tex('fx_tile', B.mjBUILTIN_CHECKER, (0.93, 0.93, 0.91), (0.91, 0.92, 0.90), M.mjMARK_EDGE, (0.70, 0.71, 0.70), size=64)
    tex('fx_worktop', B.mjBUILTIN_FLAT, (0.20, 0.21, 0.22), (0.20, 0.21, 0.22), M.mjMARK_RANDOM, (0.30, 0.31, 0.32), random=0.04)
    tex('fx_floor', B.mjBUILTIN_CHECKER, (0.46, 0.48, 0.50), (0.42, 0.44, 0.46), M.mjMARK_EDGE, (0.36, 0.37, 0.39), size=64)
    tex('fx_paint', B.mjBUILTIN_FLAT, (0.80, 0.81, 0.80), (0.80, 0.81, 0.80), M.mjMARK_RANDOM, (0.78, 0.79, 0.78), random=0.2, size=256)
    mat('fx_tile', 'fx_tile', (3.3, 3.3), specular=0.35, shininess=0.6)        # 150 mm tiles (2 per texture repeat)
    mat('fx_worktop', 'fx_worktop', (2.0, 2.0), specular=0.35, shininess=0.5)  # speckled black epoxy resin lab top
    mat('fx_floor', 'fx_floor', (0.8, 0.8), specular=0.2, shininess=0.3)
    mat('fx_paint', 'fx_paint', (1.0, 1.0), specular=0.05, shininess=0.1)


def tint(contents, alpha_min=0.0):
    """rgba of a mixture (mass-weighted, with per-species tinting strength)"""
    w = {s: g * SPECIES[s][1] for s, g in contents.items() if s in SPECIES and g > 1e-6}
    tot = sum(w.values())
    if tot <= 0: return np.array([0.7, 0.85, 1.0, 0.35])
    c = sum(np.asarray(SPECIES[s][0]) * x for s, x in w.items()) / tot; c[3] = max(c[3], alpha_min)
    return c


def mid_x(a, b): return 0.5 * (a + b)


class Look:
    def __init__(self, ctx):
        self.ctx = ctx; w = ctx.w; m = w.m; self.m = m
        self.mat = {n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_MATERIAL, n) for n in ('fx_tile', 'fx_worktop', 'fx_floor', 'fx_paint')}
        gid = lambda n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, n)
        self.hidden = [g for g in [gid('liquid_' + bk) for bk in BEAKERS] + [gid('flask_liquid'), gid('foam')] if g >= 0]
        self.style = {}
        for bk in BEAKERS: self.style[gid('beaker_%s_vis' % bk)] = PP
        for n in ('flask_body', 'flask_neck'): self.style[gid(n)] = GLASS
        for n in ('funnel_cone', 'funnel_stem'): self.style[gid(n)] = dict(rgba=(0.90, 0.93, 0.96, 0.30), specular=0.8, shininess=0.8)
        self.style[gid('st07_catch_well_vis')] = dict(rgba=(0.86, 0.91, 0.95, 0.30), specular=0.8, shininess=0.8)
        self.table = gid('table'); self.metal = [i for i in range(m.ngeom) if (m.geom(i).name or '').startswith('rail_')]
        self.style.pop(-1, None)
        x0, y0, x1, y1 = w.P['world']['table_xy']; self.table_xy = (x0, y0, x1, y1)
        # sample points filling a beaker's cavity (cavity frame, mm), for the liquid shape of a tilted beaker
        rng = np.random.default_rng(7); n = 600; h = ctx.h_beaker - ctx.floor
        rr = ctx.r_in * np.sqrt(rng.random(n)); a = rng.random(n) * 2 * math.pi
        self.cav = np.c_[rr * np.cos(a), rr * np.sin(a), ctx.floor + rng.random(n) * h]
        self.cap_ml = math.pi * ctx.r_in ** 2 * h / 1000.0
        self.ms = []                                  # decorate time per frame (ms), for the preview's budget check
        self._ovf = (0.0, 0.0)                        # foam overflow seen so far and when it last grew (the drapes slump after)

    # ================================================================== entry
    def __call__(self, scn):
        t0 = time.perf_counter(); c = Canvas(scn)
        self.lights(scn); self.restyle(c); self.room(c)
        for gid in self.hidden: c.hide(gid)
        self.liquids(c); self.streams(c); self.drips(c); self.funnel(c); self.yeast(c); self.spills(c); self.foam(c)
        self.ms.append((time.perf_counter() - t0) * 1000.0)

    # ================================================================== room, light, materials
    def lights(self, scn):
        for i in range(scn.nlight):
            L = scn.lights[i]
            if L.headlight: L.ambient[:] = 0.22; L.diffuse[:] = 0.28; L.specular[:] = 0.15
            elif L.castshadow: L.diffuse[:] = 0.80; L.specular[:] = 0.35; L.ambient[:] = 0.0
            else: L.diffuse[:] = 0.30; L.specular[:] = 0.10
        if scn.nlight < len(scn.lights):               # soft overhead fill, no shadow
            L = scn.lights[scn.nlight]; scn.nlight += 1
            L.type = int(mujoco.mjtLightType.mjLIGHT_DIRECTIONAL); L.headlight = 0; L.castshadow = 0
            L.pos[:] = [0.5, 0.2, 2.0]; d = np.array([0.25, 0.45, -1.0]); L.dir[:] = d / np.linalg.norm(d)
            L.ambient[:] = 0.06; L.diffuse[:] = 0.22; L.specular[:] = 0.05; L.attenuation[:] = [1, 0, 0]; L.cutoff = 180.0; L.exponent = 0.0

    def restyle(self, c):
        for gid, st in self.style.items():
            for g in c.find(gid):
                g.rgba[:] = st['rgba']; g.specular = st['specular']; g.shininess = st['shininess']
        for gid in self.metal:
            for g in c.find(gid): g.rgba[:] = (0.74, 0.76, 0.79, 1); g.specular = 0.7; g.shininess = 0.6
        if self.mat['fx_worktop'] >= 0:
            for g in c.find(self.table): g.rgba[:] = (1, 1, 1, 1); c.material(g, self.m, self.mat['fx_worktop'])

    def room(self, c):
        x0, y0, x1, y1 = self.table_xy; m = self.m; mat = self.mat
        cx, cy = mid_x(x0, x1), mid_x(y0, y1)
        WX0, WX1, WY0, WY1, CEIL = x0 - 520, x1 + 520, y0 - 1000, y1 + 40, 2000.0
        hz = (CEIL - FLOOR_Z) / 2; zc = (CEIL + FLOOR_Z) / 2; white = (1, 1, 1, 1)
        c.box((cx, cy, FLOOR_Z - 10), (3000, 3000, 10), white, matid=mat['fx_floor'], model=m, specular=0.2)
        c.box((cx, cy, mid_x(FLOOR_Z, -20)), ((x1 - x0) / 2 - 25, (y1 - y0) / 2 - 25, (-20 - FLOOR_Z) / 2), (0.80, 0.82, 0.84, 1), specular=0.2)
        tile_top = 620.0
        c.box((cx, WY1 + 10, mid_x(FLOOR_Z, tile_top)), ((WX1 - WX0) / 2, 10, (tile_top - FLOOR_Z) / 2), white, matid=mat['fx_tile'], model=m)
        c.box((cx, WY1 + 10, mid_x(tile_top, CEIL)), ((WX1 - WX0) / 2, 10, (CEIL - tile_top) / 2), white, matid=mat['fx_paint'], model=m)
        c.box((WX0 - 10, mid_x(WY0, WY1), mid_x(FLOOR_Z, tile_top)), (10, (WY1 - WY0) / 2, (tile_top - FLOOR_Z) / 2), white, matid=mat['fx_tile'], model=m)
        c.box((WX0 - 10, mid_x(WY0, WY1), mid_x(tile_top, CEIL)), (10, (WY1 - WY0) / 2, (CEIL - tile_top) / 2), white, matid=mat['fx_paint'], model=m)
        c.box((WX1 + 10, mid_x(WY0, WY1), zc), (10, (WY1 - WY0) / 2, hz), white, matid=mat['fx_paint'], model=m)
        c.box((cx, WY0 - 10, zc), ((WX1 - WX0) / 2, 10, hz), white, matid=mat['fx_paint'], model=m)
        c.box((cx, mid_x(WY0, WY1), CEIL + 10), ((WX1 - WX0) / 2, (WY1 - WY0) / 2, 10), (0.9, 0.9, 0.9, 1))

    # ================================================================== liquids at rest
    def liquids(self, c):
        ctx = self.ctx; r = ctx.r_in - 0.5
        for lv in ctx.levels():
            v = lv['volume_ml']
            if v <= 0.05: continue
            col = tint(lv['contents']); p, R = lv['pos'], lv['R']; h = min(lv['height_mm'], ctx.h_beaker - ctx.floor - 0.5)
            surf = np.r_[np.minimum(col[:3] * 1.08, 1.0), min(1.0, col[3] + 0.25)]
            if lv['tilt_deg'] < 6.0:
                c.cylinder(p + R @ [0, 0, ctx.floor + h / 2], r, h / 2, col, R=R, specular=0.4, shininess=0.6)
                c.cylinder(p + R @ [0, 0, ctx.floor + h - 0.2], r, 0.2, surf, R=R, specular=1.0, shininess=0.95)
                continue
            # tilted: the liquid is the lowest share of the cavity (flat horizontal surface): fit an ellipsoid to it
            P = p + self.cav @ R.T; k = int(round(len(P) * min(v / self.cap_ml, 1.0)))
            if k < 8: continue
            sel = P[np.argsort(P[:, 2])[:k]]; mu = sel.mean(0); ev, vec = np.linalg.eigh(np.cov((sel - mu).T))
            radii = np.sqrt(np.maximum(ev, 0.1) * 3.6)          # between a box (3) and a solid ellipsoid (5): stays inside the cavity
            c.ellipsoid(mu, radii, col, R=vec if np.linalg.det(vec) > 0 else vec * [1, 1, -1], specular=0.4, shininess=0.6)

    # ================================================================== pours
    def streams(self, c):
        ctx = self.ctx; t = ctx.t
        for s in ctx.streams():
            col = tint(s['contents']); col[3] = 1.0
            Q = s['q_ml_s'] * 1000.0; pts = s['points']
            rad = np.clip(np.sqrt(Q / (math.pi * np.maximum(s['speed'], 1.0))) * 1.15, 0.7, 3.4)
            if s['q_ml_s'] >= 1.5:
                c.tube(pts, rad, col, specular=0.9, shininess=0.95)
            else:                                    # a trickle breaks into drops
                T = math.sqrt(max(2 * (pts[0, 2] - pts[-1, 2]) / 9810.0, 1e-6)); nd = 7
                for k in range(nd):
                    tau = ((t * 9.0 + k / nd) % 1.0) * T
                    q = np.r_[pts[0, :2] + s['v0'] * s['dh'] * tau, pts[0, 2] - 0.5 * 9810.0 * tau * tau]
                    c.ellipsoid(q, (1.3, 1.3, 1.9), col, specular=0.9, shininess=0.95)
                c.capsule(pts[0], pts[min(2, len(pts) - 1)], 1.1, col, specular=0.9, shininess=0.95)
            self.splash(c, pts[-1], rad[-1], col, s['recv'], seed=BEAKERS.index(s['src']))

    def splash(self, c, p, r, col, recv, seed=0):
        t = self.ctx.t; lite = np.r_[np.minimum(np.asarray(col[:3]) * 1.1 + 0.05, 1.0), 0.75]
        c.ellipsoid(p + [0, 0, 0.4], (r * 3.0, r * 3.0, 0.7), lite, specular=1.0, shininess=0.95)
        for k in range(6):                            # droplets thrown up from the impact
            ph = (t * 4.0 + hash01(seed, k)) % 1.0; a = 2 * math.pi * hash01(seed, k, 1)
            d = r * 2 + 10 * ph; z = 9.0 * ph * (1 - ph) * 4 * hash01(seed, k, 2)
            c.sphere(p + [d * math.cos(a), d * math.sin(a), z], 0.7, lite, specular=1.0)
        if recv not in ('table', 'funnel'):           # ripples on the receiving surface
            for k in range(2):
                ph = (t * 1.6 + k / 2) % 1.0; rr = r * 3 + ph * (self.ctx.r_in - r * 3 - 1)
                c.cylinder(p + [0, 0, 0.15], rr, 0.12, np.r_[lite[:3], 0.35 * (1 - ph)], specular=1.0, shininess=0.95)

    def drips(self, c):
        ctx = self.ctx; t = ctx.t; drip_ml = ctx.LM.cfg['drip_ml'] if ctx.LM is not None else 1.0
        for d in ctx.drips():
            col = tint(d['contents'], alpha_min=0.7); lip = d['lip']; H = max(lip[2] - d['land_z'], 1.0)
            T = math.sqrt(2 * H / 9810.0); rate = 2.0 + 10.0 * min(d['film_ml'] / drip_ml, 1.0)
            for k in range(3):
                tau = ((t * rate + k / 3.0) % 1.0) * T * 1.4 - 0.4 * T    # a drop swells on the lip, then falls
                if tau < 0: c.sphere(lip + [0, 0, -1.2], 1.0 + 0.5 * (1 + tau / (0.4 * T)), col, specular=1.0); continue
                c.ellipsoid(lip + [0, 0, -1.5 - 0.5 * 9810.0 * tau * tau], (1.2, 1.2, 1.7), col, specular=1.0, shininess=0.95)

    def funnel(self, c):
        """liquid running down the funnel cone and out of the stem into the flask"""
        ctx = self.ctx; f = ctx.funnel_flow(); fl = ctx.flask()
        if f is None or fl is None: return
        g = ctx.funnel_geo; rim = f['rim']; z_stem = rim[2] - g['cone_h']; col = tint(f['contents'], alpha_min=0.6)
        land = [s['points'][-1] for s in ctx.streams() if s['recv'] == 'funnel']
        for p in land:
            c.capsule(p + [0, 0, 0.8], [rim[0], rim[1], z_stem + 1.0], 1.4, col, specular=0.9, shininess=0.9)
        top = np.array([rim[0], rim[1], z_stem - g['stem_h']]); z_end = fl['floor_z'] + fl['liquid_h']
        r = 1.0 + min(f['g'] / 3.0, 1.6)
        c.capsule(top, [top[0], top[1], z_end], r, col, specular=0.9, shininess=0.95)

    # ================================================================== yeast and spills
    def yeast(self, c):
        a = self.ctx.auger()
        if a is None: return
        t = self.ctx.t; o = a['outlet']; H = max(o[2] - a['land_z'], 1.0); T = math.sqrt(2 * H / 9810.0)
        for k in range(26):
            ph = (t * 1.7 + hash01(k, 3)) % 1.0; tau = ph * T; ang = 2 * math.pi * hash01(k, 4); rr = 3.0 * hash01(k, 5) * (1 + 1.5 * ph)
            p = o + [rr * math.cos(ang), rr * math.sin(ang), -0.5 * 9810.0 * tau * tau - 1.0]
            sh = 0.85 + 0.25 * hash01(k, 6)
            c.sphere(p, 0.6 + 0.5 * hash01(k, 7), (0.80 * sh, 0.64 * sh, 0.40 * sh, 1.0), specular=0.1, shininess=0.1)

    def spills(self, c):
        for xy, ml, _ in self.ctx.spills():
            r = math.sqrt(ml * 1000.0 / (math.pi * 0.6))
            if r < 0.8: continue
            c.ellipsoid((xy[0], xy[1], 0.35), (r, r, 0.35), (0.70, 0.84, 1.0, 0.55), specular=1.0, shininess=0.95)

    # ================================================================== flask and foam
    def foam(self, c):
        ctx = self.ctx; fl = ctx.flask(); fo = ctx.foam()
        if fl is None: return
        o = fl['origin']; z0 = fl['floor_z']; axis = np.array([o[0], o[1], 0.0])
        hL = min(fl['liquid_h'], fl['geo']['height'] - 1)
        if fl['volume_ml'] > 0.2 and hL > 0.5:                 # liquid in the flask: frustum slices
            col = tint(fl['contents']); n = max(1, int(math.ceil(hL / 10.0))); dz = hL / n
            for i in range(n):
                zm = (i + 0.5) * dz; c.cylinder(axis + [0, 0, z0 + zm], ctx.flask_radius(zm) - 0.8, dz / 2, col, specular=0.4, shininess=0.6)
        if fo is None: return
        self.base = np.r_[FOAM_YEAST[:3] if fo['yeast'] else FOAM[:3], 1.0]; self.dyed = fo['dyed']
        hF = min(fl['foam_h'], fl['geo']['height'])
        if fo['inside_ml'] > 0.3 and hF > hL + 0.5:           # foam rising inside the flask, seen through the glass
            n = max(1, int(math.ceil((hF - hL) / 8.0))); dz = (hF - hL) / n
            for i in range(n):
                zm = hL + (i + 0.5) * dz
                c.cylinder(axis + [0, 0, z0 + zm], ctx.flask_radius(zm) - 1.0, dz / 2, np.r_[self.base[:3], 0.92], emission=FOAM_GLOW, specular=0.05)
        H = fo['column_mm']; t = ctx.t
        if fo['overflow_ml'] > self._ovf[0] + 1e-6: self._ovf = (fo['overflow_ml'], t)
        if H <= 0.5 and fo['overflow_ml'] <= 0.5: return
        scroll = fo['scroll_mm']; r0 = fo['r_col']; neck = fo['neck']
        fun = ctx.site('funnel_rim'); g = ctx.funnel_geo; z_stem = fun[2] - g['cone_h']
        r_cone = lambda z: g['stem_r'] - 1.5 + (g['rim_r'] - g['stem_r']) * np.clip((z - z_stem) / g['cone_h'], 0.0, 1.0)
        # the toppled foam lands back in the funnel and fills its cone before it spills over the rim into the catch well
        cone_cap = self.cone_ml(r_cone, z_stem, fun[2], r0)
        in_cone = min(fo['overflow_ml'], cone_cap); spilled = max(0.0, fo['overflow_ml'] - cone_cap)
        z_fill = self.cone_fill(c, axis, r_cone, z_stem, fun[2], r0, in_cone)
        overflowing = H >= fo['cap_mm'] - 1.0 and fo['rate'] > 1.0
        slump = math.exp(-max(t - self._ovf[1], 0.0) / 25.0) if fo['overflow_ml'] > 0.5 else 0.0   # draped foam sags once the flow stops
        # the column: up from the neck, swaying a little, and over the top while it overflows
        zz = np.linspace(0.0, max(H, 0.1), max(3, int(H / 8) + 2))
        sw = np.minimum(zz / 80.0, 1.0); sw = sw * sw * (3 - 2 * sw)
        path = list(neck + np.c_[2.5 * np.sin(1.3 * t + zz / 45.0) * sw, 2.0 * np.cos(0.9 * t + zz / 60.0) * sw, zz])
        top = path[-1]; d = np.array([math.cos(0.35), math.sin(0.35), 0.0]); side = np.cross(d, [0, 0, 1.0])
        if overflowing and H > 30:
            Rc = 22.0
            for a in np.linspace(0.2, math.pi, 8): path.append(top + d * (Rc - Rc * math.cos(a)) + [0, 0, 0.75 * Rc * math.sin(a)])
            end = path[-1]; land = axis + d * 30.0; land[2] = z_fill + 4.0
            for u in np.linspace(0.12, 1.0, 8):
                path.append(lerp(end, land, u) + d * (10.0 * math.sin(math.pi * u)) + side * (3.0 * math.sin(2.2 * t + 4 * u)))
        Hc = H
        def radius(s):
            w = np.minimum(s / 70.0, 1.0); return r0 * (0.98 + 0.30 * w * w * (3 - 2 * w)) * np.where(s <= Hc, 1.0, 0.85)
        self.blob_tube(c, np.array(path), radius, scroll, side, seed=1)
        if H > 0.5: self.dome(c, top, float(radius(np.array([H]))[0]))
        if spilled > 0.5: self.spill_over(c, axis, fun, fl, spilled, scroll, slump)

    def foam_rgba(self, phi, s, seed):
        """white foam (cream with yeast) with dye streaks running along the rope, wavering a little (arrays in, (n, 4) out)"""
        phi = np.asarray(phi, float); s = np.broadcast_to(np.asarray(s, float), phi.shape)
        col = np.tile(self.base, (phi.size, 1))
        if self.dyed:
            v = np.cos(3 * phi + 0.7 * np.sin(s / 35.0 + seed)) + 0.35 * (hash01v((s // 9).astype(int), seed, 71) - 0.5)
            k = np.clip(0.5 + (v - 0.62) * 1.2, 0.0, 1.0) * (v > 0.62)
            col[:, :3] = self.base[:3] + (np.asarray(DYE_STREAK[:3]) - self.base[:3]) * k[:, None]
        return col

    def blobs(self, c, P, r, rgba):
        c.spheres(P, r, rgba, emission=FOAM_GLOW, specular=0.04, shininess=0.1)

    def blob_tube(self, c, path, radius, scroll, side, seed=0, step=6.0, n_around=5):
        """foam extruded along a path: rings of blobs at material positions that travel with the scroll, so the foam
        visibly moves out of the neck; ``side`` is a fixed normal (the path stays in one vertical plane)"""
        seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]; L = seg[-1]
        if L < 0.5: return
        k = np.arange(int(math.floor(-scroll / step)), int(math.floor((L - scroll) / step)) + 1); s = k * step + scroll
        keep = (s >= 0) & (s <= L); k = k[keep]; s = s[keep]
        if not len(k): return
        i = np.clip(np.searchsorted(seg, s), 1, len(seg) - 1); f = ((s - seg[i - 1]) / np.maximum(seg[i] - seg[i - 1], 1e-9))[:, None]
        P = path[i - 1] + (path[i] - path[i - 1]) * f; T = path[i] - path[i - 1]; T /= np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
        n1 = side - T * (T @ side)[:, None]; n1 /= np.maximum(np.linalg.norm(n1, axis=1), 1e-9)[:, None]; n2 = np.cross(T, n1)
        R = radius(s) * (0.92 + 0.16 * hash01v(k, seed, 11))
        self.blobs(c, P, R * 0.84, self.base)                                       # core
        phi = 2 * math.pi * (hash01v(k, seed, 12)[:, None] / n_around + np.arange(n_around)[None, :] / n_around)
        rb = R[:, None] * (0.44 + 0.16 * hash01v(k[:, None], np.arange(n_around)[None, :], seed, 13))
        U = np.cos(phi)[..., None] * n1[:, None, :] + np.sin(phi)[..., None] * n2[:, None, :]
        Q = P[:, None, :] + U * (R[:, None] - rb * 0.8)[..., None]
        self.blobs(c, Q.reshape(-1, 3), rb.reshape(-1), self.foam_rgba(phi.reshape(-1), np.repeat(s, n_around), seed))

    def dome(self, c, top, R):
        """rounded, bubbly cap on the column"""
        j = np.arange(7); phi = 2 * math.pi * (j + hash01v(j, 31)) / 7; rb = R * (0.32 + 0.14 * hash01v(j, 32))
        U = np.c_[np.cos(phi), np.sin(phi), np.zeros(7)]
        P = top + U * ((R - rb) * 0.85)[:, None] + np.c_[np.zeros((7, 2)), R * 0.35 * hash01v(j, 33)]
        self.blobs(c, np.vstack([top + [0, 0, R * 0.1], P]), np.r_[R * 0.9, rb], np.vstack([self.base, self.foam_rgba(phi, 0.0, 3)]))

    @staticmethod
    def cone_ml(r_cone, z0, z1, r_col):
        z = np.linspace(z0, z1, 40); a = np.pi * np.maximum(r_cone(z) ** 2 - r_col ** 2, 0.0)
        return float(np.sum(0.5 * (a[1:] + a[:-1]) * np.diff(z)) / 1000.0)

    def annulus(self, c, axis, z, r_in, r_out, seed, top=False, rb_max=8.0):
        """one layer of foam filling the ring between r_in and r_out at height z"""
        rb = max(min(0.5 * (r_out - r_in), rb_max), 3.5); n_r = max(1, int((r_out - r_in) / (1.7 * rb)))
        P = []; r = []; phis = []
        for ir in range(n_r):
            rm = r_in + rb + (r_out - r_in - 2 * rb) * (ir + 0.5) / n_r if n_r > 1 else 0.5 * (r_in + r_out)
            n = max(5, int(2 * math.pi * rm / (rb * 1.35))); j = np.arange(n)
            phi = 2 * math.pi * (j + hash01v(seed, ir, j, 41)) / n
            lift = rb * 0.4 * hash01v(seed, ir, j, 42) if top else np.zeros(n)
            P.append(np.c_[axis[0] + rm * np.cos(phi), axis[1] + rm * np.sin(phi), z + lift]); r.append(rb * (0.9 + 0.25 * hash01v(seed, ir, j, 43))); phis.append(phi)
        phi = np.concatenate(phis); self.blobs(c, np.vstack(P), np.concatenate(r), self.foam_rgba(phi * 1.3, z + 0 * phi, seed % 7))

    def cone_fill(self, c, axis, r_cone, z0, z1, r_col, v_ml):
        """foam collected in the funnel cone around the column, from the stem up; -> fill level z"""
        if v_ml <= 0.3: return z0
        zs = np.linspace(z0, z1, 140); a = np.pi * np.maximum(r_cone(zs) ** 2 - r_col ** 2, 0.0)
        V = np.r_[0.0, np.cumsum(0.5 * (a[1:] + a[:-1]) * np.diff(zs))] / 1000.0; zt = float(np.interp(v_ml, V, zs))
        n_layers = max(1, int((zt - z0) / 10.0))
        for li in range(n_layers + 1):
            zl = z0 + (zt - z0) * (li + 0.5) / (n_layers + 1) if li < n_layers else zt - 2.0
            self.annulus(c, axis, zl, r_col * 0.9, float(r_cone(zl)) - 1.0, 100 + li, top=li == n_layers)
        return zt

    def spill_over(self, c, axis, fun, fl, v_ml, scroll, slump):
        """foam over the funnel rim: drapes falling to the catch well, and the pile filling the well around the flask"""
        ctx = self.ctx; g = fl['geo']; z_floor = fl['floor_z']
        r_well = g['well_rin'] - 1.0; z_c = z_floor + g['collar_h'] - 2.0
        area = math.pi * (r_well ** 2 - (g['base_r'] - 8.0) ** 2); h = min(v_ml * 1000.0 / area, g['well_h'] - g['collar_h'] + 8.0)
        n_layers = max(1, int(math.ceil(h / 10.0)))
        for li in range(n_layers):
            z = z_c + min((li + 0.5) * 10.0, h)
            self.annulus(c, axis, z, ctx.flask_radius(z - z_floor, inner=False) + 1.0, r_well, 200 + li, top=li == n_layers - 1, rb_max=9.0)
        z_top = z_c + h; R = ctx.funnel_geo['rim_r']; thick = (6.0 + 6.0 * min(v_ml / 150.0, 1.0)) * (0.55 + 0.45 * slump)
        for i, ang in enumerate((0.35, 2.4, 4.3)[:1 + int(min(v_ml / 60.0, 2))]):     # more drapes as more foam spills
            u = np.array([math.cos(ang), math.sin(ang), 0.0]); s2 = np.cross(u, [0, 0, 1.0])
            p0 = axis + u * (R - 6) + [0, 0, fun[2] + 4]; p1 = axis + u * (R + 6) + [0, 0, fun[2] - 6]; p2 = axis + u * (r_well - 6) + [0, 0, z_top + 3]
            path = np.array([p0, p1] + [lerp(p1, p2, x) for x in np.linspace(0.1, 1.0, 10)])
            self.blob_tube(c, path, lambda s: np.full_like(s, thick), scroll * 0.7 + 13 * i, s2, seed=10 + i, step=7.0, n_around=4)
