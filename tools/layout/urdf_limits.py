"""Map the LeRobot so101_new_calib.urdf joint limits onto the CAD (Fusion as-built) joint zero used by kin_model.

q_urdf = s_j * q_cad + o_j, found per arm by matching the URDF forward kinematics to the CAD joint axes:
  pan          : arm plane faces straight out of the base in both models -> o = 0
  shoulder/elbow/wrist_flex : in-plane link angles (shoulder->elbow, elbow->wrist, wrist->hinge) matched exactly
  wrist_roll   : direction of the jaw hinge axis about the roll axis matched
CAD limits = ((urdf_lo, urdf_hi) - o) / s, shrunk by MARGIN on each side (CDR-31: minus 5 deg).
Run directly to print the table."""
import math, os
import numpy as np
import xml.etree.ElementTree as ET
from scipy.optimize import least_squares
from kin_model import Arm, rot

URDF = os.path.join(os.path.expanduser('~'), 'so101', 'so101_new_calib.urdf')
NAMES = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll']
MARGIN = math.radians(5.0)
UP = np.array([0, 0, 1.0])

def _rpy(r, p, y):
    return rot((0, 0, 1), y) @ rot((0, 1, 0), p) @ rot((1, 0, 0), r)

def load_urdf(path=URDF):
    root = ET.parse(path).getroot(); J = {}
    for j in root.findall('joint'):
        o = j.find('origin'); lim = j.find('limit'); ax = j.find('axis')
        J[j.get('name')] = dict(xyz=np.array([float(v) for v in o.get('xyz').split()]) * 1000,
                                R=_rpy(*[float(v) for v in o.get('rpy').split()]),
                                axis=np.array([float(v) for v in ax.get('xyz').split()]) if ax is not None else None,
                                lim=(float(lim.get('lower')), float(lim.get('upper'))) if lim is not None else None)
    return J

def urdf_fk(J, q):
    """frames (R, p) at each named joint (axis = R[:,2]) for the 5 arm joints, plus the jaw hinge"""
    R = np.eye(3); p = np.zeros(3); out = {}
    for k, n in enumerate(NAMES):
        j = J[n]; p = p + R @ j['xyz']; R = R @ j['R']; out[n] = (R.copy(), p.copy()); R = R @ rot(j['axis'], q[k])
    jg = J['gripper']; out['gripper'] = (R @ jg['R'], p + R @ jg['xyz'])
    return out

def _ang(v): return math.atan2(v[1], v[0])
def _wrap(a): return (a + math.pi) % (2 * math.pi) - math.pi

def _plane(P, origin, pitch, toward):
    f = np.cross(pitch, UP); f /= np.linalg.norm(f)
    if f @ toward < 0: f = -f
    return np.array([[(x - origin) @ f, (x - origin) @ UP] for x in P])

def _cad(arm, q):
    pts = [(arm.chain(q, i) @ np.append(arm.axes[i][0], 1))[:3] for i in (0, 1, 2, 3)]
    M5 = arm.chain(q, 5); hinge = (M5 @ np.append(arm.axes[5][0], 1))[:3]
    pitch = arm.chain(q, 1)[:3, :3] @ np.array(arm.axes[1][1])
    roll = arm.chain(q, 4)[:3, :3] @ np.array(arm.axes[4][1]); hax = M5[:3, :3] @ np.array(arm.axes[5][1])
    return pts, hinge, pitch, roll / np.linalg.norm(roll), hax / np.linalg.norm(hax)

def _urdf(J, q):
    F = urdf_fk(J, q)
    pts = [F[n][1] for n in NAMES[:4]]
    return pts, F['gripper'][1], F['shoulder_lift'][0][:, 2], F['wrist_roll'][0][:, 2], F['gripper'][0][:, 2]

def _link_angles(pts, hinge, pitch):
    P = _plane([pts[1], pts[2], pts[3], hinge], pts[0], pitch, pts[1] - pts[0])
    return np.array([_ang(P[1] - P[0]), _ang(P[2] - P[1]), _ang(P[3] - P[2])])

def _roll_angle(pitch, roll, hax):
    """angle of the jaw-hinge axis about the roll axis, measured from the pitch axis (sign-free line direction)"""
    pa = pitch - roll * (pitch @ roll); pa /= np.linalg.norm(pa); b = np.cross(roll, pa)
    h = hax - roll * (hax @ roll)
    return math.atan2(h @ b, h @ pa)

