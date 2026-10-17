"""Fastener reach check (CDR-01 / CDR-24).

Run:  python analysis/fastener_reach.py [path/to/meshes.json]
Default mesh file: ~/fusion_bridge/meshes.json (export_meshes.py output, triangles in world mm).
Writes analysis/fastener_reach.md and analysis/fastener_reach.json next to this script.

Method
------
1. Every scene occurrence whose component name starts with SHCS / CSK / ISO 7380 / Pan Head / Type I
   is a screw. Bodies with the same occurrence path (head + thread bodies) are merged.
2. Axis = longest bounding-box extent. The head is the end whose vertices spread wider about the
   axis. Tip = the other end. Nominal d and length come from the name (Mdxl).
3. Receiving thread, in priority order:
   a. a metal thread element (T-nut, heat-set insert, tapped servo horn) whose cross-section contains
      the screw axis: engagement = overlap of the shank interval with the element's axial extent;
   b. a printed (PLA) part with a pilot: the axis is sampled every 0.05 mm and at each station a ring
      of 16 points at r = d/2 - 0.1 mm is tested point-in-mesh (ray parity). A station is "pilot" if
      >=80 % of the ring is inside material (a clearance hole leaves the ring mostly in air; the
      export tessellates holes as pentagons, which this radius still separates for M3-M5).
      Engagement = shank length lying in pilot stations.
   The search runs 15 mm past the tip, so a screw that stops short still names the part it was meant
   to enter and reports the gap.
4. Criterion: FAIL if engagement < 1.5 d in PLA or < 1.0 d in steel / aluminium / brass.
"""
import json, math, os, re, sys
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MESH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "fusion_bridge", "meshes.json")
SCREW_PREFIX = ("SHCS", "CSK", "ISO 7380", "Pan Head", "Type I")
PRINTED_PREFIX = ("AG-", "DH-", "ST-", "TT-", "WS-", "RK-", "GR-", "TL-", "CAL-", "EL-", "FN-")
PITCH = {2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0}
EXT = 15.0          # search beyond the tip, mm
STEP = 0.05

# CDR disposition per group (what the ruling says the joint becomes); keyed by (group, screw spec, receiver tag)
DISPOSITION = {
    ("Measuring + auger station", "SHCS M3x12", "AG-01"): "CDR-01: replace by SHCS M3x20, tip Z128, 7.0 mm (2.3d) in the AG-01 pilot",
    ("Arm mounts", "CSK M4x20", "T-nut"): "CDR-11: replace by ISO 7380 M4x20, 2.0 mm; T-nut is 3.8 mm long, so 1.0d is not reachable; accepted (PLA-boss-limited preload ~1 kN)",
    ("Arm mounts", "SHCS M4x20", "T-nut"): "CDR-11: unchanged, 2.0 mm accepted (T-nut 3.8 mm < 1.0d; PLA-boss-limited preload)",
    ("Saddle bolts", "SHCS M5x12", "T-nut"): "CDR-24: TT-01/ST-01 saddles not reprinted, 2.2 mm accepted (PLA-roof-limited preload, SF ~1.5 install / >40 service)",
    ("Measuring + auger station", "SHCS M5x12", "T-nut"): "AG-01/WS-01: CDR-03/06 Ø10x1.5 counterbore -> 3.35-4.05 mm; RK-02 already full T-nut",
    ("Frame brackets", "SHCS M5x8", "T-nut"): "Not reviewed at CDR; T-nut-limited",
    ("Four-bar", "SHCS M5x20", "insert"): "",
    ("Servos", "SHCS M3x12", "TT-01"): "",
    ("Servos", "SHCS M3x12", "ST-01"): "",
    ("(root)", "SHCS M3x12", "horn"): "Al horn flange is 2.0 mm thick: 1.0d not reachable; same class as the CDR-24 carousel deck screws (full 2.0 mm flange accepted)",
}


def load():
    with open(MESH) as f:
        data = json.load(f)
    bodies = []
    for s in data["scene"]:
        v = np.asarray(s["tris"], float).reshape(-1, 3, 3)
        if len(v):
            bodies.append({"name": s["name"], "path": s["path"], "tri": v,
                           "lo": v.reshape(-1, 3).min(0), "hi": v.reshape(-1, 3).max(0)})
    return data, bodies


