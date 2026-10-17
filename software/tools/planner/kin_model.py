"""Forward/inverse kinematics for the two stock SO-101s, calibrated from the Fusion model.
Zero configuration = the as-built (imported) pose; joint values are Fusion as-built joint angles (rad)."""
import json, os, math
import numpy as np

K = json.load(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'kin.json')))
# servo shaft axes measured from the geometry (arm A); arm B = +240 in X
AXES_A = [((330.0, 525.7, 47.3), (0, 0, 1)), ((351.2, 494.3, 139.4), (1, 0, 0)), ((352.7, 606.8, 168.4), (1, 0, 0)),
          ((354.8, 472.3, 172.5), (1, 0, 0.017)), ((337.2, 448.9, 172.0), (0, 1, 0)), ((318.1, 387.2, 191.4), (1, 0, 0))]

def rot(axis, ang):
    a = np.asarray(axis, float); a /= np.linalg.norm(a)
    K_ = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(ang) * K_ + (1 - math.cos(ang)) * K_ @ K_

def T(axis_pt, axis_dir, ang):
    R = rot(axis_dir, ang); p = np.asarray(axis_pt, float)
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = p - R @ p
    return M

class Arm:
    def __init__(self, tag):
        dx = 0 if tag == 'A' else 240.0
        self.axes = []
        for i, ((p, d), jd) in enumerate(zip(AXES_A, K[tag]['joints'])):
            p = (p[0] + dx, p[1], p[2])
            # sign calibration from the +10 deg probe in Fusion
            p0 = np.array(jd['p0']); p1 = np.array(jd['p1'])
            best = None
            for s in (1, -1):
                q = (T(p, np.array(d) * s, math.radians(10)) @ np.append(p0, 1))[:3]
                err = np.linalg.norm(q - p1)
                if best is None or err < best[0]: best = (err, s)
            self.axes.append((p, tuple(np.array(d, float) * best[1])))
        fj = np.array(K[tag]['fixed_jaw']); mj = np.array(K[tag]['moving_jaw'])
        gp, gd = self.axes[5]
        # finger direction: from the gripper axis to the far end of the fixed jaw
        d = fj - np.array(gp); far = fj[np.argmax(np.linalg.norm(d, axis=1))]
        v = far - np.array(gp); g = np.array(gd) / np.linalg.norm(gd); v = v - g * (v @ g)
        self.finger = v / np.linalg.norm(v)
        self.gp = np.array(gp)
        # grasp point: 45 mm out along the finger, midway between the jaws across the closing plane
        self.grasp0 = self.gp + 45 * self.finger
        self.close_axis0 = g            # gripper joint axis (normal to the jaw closing plane)

    def chain(self, q, upto=6):
        M = np.eye(4)
        for i in range(upto):
            p, d = self.axes[i]; M = M @ T(p, d, q[i])
        return M

    def grasp(self, q):
        M = self.chain(q, 5)            # wrist-roll link carries the grasp frame (gripper joint only opens the jaw)
        G = (M @ np.append(self.grasp0, 1))[:3]
        a = M[:3, :3] @ self.finger      # approach direction
        c = M[:3, :3] @ self.close_axis0 # jaw-hinge axis
        return G, a, c

    def ik(self, target, approach, hinge=None, q0=None, iters=300):
        q = np.zeros(6) if q0 is None else np.array(q0, float)
        tgt = np.asarray(target, float); ap = np.asarray(approach, float); ap /= np.linalg.norm(ap)
        def resid(qq):
            G, a, c = self.grasp(qq)
            r = list(G - tgt) + list(60 * (a - ap))
            if hinge is not None:
                h = np.asarray(hinge, float); h /= np.linalg.norm(h); r += list(30 * np.cross(c, h))
            return np.array(r)
        lam = 1e-2
        for _ in range(iters):
            r = resid(q); Jm = np.zeros((len(r), 5))
            for k in range(5):
                dq = np.zeros(6); dq[k] = 1e-4; Jm[:, k] = (resid(q + dq) - r) / 1e-4
            step = np.linalg.solve(Jm.T @ Jm + lam * np.eye(5), -Jm.T @ r)
            q[:5] += np.clip(step, -0.2, 0.2)
            if np.linalg.norm(r) < 0.05: break
        G, a, c = self.grasp(q)
        return q, float(np.linalg.norm(G - tgt)), float(math.degrees(math.acos(np.clip(a @ ap, -1, 1))))