def calibrate(tag):
    arm = Arm(tag); J = load_urdf(); z = np.zeros(6)
    pts, hinge, pitch, roll, hax = _cad(arm, z)
    tgt = _link_angles(pts, hinge, pitch)
    def res(x):
        p, h, pi_, r, hx = _urdf(J, np.r_[0, x, 0]); return _wrap(_link_angles(p, h, pi_) - tgt)
    best = min((least_squares(res, np.radians(s0)) for s0 in ([-90, 90, 0], [0, 0, 0], [90, -90, 0], [-45, 45, 45])), key=lambda r: r.cost)
    o = [0.0] + [_wrap(v) for v in best.x]
    # signs: compare the in-plane response to a small positive joint step in each model
    s = [1]
    for k in (1, 2, 3):
        dq = z.copy(); dq[k] = 1e-3; c1 = _link_angles(*[_cad(arm, dq)[i] for i in (0, 1, 2)]) - tgt
        qu = np.r_[o[:4], 0]; qu2 = qu.copy(); qu2[k] += 1e-3
        u0 = _link_angles(*[_urdf(J, qu)[i] for i in (0, 1, 2)]); u1 = _link_angles(*[_urdf(J, qu2)[i] for i in (0, 1, 2)])
        s.append(1 if c1[k - 1] * (u1 - u0)[k - 1] > 0 else -1)
    # roll: the jaw hinge is a line, so match its direction modulo 180 deg, then pick the branch that also matches
    # the side of the roll axis the hinge sits on
    a_c = _roll_angle(pitch, roll, hax)
    def side(model_pts, hingep, rollv, pitchv, rollpt):
        v = hingep - rollpt; v -= rollv * (v @ rollv); return v @ np.cross(rollv, pitchv)
    cands = []
    for r in np.radians(np.arange(-180, 180, 0.1)):
        p, h, pi_, ro, hx = _urdf(J, np.r_[o[:4], r])
        d = _wrap(2 * (_roll_angle(pi_, ro, hx) - a_c)) / 2
        cands.append((abs(d), r))
    cands.sort(); r_best = [r for d, r in cands[:40]]
    # choose the candidate whose hinge offset is on the same side as in the CAD
    rollpt_c = (arm.chain(z, 4) @ np.append(arm.axes[4][0], 1))[:3]
    sc = side(None, hinge, roll, pitch, rollpt_c)
    def side_u(r):
        F = urdf_fk(J, np.r_[o[:4], r]); ro = F['wrist_roll'][0][:, 2]; pi_ = F['shoulder_lift'][0][:, 2]
        return side(None, F['gripper'][1], ro, pi_, F['wrist_roll'][1])
    good = [r for r in r_best if np.sign(side_u(r)) == np.sign(sc)]
    o.append(good[0] if good else r_best[0])
    # roll sign: compare the roll-axis direction in a common frame. URDF->CAD: the forward (pan->shoulder offset)
    # and pitch directions span both frames, so express the roll axis in (fwd, pitch, up) in each model
    def fpu(v, pitchv, fwd_hint):
        f = np.cross(pitchv, UP); f /= np.linalg.norm(f); f = f if f @ fwd_hint > 0 else -f
        return np.array([v @ f, v @ np.cross(UP, f), v @ UP])
    pts_u, h_u, pi_u, ro_u, hx_u = _urdf(J, np.r_[o[:4], o[4]])
    a = fpu(roll, pitch, pts[1] - pts[0]); b = fpu(ro_u, pi_u, pts_u[1] - pts_u[0])
    s.append(1 if a @ b > 0 else -1)
    return np.array(o), np.array(s), J, best.cost

def cad_limits(tag, margin=MARGIN):
    o, s, J, _ = calibrate(tag)
    L = []
    for k, n in enumerate(NAMES):
        lo, hi = J[n]['lim']; a, b = (lo - o[k]) / s[k], (hi - o[k]) / s[k]
        a, b = min(a, b), max(a, b); L.append((a + margin, b - margin))
    return np.array(L)

if __name__ == '__main__':
    for t in 'AB':
        o, s, J, cost = calibrate(t)
        print('arm', t, 'URDF value at CAD zero (deg):', np.degrees(o).round(2), 'signs', s, 'fit cost %.1e' % cost)
        for n, (a, b) in zip(NAMES, np.degrees(cad_limits(t))):
            print('   %-14s urdf %7.1f..%6.1f  -> CAD %7.1f..%6.1f deg (5 deg margin)' % (n, *np.degrees(J[n]['lim']), a, b))