def inside(points, tri):
    """Ray-parity point-in-mesh (Moller-Trumbore), skewed ray to avoid edge hits."""
    d = np.array([0.5773, 0.4219, 0.6991]); d /= np.linalg.norm(d)
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    h = np.cross(d, e2); a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-12
    v0, e1, e2, h, a = v0[ok], e1[ok], e2[ok], h[ok], a[ok]
    f = 1.0 / a
    out = np.zeros(len(points), bool)
    for i in range(0, len(points), 2000):
        P = points[i:i + 2000]
        s = P[:, None, :] - v0[None]
        u = f * np.einsum("pij,ij->pi", s, h)
        q = np.cross(s, e1[None])
        w = f * np.einsum("ij,pij->pi", np.broadcast_to(d, e1.shape), q)
        t = f * np.einsum("ij,pij->pi", e2, q)
        hit = (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 1e-9)
        out[i:i + 2000] = hit.sum(1) % 2 == 1
    return out


def screw_geometry(group):
    V = np.concatenate([b["tri"].reshape(-1, 3) for b in group])
    lo, hi = V.min(0), V.max(0)
    ax = int(np.argmax(hi - lo))
    o = [i for i in range(3) if i != ax]
    c = 0.5 * (lo[o] + hi[o])
    L = hi[ax] - lo[ax]
    rad = np.hypot(V[:, o[0]] - c[0], V[:, o[1]] - c[1])
    near_lo = V[:, ax] < lo[ax] + 0.15 * L
    near_hi = V[:, ax] > hi[ax] - 0.15 * L
    head_hi = rad[near_hi].max() > rad[near_lo].max()
    return ax, o, c, lo[ax], hi[ax], head_hi


def classify(name):
    n = name.lower()
    if "t-nut" in n: return "T-nut", "steel"
    if "insert" in n: return "insert", "brass"
    if n.startswith("25t al disc horn"): return "horn", "Al 6061"
    if name.startswith(PRINTED_PREFIX): return name.split()[0], "PLA"
    return None, None


