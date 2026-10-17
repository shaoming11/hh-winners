"""Hand load cases for the wet lab bench (CDR-28 rewrite). Run:  python analysis/load_cases.py
Regenerates analysis/load_cases.md next to this script. Do not edit the .md by hand.

Units: N, mm, MPa (N/mm^2), N*mm, unless a row says otherwise.

Allowables (CDR-28 / M-26), scatter-adjusted FDM PLA:
    across layers 10 MPa, along layers 30 MPa, bearing 50 MPa; VHB 4950 shear 0.3 MPa sustained.
Criteria:
    OP  (operational):            SF >= 2.0 against the allowable.
    ACC (accident, two-fault, e.g. servo stall into a stop with the firmware clamp failed):
                                  SF >= 1.0 against the allowable AND SF >= 2.0 against 20 MPa (across) / 40 MPa (along).
    Non-stress rows state their own criterion.
Stress concentration: Peterson stepped-bar fits (bending chart 3.10, torsion chart 3.12; Pilkey & Pilkey 3rd ed.)
evaluated with the measured root radii from the CDR record. analysis/fillet_report.md (CDR-12 export gate) does not
exist yet; where the ruling fixed a Kt for a partial shoulder (ST-01 stop post), that value is used and the
full-shoulder Peterson value is printed beside it.

Optional input: ~/fusion_bridge/meshes.json (or argv[1]) for the DH-01 section slices. Without it the slice rows fall
back to the values recorded in the CDR (M-02).
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
g = 9.81
KGCM = 0.0980665                       # N*m per kg*cm
STALL = 45 * KGCM                      # 4.413 N*m, M45CHW at 8.4 V (full 2S), worst case
E_PLA = 3500.0                         # MPa
A_ACROSS, A_ALONG, A_BEAR, A_VHB = 10.0, 30.0, 50.0, 0.3
A2_ACROSS, A2_ALONG = 20.0, 40.0       # second accident check

ROWS = []


# ----------------------------------------------------------------------------------------------------------------
# Peterson stress concentration, stepped round bar with shoulder fillet. D large dia, d small dia, r root radius.
def kt_bending(D, d, r):
    h = (D - d) / 2.0; q = h / r; s = math.sqrt(q)
    if q <= 2.0:
        C = (0.947 + 1.206 * s - 0.131 * q, 0.022 - 3.405 * s + 0.915 * q,
             0.869 + 1.777 * s - 0.555 * q, -0.810 + 0.422 * s - 0.260 * q)
    else:
        C = (1.232 + 0.832 * s - 0.008 * q, -3.813 + 0.968 * s - 0.260 * q,
             7.423 - 4.868 * s + 0.869 * q, -3.839 + 3.070 * s - 0.600 * q)
    x = 2 * h / D
    return C[0] + C[1] * x + C[2] * x ** 2 + C[3] * x ** 3


def kt_torsion(D, d, r):
    h = (D - d) / 2.0; q = min(max(h / r, 0.25), 4.0); s = math.sqrt(q)
    C = (0.905 + 0.783 * s - 0.075 * q, -0.437 - 1.969 * s + 0.553 * q,
         1.557 + 1.073 * s - 0.578 * q, -1.061 + 0.171 * s + 0.086 * q)
    x = 2 * h / D
    return C[0] + C[1] * x + C[2] * x ** 2 + C[3] * x ** 3


# ----------------------------------------------------------------------------------------------------------------
def row(rid, case, cat, formula, inputs, demand, capacity, unit, crit=None, note="", second=None, status=None, cdr=""):
    """cat: OP / ACC / INFO / TEST / CHECK.  For stress rows capacity is the allowable; second = (allowable2) for ACC."""
    sf = (capacity / demand if demand else float("inf")) if capacity is not None else None
    if status is None:
        if cat == "OP":
            need = crit if crit is not None else 2.0
            status = "PASS" if sf >= need - 1e-9 else "FAIL"
            crit_txt = "SF >= %.1f" % need
        elif cat == "ACC":
            sf2 = second / demand if (second and demand) else None
            ok = sf >= 1.0 - 1e-9 and (sf2 is None or sf2 >= 2.0 - 1e-9)
            status = "PASS" if ok else "FAIL"
            crit_txt = "SF >= 1.0" + (" and >= 2.0 vs %g" % second if second else "")
        else:
            need = crit if crit is not None else 1.0
            status = "PASS" if sf >= need - 1e-9 else "FAIL"
            crit_txt = "SF >= %.2g" % need
    else:
        crit_txt = crit if isinstance(crit, str) else ""
    sf2 = (second / demand) if (cat == "ACC" and second and demand) else None
    ROWS.append(dict(id=rid, case=case, cat=cat, formula=formula, inputs=inputs, demand=demand, capacity=capacity,
                     unit=unit, sf=sf, sf2=sf2, crit=crit_txt, status=status, note=note, cdr=cdr))


def fmt(v, unit):
    if v is None: return "-"
    if abs(v) >= 1000: return "%.0f %s" % (v, unit)
    if abs(v) >= 100: return "%.0f %s" % (v, unit)
    if abs(v) >= 10: return "%.1f %s" % (v, unit)
    return "%.2f %s" % (v, unit)


# ================================================================================================================
# 1. ST-01 stop post (CDR-07/08/09, M-04). Crank 20 wide, contact radius r_c = 30.15 mm from the pivot.
r_c, r_post, t_sleeve = 30.15, 9.0, 1.2
a_bare = math.sqrt(r_c ** 2 - (10 + r_post) ** 2)
a_slv = math.sqrt(r_c ** 2 - (10 + r_post + t_sleeve) ** 2)
F_bare, F_slv = STALL * 1e3 / a_bare, STALL * 1e3 / a_slv
ANG = math.radians(39.0)                        # resultant 39 deg off tangential (X): X = F cos, -Y = F sin
row("1a", "Stop post contact force at stall, bare (crank 39 deg)", "INFO",
    "F = T_stall / sqrt(r_c^2 - (10 + r_post + t_sleeve)^2)",
    "T_stall = %.3f N*m (45 kg*cm), r_c = %.2f, r_post = %.1f, t_sleeve = 0 -> lever %.2f mm" % (STALL, r_c, r_post, a_bare),
    F_bare, None, "N", status="-", note="X %.0f N, -Y %.0f N" % (F_bare * math.cos(ANG), F_bare * math.sin(ANG)), cdr="CDR-07")
row("1b", "Stop post contact force at stall, ST-09 sleeved", "INFO",
    "F = T_stall / sqrt(r_c^2 - (10 + r_post + t_sleeve)^2)",
    "t_sleeve = %.1f -> lever %.2f mm" % (t_sleeve, a_slv), F_slv, None, "N", status="-",
    note="X %.0f N, -Y %.0f N. Design value." % (F_slv * math.cos(ANG), F_slv * math.sin(ANG)), cdr="CDR-08")

kt_root_full = kt_bending(27.0, 18.0, 2.0)
for tag, F in (("bare", F_bare), ("sleeved", F_slv)):
    Fx, Fy = F * math.cos(ANG), F * math.sin(ANG)
    L, Zx, Zy, Kt = 61.0 - 7.3, 4008.0, 2580.0, 1.5
    s_nom = Fx * L / Zx + Fy * L / Zy
    row("1c-" + tag, "Stop post v1, Z7.3 composite root (post + web + cradle wall), %s" % tag, "ACC",
        "sigma = Kt (Fx L / Zx + Fy L / Zy)",
        "F = %.0f N at Z61, L = %.1f, A 662 mm^2, Zx %.0f, Zy %.0f mm^3, Kt %.1f (R2.0; Peterson full shoulder r/d 0.11, D/d 1.5: %.2f)"
        % (F, L, Zx, Zy, Kt, kt_root_full), Kt * s_nom, A_ACROSS, "MPa", second=A2_ACROSS,
        note="sigma_nom %.2f MPa. Across layers." % s_nom, cdr="CDR-07")
for tag, F in (("bare", F_bare), ("sleeved", F_slv)):
    L, Z, Kt = 61.0 - 35.5, 577.0, 1.2
    s_nom = F * L / Z
    row("1d-" + tag, "Stop post v1, Z35.5 post top above the web (governing), %s" % tag, "ACC",
        "sigma = Kt F L / Z (resultant, minimum Z)",
        "F = %.0f N, L = %.1f, Z = %.0f mm^3 (A 260), Kt %.1f (R2.0 partial shoulder, ruling value; Peterson full shoulder %.2f)"
        % (F, L, Z, Kt, kt_root_full), Kt * s_nom, A_ACROSS, "MPa", second=A2_ACROSS,
        note="sigma_nom %.2f MPa. v1 knife edge: ST-01 v2 mandatory before the live demo; accepted-risk wording if not fitted." % s_nom,
        cdr="CDR-07")
L, Z, Kt = 7.0, 577.0, 1.3
row("1e", "Stop post v2, Z54 fin top (sleeved)", "ACC", "sigma = Kt F L / Z",
    "F = %.0f N, L = 61 - 54 = %.1f, Z = %.0f mm^3, Kt %.1f (R3 fin-to-post)" % (F_slv, L, Z, Kt),
    Kt * F_slv * L / Z, A_ACROSS, "MPa", second=A2_ACROSS,
    note="Predicted. Acceptance (CDR-07): slice the v2 STL, sigma_peak <= 10 MPa at every Z 5-66 under 197 N at Z61. "
         "At Z35.3 the post+fin section (>330 mm^2) carries 197 N x 25.7 mm with no notch.", cdr="CDR-07")

# 2. Impact with crank compliance (M-04 defence (b), CDR-09: >= 3 s smoothstep)
m_tray = (0.108 + 0.044 + 0.109) + 0.150 + 0.115 + 0.060 + 0.100     # kg, tray+collar+well, flask, liquid, funnel, foam
L_crank, travel = 150.0, 180.0
I_crank = 10 * 20 ** 3 / 12.0                                         # 20 wide (in plane) x 10 thick
L_free = L_crank - a_slv
k_crank = 3 * E_PLA * I_crank / L_free ** 3                           # N/mm at the tip
k_post = 3 * E_PLA * (math.pi * 18 ** 4 / 64) / 25.7 ** 3
k_s = 1 / (1 / k_crank + 1 / k_post)
for T, cat, lab in ((3.0, "ACC", "3 s smoothstep (CDR-09 minimum)"), (1.0, "ACC", "1 s move (wrong profile, fault on fault)")):
    v = 1.5 * travel / T / 1e3                                         # m/s, smoothstep peak velocity
    F_tip = v * math.sqrt(m_tray * k_s * 1e3)                           # N
    F_imp = F_tip * L_crank / a_slv
    s35 = 1.2 * F_imp * 25.5 / 577.0
    row("2-%gs" % T, "Stop impact, %s: post force and v1 Z35.5 stress" % lab, cat,
        "F_tip = v sqrt(m k_s); F_post = F_tip L_crank / a; sigma = Kt F_post L / Z",
        "m %.2f kg, v = 1.5 s/T = %.3f m/s, k_crank = 3EI/L^3 = %.1f N/mm (L %.1f), k_post %.0f N/mm, k_s %.1f N/mm, "
        "L_crank 150, a %.2f -> F_post %.0f N; Z35.5: L 25.5, Z 577, Kt 1.2"
        % (m_tray, v, k_crank, L_free, k_post, k_s, a_slv, F_imp), s35, A_ACROSS, "MPa", second=A2_ACROSS,
        note="Sleeve compliance ignored (conservative). Tray mass reflected 1:1 to the crank tip.", cdr="CDR-09")

# 3. DH-01 joint (CDR-02, M-02). Y=299 plane is vertical in the Z-up print: bending runs ALONG layers.
def dh01_slices():
    mesh = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "fusion_bridge", "meshes.json")
    if not os.path.exists(mesh):
        return None
    import json
    import numpy as np
    sys.path.insert(0, HERE)
    from fastener_reach import inside
    with open(mesh) as f:
        sc = json.load(f)["scene"]
    tri = [np.asarray(s["tris"], float).reshape(-1, 3, 3) for s in sc if s["name"].startswith("DH-01")][0]
    h = 0.25
    xs = np.arange(40 + h / 2, 107, h); zs = np.arange(135 + h / 2, 205, h)
    X, Z = np.meshgrid(xs, zs)
    def mask(y):
        P = np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()])
        return inside(P, tri).reshape(X.shape)
    m_a, m_b, m_320 = mask(298.95), mask(299.05), mask(320.0)
    web = (X >= 79) & (X <= 95) & (Z >= 135) & (Z <= 152)
    bore14 = (X - 87) ** 2 + (Z - 155) ** 2 <= 7.0 ** 2
    A = h * h
    return dict(
        v1_bridge=m_a.sum() * A, v1_tube=m_b.sum() * A, v1_cont=(m_a & m_b).sum() * A, v1_320=m_320.sum() * A,
        v2_cont=(m_a & ((m_b | web) & ~bore14)).sum() * A,
        v2_320=((m_320 | web) & ~bore14).sum() * A,
        web_in_bridge=(m_a & web & ~bore14).sum() * A)

S = dh01_slices()
src = "meshes.json slice (0.25 mm raster, point-in-mesh)" if S else "CDR record (M-02), meshes.json not found"
if not S:
    S = dict(v1_bridge=714.0, v1_tube=275.0, v1_cont=50.0, v1_320=float("nan"), v2_cont=float("nan"),
             v2_320=float("nan"), web_in_bridge=float("nan"))
fillet_add = 2 * 3.0 * 13.9                               # two R3 web-to-bridge fillets: upper bound, full R width at the face
row("3a", "DH-01 v1 Y=299 joint: continuous section (sliver)", "CHECK",
    "A_cont = area(slice Y298.95 AND slice Y299.05)",
    "%s: bridge side %.0f mm^2, tube side %.0f mm^2" % (src, S["v1_bridge"], S["v1_tube"]),
    700.0, S["v1_cont"], "mm^2", crit=1.0,
    note="Strip ~15.6 x 4 mm, Z_bend ~42 mm^3. v1 is not printed (CDR-02 web is P0-before-print).", cdr="CDR-02")
M_down, T_lat = 10 * 31.0, 10 * 58.0                   # N*mm: 10 N down at the hopper (lever ~31), 10 N lateral at Z205
row("3b", "DH-01 v1 sliver under 10 N hand load on the hopper", "OP",
    "sigma = M / Z_bend",
    "M = 10 N x 31 mm = %.0f N*mm, Z_bend 42 mm^3 (M-02); torsion 10 N x 58 mm = %.0f N*mm -> tau ~8 MPa on 15.6 x 4"
    % (M_down, T_lat), M_down / 42.0, A_ALONG, "MPa", note="Bending along layers; torsional shear ~8 MPa vs 10 also fails.", cdr="CDR-02")
row("3b-t", "DH-01 v1 sliver torsion, 10 N lateral at the hopper rim (Z205)", "OP",
    "tau = T / (alpha b c^2), alpha 0.29", "T = %.0f N*mm, b 15.6, c 4 (M-02)" % T_lat,
    T_lat / (0.29 * 15.6 * 4.0 ** 2), A_ACROSS, "MPa", note="No Kt applied (would be worse).", cdr="CDR-02")
row("3c", "DH-01 v2 Y=299 joint: continuous section with the web X79-95, Z135-152", "CHECK",
    "A_cont = area(bridge side AND (tube side OR web) minus v2 bore D14)",
    "web 16 x 17 joined at the bridge face; web-in-bridge overlap %.0f mm^2; R3 web-to-bridge fillets add ~%.0f mm^2 near the face"
    % (S["web_in_bridge"], fillet_add), 700.0, S["v2_cont"], "mm^2", crit=1.0,
    note="Predicted from the v1 mesh + web box (v2 STL not exported yet). The web only spans X79-95 of the 60-wide "
         "bridge, so the load-transfer area across Y=299 cannot reach 700 mm^2 as drawn (+fillets ~%.0f). "
         "The >=700 figure is met only if the whole bridge face is counted. RECORD the measured v2 value here." % (
             S["v2_cont"] + fillet_add), cdr="CDR-02")
row("3d", "DH-01 v2 Y=320 section (web + tube ring + hopper walls)", "CHECK",
    "A = area(slice Y320 OR web, minus v2 bore D14)",
    "v1 section at Y320 %.0f mm^2 (v1 hopper geometry)" % S["v1_320"], 600.0, S["v2_320"], "mm^2", crit=1.0,
    note="Predicted; v2 hopper walls (60 deg, slot Y312-344) change this. RECORD the measured v2 value here.", cdr="CDR-02")
b_w, h_w = 16.0, 13.9                                   # web inside the bridge height
Z_web = b_w * h_w ** 2 / 6
kt_web = kt_bending(h_w + 2 * 6, h_w, 3.0)
row("3e", "DH-01 v2 web joint under 10 N hand load (bending)", "OP", "sigma = Kt M / Z_web, Z_web = b h^2 / 6",
    "M %.0f N*mm, b %.0f, h %.1f -> Z %.0f mm^3, Kt(R3) %.2f" % (M_down, b_w, h_w, Z_web, kt_web),
    kt_web * M_down / Z_web, A_ALONG, "MPa", cdr="CDR-02")
tau_web = (T_lat + 350.0) / (0.21 * b_w * h_w ** 2)     # hand torsion + N20 stall reaction 0.35 N*m
row("3f", "DH-01 v2 web joint: torsion (hand 10 N lateral + N20 stall 0.35 N*m)", "OP",
    "tau = Kt T / (alpha b c^2), alpha 0.21", "T = %.0f + 350 N*mm, b %.0f, c %.1f, Kt %.2f" % (T_lat, b_w, h_w, kt_web),
    kt_web * tau_web, A_ACROSS, "MPa", note="Shear allowable taken as the across-layer 10 MPa (conservative). "
    "SUPERSEDED by the servo change, 2026-10-14: the N20 is replaced by the Feetech FB5311M-360 on the DH-01 v3 mounting wall "
    "(stall 1.52 N*m at 6 V); this row is the v2/N20 record and has not been re-run for v3.", cdr="CDR-02")

# 4. AG-01 hand load 20 N at Z180 (CDR-03, M-06)
M_ag = 20 * (180 - 12)
kt_ag = kt_bending(25 + 2 * 12, 25, 8.0)
row("4a", "AG-01 v2 post root, 20 N at Z180 (worst axis, Z_y 3125)", "OP", "sigma = Kt F (Z_load - Z_root) / Z",
    "F 20 N, lever 168 mm -> M %.0f N*mm, post 30 x 25 (Z_x 3750, Z_y 3125 mm^3), R8 root Kt %.2f" % (M_ag, kt_ag),
    kt_ag * M_ag / 3125.0, A_ACROSS, "MPa", cdr="CDR-03")
ratio_EI = (30 * 16 ** 3) / (20 * 12 ** 3)
ratio_GJ = (0.220 * 30 * 16 ** 3) / (0.209 * 20 * 12 ** 3)
for lab, k_v1, ratio in (("-X (pivot on foot X edge)", 3.85e5, ratio_EI), ("-Y (pivot on foot Y edge, bar bending + torsion)", 1.21e5, 0.5 * (ratio_EI + ratio_GJ))):
    for ver, k in (("v1 20x12 bar", k_v1), ("v2 30x16 bar", k_v1 * ratio)):
        th = math.degrees(20 * 180 / k)
        row("4-%s-%s" % (lab[:2], ver[:2]), "AG-01 rocking, 20 N %s, %s" % (lab, ver), "OP",
            "theta = F H / k_theta", "F 20 N, H 180 mm, k_theta %.3g N*mm/rad (M-06 beam-matrix model%s)" % (
                k, "" if ver.startswith("v1") else ", scaled by bar EI/GJ ratio %.2f" % ratio),
            th, 0.5, "deg", crit=1.0, note="Hopper top moves %.1f mm. +X/+Y bear on the bar/saddle side and are stiffer." % (
                math.radians(th) * 205), cdr="CDR-03")

# 5. DH-02 jam (CDR-04, M-09)
T_jam = 250.0
tau_v2 = 16 * T_jam / (math.pi * 7.0 ** 3)
kt_d2 = kt_torsion(9.0, 7.0, 2.0)
row("5a", "DH-02 v2 jam 0.25 N*m, D7 hub at the D9 collar (R2)", "OP", "tau = Kt 16 T / (pi d^3)",
    "T %.0f N*mm (N20 6 V stall at the 6.0 V-compensated duty), d 7, Peterson torsion D9/d7/r2: Kt %.2f (ruling quoted 1.3)" % (T_jam, kt_d2),
    kt_d2 * tau_v2, A_ACROSS, "MPa",
    note="tau_nom %.2f MPa; with Kt 1.3: %.1f MPa (SF %.2f). At the 0.35 N*m top of the N20 stall range: SF %.2f. Shear on layer planes (upright print). "
         "SUPERSEDED by the servo change, 2026-10-14 (N20 and DH-02 v2 dropped; see row 5c)."
         % (tau_v2, 1.3 * tau_v2, A_ACROSS / (1.3 * tau_v2), A_ACROSS / (kt_d2 * tau_v2 * 0.35 / 0.25)), cdr="CDR-04")
J_v1 = math.pi * (5.1 ** 4 - 3.1 ** 4) / 32
row("5b", "DH-02 v1 jam 0.25 N*m, hub annulus D5.1/D3.1, sharp step", "OP", "tau = Kt T r / J",
    "J = pi (5.1^4 - 3.1^4) / 32 = %.0f mm^4, r 2.55, Kt ~2 (sharp)" % J_v1, 2.0 * T_jam * 2.55 / J_v1, A_ACROSS, "MPa",
    note="Superseded by v2 (not printed).", cdr="CDR-04")
# 5c. DH-02 v3 jam under the Feetech FB5311M-360 (servo change, 2026-10-14)
T_fb = 1520.0                                           # 15.5 kg*cm stall at 6 V (datasheet); higher at 8.4 V
tau_v3 = 16 * T_fb / (math.pi * 8.0 ** 3)
row("5c", "DH-02 v3 jam at full FB5311M-360 stall 1.52 N*m, D8 hub", "ACC", "tau = 16 T / (pi d^3)",
    "T %.0f N*mm (FB5311M-360 15.5 kg*cm stall at 6 V), d 8, Kt not applied (flange root radius not in this script)" % T_fb,
    tau_v3, A_ACROSS, "MPa",
    note="Servo change, 2026-10-14. Nominal shear already exceeds the across-layer allowable, and the stall torque rises at 8.4 V. "
         "Not a design point: the firmware stall rule (A2 feedback progress < 5 deg in 150 ms -> stop, reverse 1/4 rev, retry; "
         "3 stalls -> F AUGER_JAM) must stop the servo first. DH-02 v3 is printed at 100 % infill, 1 spare.", cdr="servo change 2026-10-14")

# 6. Grip friction (CDR-13, M-11)
W_b = (0.025 + 0.080 * 1.04) * g
row("6a", "Grip pull-out vs 100 mL beaker + 80 mL developer, 1 g + 1 g shake", "TEST",
    "F_pull >= 1.5 (1 g + 1 g shake) W; F_pull = 2 mu N",
    "W = (25 g + 80 mL x 1.04) g = %.2f N; demand 2W = %.2f N; calibrated pull-out >= 3.2 N" % (W_b, 2 * W_b),
    2 * W_b, 3.2, "N", crit=1.5,
    note="Torque-limited close, calibrated Friday on a water-filled beaker with wet silicone fingers. N per finger = 3.2 / (2 x 0.6) = %.1f N "
         "(mu 0.6 silicone); without silicone (mu 0.3) %.1f N. Static 1 g: SF %.1f." % (3.2 / 1.2, 3.2 / 0.6, 3.2 / W_b), cdr="CDR-13")

# 7. Load cell overload stop (CDR-06, M-15)
FS = 1.0 * g
F_place = 4.0                       # grip-slip limited axial force (calibrated pull-out 3.2 N, allow up to 4 N)
F_demo = 0.4 * g
row("7a", "Load cell: arm place force + max demo load vs stop engagement", "CHECK",
    "F = F_slip + m_max g  vs  F_stop = 1.2 FS",
    "F_slip %.1f N (grip pull-out, beaker slides in the fingers), m_max 0.4 kg; stop set with 2 paper sheets under 500 g -> 1.2-1.4 FS"
    % F_place, F_place + F_demo, 1.2 * FS, "N", crit=1.0,
    note="Criterion: the stop is not touched in normal use (lower stop setting 1.2 FS).", cdr="CDR-06")
row("7b", "Load cell: stop engagement (upper) vs 150 % safe overload", "ACC",
    "F_stop,max = 1.4 FS  vs  1.5 FS", "FS = 1 kg = %.2f N" % FS, 1.4 * FS, 1.5 * FS, "N", crit=1.0,
    note="Hand on the pan / dropped beaker: the set-screw stop carries the rest.", cdr="CDR-06")

# 8. Thermal (CDR-18, M-16)
def T_adiabatic(V_dev, T0=28.0):
    m_h2o2 = V_dev * 1.04 * 0.12
    Q = m_h2o2 / 34.01 * 98.2e3                         # J
    m_liq = V_dev * 1.04 + 58.0                          # developer + yeast water + soap (M-16: 110 g at 50 mL)
    C = m_liq * 4.0 + 90.0                              # J/K, liquid + 250 mL flask
    return T0 + Q / C, Q, C
for V in (40.0, 50.0):
    T, Q, C = T_adiabatic(V)
    for mat, hdt in (("PLA", 55.0), ("PETG", 70.0)):
        row("8-%g-%s" % (V, mat), "Hot-wetted ST-04/05/07 at %g mL charge vs %s HDT" % (V, mat), "CHECK",
            "T = T0 + (V rho w / M) dH / (m_liq c + C_flask)",
            "V %g mL, rho 1.04, w 0.12, M 34.01, dH 98.2 kJ/mol -> Q %.1f kJ; C %.0f J/K; T0 28 C" % (V, Q / 1e3, C),
            T, hdt, "C", crit=1.0,
            note=("Margin %+.1f K. Near-zero (kPa) stress for minutes: warping, not strength, is the risk; check ST-07 roundness "
                  "after each run (CDR-18). As-printed material (PLA vs PETG) still to be confirmed from printer logs." % (hdt - T)),
            cdr="CDR-18")

# 9. Foam volume (CDR-19, M-17)
V_dev = 40.0
V_gas = V_dev * 40 / 1e3 * (273.15 + T_adiabatic(40.0)[0]) / 273.15
V_well = 0.65
row("9", "Foam volume at the 40 mL cap vs ST-07 well annulus", "CHECK",
    "V_foam ~ V_O2 = V_dev x 40 vol x T/273 K",
    "V_dev 40 mL, 40-vol developer, T %.0f C; well annulus 0.65 L (D126 x 88 around the D85 flask)" % T_adiabatic(40.0)[0],
    V_gas, V_well, "L", crit=1.0,
    note="Overflow ~%.1f L by design: contained by the taped drop cloth + absorbent pads ringing ERUPT (CDR-19); "
         "optional PP container (OD <=150) holds ~2.3 L." % (V_gas - V_well), cdr="CDR-19")

# 10. Fastener engagement per group (post-CDR lengths; as-modelled CAD values in analysis/fastener_reach.md)
def strip_steel(d, Le, uts=250.0):      # internal thread strip in a soft steel T-nut, 0.5 knock-down (M-21)
    return math.pi * d * Le * 0.58 * uts * 0.5
FG = [
    # id, joint, d, Le, material, receiver, F_strip formula label, F_strip, F_preload/ service, service, CDR
    ("10a", "DH-01 -> AG-01, SHCS M3x20 self-tapped D2.5 pilot", 3, 7.0, "PLA", "pi d Le tau 0.6 (tau 10)", math.pi * 3 * 7.0 * 10 * 0.6, 30.0, "CDR-01"),
    ("10b", "Arm front row, ISO 7380 M4x20 into steel T-nut", 4, 2.0, "steel", "pi d Le 0.58 UTS 0.5 (UTS 250)", strip_steel(4, 2.0), 1000.0, "CDR-11"),
    ("10c", "Arm back row, SHCS M4x20 into steel T-nut", 4, 2.0, "steel", "pi d Le 0.58 UTS 0.5", strip_steel(4, 2.0), 1000.0, "CDR-11"),
    ("10d", "TT-01/ST-01 saddle M5x12 into T-nut (no counterbore)", 5, 2.2, "steel", "pi d Le 0.58 UTS 0.5", strip_steel(5, 2.2), 1650.0, "CDR-24"),
    ("10e", "AG-01/WS-01 v2 saddle M5x12, D10x1.5 counterbore (min)", 5, 3.35, "steel", "pi d Le 0.58 UTS 0.5", strip_steel(5, 3.35), 1650.0, "CDR-03/06"),
    ("10f", "RK-02 M5x12 into T-nut (full nut)", 5, 3.8, "steel", "pi d Le 0.58 UTS 0.5", strip_steel(5, 3.8), 1650.0, "CDR-24"),
    ("10g", "Four-bar pivot M5x20 into ruthex M5 insert", 5, 8.0, "brass", "pi d Le 0.58 UTS 0.5 (UTS 300)", strip_steel(5, 8.0, 300.0), 500.0, ""),
    ("10h", "Carousel deck SHCS M3x12 into 25T Al horn (2.0 mm flange)", 3, 2.0, "Al", "pi d Le 0.58 UTS 0.5 (UTS 290)", strip_steel(3, 2.0, 290.0), 500.0, "CDR-24"),
    ("10i", "Stage crank SHCS M3x12 into 25T Al horn (2.0 mm flange)", 3, 2.0, "Al", "pi d Le 0.58 UTS 0.5 (UTS 290)", strip_steel(3, 2.0, 290.0), 500.0, ""),
    ("10j", "Servo ears SHCS M3x12 into TT-01/ST-01 D2.5 pilots", 3, 8.0, "PLA", "pi d Le tau 0.6 (tau 10)", math.pi * 3 * 8.0 * 10 * 0.6, 150.0, ""),
]
for rid, joint, d, Le, mat, flab, F_strip, F_inst, cdr in FG:
    need = (1.5 if mat == "PLA" else 1.0) * d
    pitch = {3: 0.5, 4: 0.7, 5: 0.8}[d]
    rule = "PASS" if Le >= need else "FAIL"
    st = "PASS" if F_strip / F_inst >= (1.5 if F_inst >= 500 else 2.0) else "FAIL"
    if rule == "FAIL":
        st = ("ACCEPTED (strip %s, reach FAIL)" % st) if mat != "PLA" else "FAIL"
    row(rid, "Engagement: " + joint, "OP", "F_strip = " + flab + "  vs  installation preload / max service load",
        "Le %.2f mm = %.2f d = %.1f threads (need %.1f mm, %s); preload/service %.0f N" % (Le, Le / d, Le / pitch, need, mat, F_inst),
        F_inst, F_strip, "N", crit="strip SF >= %.1f; reach >= %s d" % (1.5 if F_inst >= 500 else 2.0, "1.5" if mat == "PLA" else "1.0"), status=st,
        note="Reach rule (>= %s d): **%s**.%s" % ("1.5" if mat == "PLA" else "1.0", rule,
             " Receiving thread is shorter than 1.0 d, so the rule cannot be met by any screw length; the ruling accepts the joint on strip vs PLA-limited preload."
             if rule == "FAIL" and mat != "PLA" else ""), cdr=cdr)

# 11. Carousel radial after the M-03 fix (CDR-10)
mu, N_ls, r_ls = 0.3, 6.0, 40.0
row("11a", "Carousel: liner friction torque (bottom plate floating) vs servo torque", "OP",
    "T_f = mu N r", "mu %.1f, N %.0f N (deck + beakers on the liner), r %.0f mm" % (mu, N_ls, r_ls),
    mu * N_ls * r_ls / 1e3, 35 * KGCM, "N*m", note="Radial load on the servo output = liner friction ~%.0f N (was 0.8-2.5 kN with both plates bonded)." % (mu * N_ls), cdr="CDR-10")
A_vhb = 6600.0
row("11b", "Carousel: upper VHB (top plate to deck) shear from the friction drag", "OP", "tau = (T_f / r) / A_vhb",
    "T_f %.3f N*m at r %.0f, A %.0f mm^2" % (mu * N_ls * r_ls / 1e3, r_ls, A_vhb), (mu * N_ls) / A_vhb, A_VHB, "MPa", cdr="CDR-10")

# 12. TT-04 pocket wall side load (M-08 / CDR-14/15)
for lab, hgt, t, r, cat in (("v1 printed: 16 tall, 2.4 wall, R0.8", 16.0, 2.4, 0.8, "ACC"),
                             ("v2 if unprinted: 12 tall (CDR-14), 2.4 wall, R1.5", 12.0, 2.4, 1.5, "ACC")):
    b = 20.0
    kt = kt_bending(t + 2 * 6, t, r)
    s = 6 * 10.0 * hgt / (b * t ** 2)
    row("12-" + lab[:2], "TT-04 pocket wall, 10 N side load at the rim (%s)" % lab, cat,
        "sigma = Kt 6 F h / (b t^2)", "F 10 N, h %.0f, b %.0f (flat-strip, conservative for a ring), t %.1f, Kt(r %.1f) %.2f" % (hgt, b, t, r, kt),
        kt * s, A_ACROSS, "MPa", second=A2_ACROSS,
        note="Rim strike = accident after the CDR-15 lead-ins and vertical approach (acceptance: 20 picks, no strike).", cdr="CDR-14/15")

# 13. Servo ear screws, in-plane shear and bearing (replaces the pull-out row)
F_ear = STALL * 1e3 / 48.6 / 2
row("13a", "Servo ear screws at stall: PLA bearing on the M3 shank", "ACC", "sigma_b = F / (d Le), F = T_stall / (s_ears 2)",
    "T %.0f N*mm, ear spacing 48.6 mm, 2 screws per side -> F %.1f N; d 3, Le 8.0 (fastener_reach)" % (STALL * 1e3, F_ear),
    F_ear / (3 * 8.0), A_BEAR, "MPa", cdr="")
row("13b", "Servo ear screws at stall: M3 shank shear (8.8)", "ACC", "tau = F / A_s", "F %.1f N, A_s 5.03 mm^2, allowable 0.6 x 640" % F_ear,
    F_ear / 5.03, 0.6 * 640, "MPa", cdr="")
row("13c", "Servo ear (servo case) bearing on the screw", "ACC", "sigma_b = F / (d t_ear)", "F %.1f N, t_ear 2.5 mm (est.), nylon/ABS ~50 MPa" % F_ear,
    F_ear / (3 * 2.5), A_BEAR, "MPa", cdr="")

# 14. Carried-over operational rows (re-checked against the new allowables)
m_deck, r_deck = 0.127, 0.118
m_beaker = 0.015 + 0.040
I_c = 0.5 * m_deck * r_deck ** 2 + 8 * m_beaker * 0.088 ** 2 + 0.06 * 0.094 ** 2 / 6
alpha = 4 * math.radians(45) / 0.6 ** 2
row("14a", "Carousel: servo torque to index 45 deg in 0.6 s (8 full beakers)", "OP", "T = I alpha + T_drag",
    "I %.4f kg*m^2, alpha %.1f rad/s^2, drag 0.02 N*m + liner %.3f N*m" % (I_c, alpha, mu * N_ls * r_ls / 1e3),
    I_c * alpha + 0.02 + mu * N_ls * r_ls / 1e3, 35 * KGCM, "N*m")
F_horn = STALL * 1e3 / (4 * 7.0)
row("14b", "Carousel: M3 horn screws, PLA bearing in deck + spacer at stall", "ACC", "sigma_b = T / (4 r_bc) / (d t)",
    "r_bc 7, d 3, t 8.1", F_horn / (3 * 8.1), A_BEAR, "MPa")
a_tray = 4 * travel / 1e3 / 1.0 ** 2
tau_stage = (0.25 * m_tray * g + m_tray * a_tray) * 0.150
row("14c", "Stage: crank torque, breakaway + accel (180 mm in 1 s, worst)", "OP", "T = (mu m g + m a) L",
    "mu 0.25, m %.2f kg, a %.2f m/s^2, L 0.15 m" % (m_tray, a_tray), tau_stage, 35 * KGCM, "N*m")
Z_link = 10 * 20 ** 2 / 6
row("14d", "Crank bending at the hub, servo stalled (in plane, along layers)", "ACC", "sigma = Kt T / Z",
    "Z = 10 x 20^2 / 6 = %.0f mm^3, Kt 1.5 (hub root radius not yet in fillet_report; assumed)" % Z_link,
    1.5 * STALL * 1e3 / Z_link, A_ALONG, "MPa", second=A2_ALONG)
F_piv = STALL * 1e3 / 150
row("14e", "ST-04 tray posts (D20), stall load, R<=0.5 root", "ACC", "sigma = Kt F L / Z",
    "F %.1f N, L 49, Z 785 mm^3, Kt 2.7 (r/d 0.025; Peterson D/d 1.2: %.2f)" % (F_piv, kt_bending(24, 20, 0.5)),
    2.7 * F_piv * 49 / 785.0, A_ACROSS, "MPa", second=A2_ACROSS, note="Printed; no reprint for fillets (CDR-12).", cdr="CDR-12")
row("14f", "F625ZZ bearing radial load at stall", "OP", "F = T / L", "L 150 mm, C ~1.1 kN", F_piv, 1100.0, "N")
M_arm = 30 * KGCM + 1.2 * g * 0.20
row("14g", "SO-101 base: tension per M4 bolt vs PLA-limited preload", "OP", "F = M / s / 2",
    "M %.2f N*m (shoulder stall + arm), rows 69.8 mm apart, 2 bolts/row; preload ~1 kN" % M_arm, M_arm / 0.0698 / 2, 1000.0, "N", cdr="CDR-11")
row("14h", "Frame: horizontal shove vs friction from 2 C-clamps", "OP", "F_f = 2 F_clamp mu", "F_clamp ~1 kN (est), mu 0.3",
    30.0, 600.0, "N")


# ================================================================================================================
def report():
    L = []
    L.append("# Load cases (CDR-28)\n")
    L.append("Generated by `python analysis/load_cases.py`. Do not edit by hand.\n")
    L.append("**Allowables** (FDM PLA, scatter-adjusted): across layers %g MPa, along layers %g MPa, bearing %g MPa; "
             "VHB 4950 %g MPa sustained shear.  " % (A_ACROSS, A_ALONG, A_BEAR, A_VHB))
    L.append("**Criteria:** OP (operational) SF >= 2 against the allowable. ACC (accident, two-fault) SF >= 1 against the "
             "allowable and SF >= 2 against %g/%g MPa. CHECK/TEST rows state their own criterion. "
             "Kt from Peterson stepped-bar fits with the measured root radii (fillet_report.md not yet generated; see notes).\n" % (A2_ACROSS, A2_ALONG))
    L.append("Servo stall %.3f N*m (M45CHW 45 kg*cm at 8.4 V).\n" % STALL)
    fails = [r for r in ROWS if r["status"] == "FAIL"]
    L.append("**Summary:** %d rows, %d FAIL: %s.\n" % (len(ROWS), len(fails), ", ".join(r["id"] for r in fails) or "none"))
    DISP = {
        "1d-sleeved": "ST-01 v1 knife edge (SF 0.96-1.0). ST-01 v2 fin is mandatory before the live demo (CDR-07); until then accepted-risk entry signed by the lead.",
        "2-1s": "Only reachable with a wrong motion profile AND a failed firmware clamp; CDR-09 enforces >= 3 s smoothstep (row 2-3s passes).",
        "3a": "v1 geometry, not printed; replaced by the CDR-02 web.",
        "3b-t": "v1 geometry, not printed; replaced by the CDR-02 web.",
        "3c": "**Open issue for CDR-02:** the web as drawn (X79-95) cannot meet the >= 700 mm^2 continuous-section acceptance at Y=299; "
              "it only reaches ~%.0f-%.0f mm^2. Either widen the web across the bridge face or restate the acceptance (bridge face area vs two-sided "
              "transfer area). Stress rows 3e/3f pass with large margin, so this is an acceptance-wording/geometry decision for the chief engineer." % (S["v2_cont"], S["v2_cont"] + fillet_add),
        "3d": "Predicted from v1 hopper walls; the v2 hopper (60 deg walls) must be sliced. Below 600 mm^2 on this estimate.",
        "4--X-v1": "v1 geometry; v2 (30x16 bar) passes.",
        "4--Y-v1": "v1 geometry; v2 passes at 0.47 deg (thin margin against 0.5 deg).",
        "5b": "v1 geometry; DH-02 v2 passes (row 5a). Both superseded by DH-02 v3 (servo change, 2026-10-14).",
        "5c": "Servo change, 2026-10-14: a full FB5311M-360 stall overloads the D8 PLA hub. Mitigation: mandatory firmware stall rule on the A2 feedback (150 ms), DH-02 v3 at 100 % infill, 1 spare printed.",
        "8-40-PLA": "Accepted by CDR-18 if PLA: kPa stress, roundness check after each run. Confirm the as-printed material.",
        "8-50-PLA": "50 mL is above the 40 mL cap; shown for reference.",
        "9": "By design: overflow is contained by the drop cloth and pads (CDR-19).",
        "12-v1": "Accident only (rim strike) after the CDR-15 lead-ins; v1 is the printed part. If TT-04 is unprinted, v2 (12 mm walls, R1.5) passes.",
    }
    fl = [r for r in ROWS if r["status"] == "FAIL"]
    if fl:
        L.append("**FAIL dispositions:**" + chr(10))
        for r in fl:
            L.append("- **%s** %s: %s" % (r["id"], r["case"], DISP.get(r["id"], "")))
        L.append("")
    acc = [r["id"] for r in ROWS if r["status"].startswith("ACCEPTED")]
    if acc:
        L.append("Rows %s meet thread-strip vs preload but miss the reach rule (receiving thread shorter than 1.0 d); accepted by CDR-11/24." % ", ".join(acc) + chr(10))
    L.append("| # | Case | Cat | Demand | Capacity | SF | SF vs 20/40 | Criterion | Result | CDR |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in ROWS:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | **%s** | %s |" % (
            r["id"], r["case"], r["cat"], fmt(r["demand"], r["unit"]), fmt(r["capacity"], r["unit"]),
            "-" if r["capacity"] is None else "%.2f" % r["sf"], "-" if r["sf2"] is None else "%.2f" % r["sf2"],
            r["crit"] or "-", r["status"], r["cdr"]))
    L.append("\n## Formulas and inputs\n")
    for r in ROWS:
        L.append("**%s %s**  " % (r["id"], r["case"]))
        L.append("Formula: `%s`  " % r["formula"])
        L.append("Inputs: %s  " % r["inputs"])
        if r["note"]:
            L.append("Note: %s  " % r["note"])
        L.append("")
    L.append("## DH-01 section record (CDR-02)\n")
    L.append("| Section | v1 (as exported) | v2 predicted | Acceptance | v2 measured |")
    L.append("|---|---|---|---|---|")
    L.append("| Y=299.0 continuous (both sides) | %.0f mm^2 | %.0f mm^2 (+~%.0f fillets) | >= 700 mm^2 | _pending: slice v2 STL_ |" % (S["v1_cont"], S["v2_cont"], fillet_add))
    L.append("| Y=320 | %.0f mm^2 | %.0f mm^2 | >= 600 mm^2 | _pending: slice v2 STL_ |" % (S["v1_320"], S["v2_320"]))
    L.append("\nSource: %s." % src)
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    md = report()
    with open(os.path.join(HERE, "load_cases.md"), "w", encoding="utf-8") as f:
        f.write(md)
    for r in ROWS:
        print("%-10s %-5s %-4s SF %6.2f  %s" % (r["id"], r["status"], r["cat"], r["sf"] if r["sf"] is not None else float("nan"), r["case"]))