def analyse():
    data, bodies = load()
    by_path = defaultdict(list)
    for b in bodies:
        by_path[b["path"]].append(b)
    screws = {p: g for p, g in by_path.items() if g[0]["name"].startswith(SCREW_PREFIX)}
    others = [b for b in bodies if not b["name"].startswith(SCREW_PREFIX)]
    rows = []
    for path, g in sorted(screws.items()):
        name = g[0]["name"]
        m = re.search(r"M(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", name)
        d, Lnom = float(m.group(1)), float(m.group(2))
        dk = int(d) if d == int(d) else d
        pitch = PITCH.get(dk, 0.15 * d)
        ax, o, c, a_lo, a_hi, head_hi = screw_geometry(g)
        tip = a_lo if head_hi else a_hi
        head_end = a_hi if head_hi else a_lo
        sgn = 1.0 if head_hi else -1.0              # + direction from tip toward head
        k = 0.0 if name.startswith("CSK") else d    # head height (CSK head sits in the countersink)
        shank_lo, shank_hi = 0.0, (abs(head_end - tip) - k)   # axial coords measured from the tip toward the head
        def world(s_arr, dx=0.0, dy=0.0):
            P = np.zeros((len(s_arr), 3)); P[:, ax] = tip + sgn * s_arr; P[:, o[0]] = c[0] + dx; P[:, o[1]] = c[1] + dy
            return P
        # candidate bodies: bbox overlaps the search segment, axis inside their cross-section bbox
        seg_lo = min(tip - sgn * EXT, head_end); seg_hi = max(tip - sgn * EXT, head_end)
        cands = []
        for b in others:
            if b["hi"][ax] < seg_lo or b["lo"][ax] > seg_hi: continue
            if not (b["lo"][o[0]] - 0.5 <= c[0] <= b["hi"][o[0]] + 0.5 and b["lo"][o[1]] - 0.5 <= c[1] <= b["hi"][o[1]] + 0.5): continue
            tag, mat = classify(b["name"])
            if tag: cands.append((b, tag, mat))
        best = None
        # (a) metal thread elements, axial-extent overlap
        for b, tag, mat in cands:
            if mat == "PLA": continue
            s1 = (b["lo"][ax] - tip) * sgn; s2 = (b["hi"][ax] - tip) * sgn
            e_lo, e_hi = min(s1, s2), max(s1, s2)
            eng = max(0.0, min(e_hi, shank_hi) - max(e_lo, shank_lo))
            gap = max(0.0, -e_hi) if eng == 0 else 0.0   # element beyond the tip
            cand = dict(recv=b["name"], tag=tag, mat=mat, eng=eng, gap=gap, avail=e_hi - e_lo)
            if best is None or (eng, -gap) > (best["eng"], -best["gap"]): best = cand
        # (b) PLA pilots by ring test
        if best is None or best["eng"] == 0:
            s = np.arange(-EXT, shank_hi + 1e-9, STEP)
            r = d / 2 - 0.1
            angs = np.linspace(0, 2 * math.pi, 16, endpoint=False)
            for b, tag, mat in cands:
                if mat != "PLA": continue
                s1 = (b["lo"][ax] - tip) * sgn; s2 = (b["hi"][ax] - tip) * sgn
                ss = s[(s >= min(s1, s2)) & (s <= max(s1, s2))]
                if not len(ss): continue
                P = np.concatenate([world(ss, r * math.cos(a), r * math.sin(a)) for a in angs])
                frac = inside(P, b["tri"]).reshape(len(angs), len(ss)).mean(0)
                pil = ss[frac >= 0.8]
                if not len(pil): continue
                eng = float(((pil >= 0) & (pil <= shank_hi)).sum() * STEP)
                gap = float(max(0.0, -pil.max())) if eng == 0 else 0.0
                avail = float(len(pil) * STEP)
                cand = dict(recv=b["name"], tag=tag, mat=mat, eng=eng, gap=gap, avail=avail)
                if best is None or (eng, -gap) > (best["eng"], -best["gap"]): best = cand
        parts = re.split(r":\d+\+", path)
        group = parts[1] if path.startswith("HARDWARE") and len(parts) > 2 else "(root)"
        spec = ("CSK " if name.startswith("CSK") else "ISO 7380 " if name.startswith("ISO 7380") else
                "SHCS " if name.startswith("SHCS") else "") + "M%gx%g" % (d, Lnom)
        # clamped part: smallest printed/bought body whose bbox holds the point 0.5 mm under the head bearing face
        hp = world(np.array([shank_hi - 0.5]))[0]
        held = [b for b in others if np.all(b["lo"] - 0.01 <= hp) and np.all(hp <= b["hi"] + 0.01)
                and not classify(b["name"])[1] in ("steel", "brass", "Al 6061")]
        held = min(held, key=lambda b: np.prod(b["hi"] - b["lo"]))["name"] if held else "(not in scene, e.g. SO-101 base)"
        tip_xyz = [None] * 3; tip_xyz[ax] = tip; tip_xyz[o[0]] = c[0]; tip_xyz[o[1]] = c[1]
        row = dict(path=path, name=name, group=group, held=held, spec=spec, d=d, pitch=pitch, axis="XYZ"[ax],
                   tip=[round(float(x), 2) for x in tip_xyz], head_end=round(float(head_end), 2))
        if best is None:
            row.update(recv="none found", tag="-", mat="-", eng=0.0, gap=None, avail=0.0)
        else:
            row.update(best)
        need = (1.5 if row["mat"] == "PLA" else 1.0) * d
        row["need"] = need
        row["ratio"] = row["eng"] / d
        row["threads"] = row["eng"] / pitch
        row["verdict"] = "PASS" if row["eng"] >= need - 1e-6 else "FAIL"
        row["disposition"] = DISPOSITION.get((group, spec, row["tag"]), "")
        rows.append(row)
    return data, rows


def report(data, rows):
    L = []
    L.append("# Fastener reach check (CDR-01 / CDR-24)\n")
    L.append("Generated by `python analysis/fastener_reach.py` from `%s` (scene list, world mm). "
             "Do not edit by hand.\n" % os.path.basename(MESH))
    L.append("Criterion: engagement >= 1.5 d in PLA, >= 1.0 d in steel / Al / brass. Engagement is the axial overlap of the "
             "shank (tip to head bearing face) with the receiving thread: T-nut, heat-set insert or tapped horn by axial extent, "
             "PLA pilot by point-in-mesh ring test at r = d/2 - 0.1 mm. 'Avail.' is the threaded length the receiving body "
             "offers on this axis (for PLA: material inside d/2 along the 15 mm search window, i.e. pilot plus any solid beyond it); 'gap' is how far short of it the tip stops.\n")
    L.append("**The CAD still carries the pre-CDR fastener lengths.** FAILs below are the as-modelled state and are expected; "
             "the CDR disposition column says what the ruling changes. Re-run after the CAD occurrences are updated.\n")
    n_fail = sum(r["verdict"] == "FAIL" for r in rows)
    L.append("Screws checked: %d. PASS %d, FAIL %d.\n" % (len(rows), len(rows) - n_fail, n_fail))
    groups = defaultdict(list)
    for r in rows: groups[r["group"]].append(r)
    for gname in sorted(groups):
        gr = groups[gname]
        L.append("\n## %s\n" % ("Root-level occurrences (not in a HARDWARE group)" if gname == "(root)" else gname))
        L.append("| Occurrence | Screw | Clamps | Axis | Tip (X, Y, Z) | Receiving thread | Material | Engaged mm | x d | Threads | Need mm | Avail. mm | Gap mm | Result |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in gr:
            occ = r["path"].split("+")[-1]
            L.append("| %s | %s | %s | %s | %s | %s | %s | %.2f | %.2f | %.1f | %.1f | %.2f | %s | **%s** |" % (
                occ, r["spec"], r["held"], r["axis"], ", ".join("%.1f" % x for x in r["tip"]), r["recv"], r["mat"],
                r["eng"], r["ratio"], r["threads"], r["need"], r["avail"],
                "-" if not r.get("gap") else "%.2f" % r["gap"], r["verdict"]))
        disp = sorted({r["disposition"] for r in gr if r["disposition"]})
        for dsp in disp:
            L.append("\n- " + dsp)
    # summary table by (group, spec, receiver)
    L.append("\n## Summary by fastener group\n")
    L.append("| Group | Screw | Clamps | Receiving | Qty | Engaged mm (min-max) | x d (min) | Threads (min) | Result | CDR disposition |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    agg = defaultdict(list)
    for r in rows: agg[(r["group"], r["spec"], r["held"], r["recv"])].append(r)
    for (gname, spec, held, recv), rr in sorted(agg.items()):
        e = [r["eng"] for r in rr]
        L.append("| %s | %s | %s | %s | %d | %.2f-%.2f | %.2f | %.1f | **%s** | %s |" % (
            gname, spec, held, recv, len(rr), min(e), max(e), min(r["ratio"] for r in rr), min(r["threads"] for r in rr),
            "FAIL" if any(r["verdict"] == "FAIL" for r in rr) else "PASS", rr[0]["disposition"]))
    L.append("\n## Not checkable from meshes.json\n")
    car = [c["name"] for c in data.get("carousel", []) if c["name"].startswith(SCREW_PREFIX)]
    if not car:
        L.append("- Carousel deck screws (README row 519, M3x10 into the 25T horn): no screw occurrence is present in the "
                 "export (neither `scene` nor `carousel`). Per M-21: tip Z48.6 in the Z48-50 flange = 1.4 mm (0.47d) **FAIL**; "
                 "CDR-24 changes them to SHCS M3x12 (tip Z46.6, full 2.0 mm flange, 0.67d, accepted: the flange is the limit).")
    L.append("- Arm-base screws pass through the borrowed SO-101 base, which is excluded from the scene; only the T-nut "
             "engagement is checked here, which is the governing thread.")
    L.append("- Any nut not modelled (e.g. DIN 985 locknuts on GR-03, CDR-16) is not in the scene and is not checked.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    data, rows = analyse()
    md = report(data, rows)
    with open(os.path.join(HERE, "fastener_reach.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(HERE, "fastener_reach.json"), "w", encoding="utf-8") as f:
        json.dump([{k: r[k] for k in ("path", "group", "spec", "recv", "mat", "eng", "ratio", "threads", "need", "verdict")}
                   for r in rows], f, indent=1)
    for r in rows:
        print("%-5s %-28s %-12s -> %-28s %5.2f mm (%.2fd, %.1f thr) need %.1f" % (
            r["verdict"], r["group"], r["spec"], r["recv"], r["eng"], r["ratio"], r["threads"], r["need"]))
