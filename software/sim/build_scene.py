"""Generate software/sim/bench.xml: the Wet Lab Bench as a MuJoCo model.

Geometry comes from software/bench/bench.yaml (generated from layout_final.json#update13_final).
The two SO-101 arms are injected from the official MJCF (assets/so101/so101_new_calib.xml) with
name prefixes, and their stock jaws are replaced by the printed fin-ray gripper.

Everything in bench.yaml is mm; MuJoCo is metres. The conversion happens here and nowhere else.

Run:  python3 software/sim/build_scene.py
"""
from __future__ import annotations

import copy
import numpy as np
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bench.config import MM, ROOT, load  # noqa: E402

SO101_XML = HERE / "assets/so101/so101_new_calib.xml"
OUT = HERE / "bench.xml"

# ---------------------------------------------------------------- gripper design
# The printed fin-ray gripper (GR-01 body, GR-02 moving jaw, GR-03 TPU fingers) replaces the
# stock SO-101 jaws.  In the MJCF `gripper` (wrist-roll) body frame:
#   finger direction  f = -z      jaw hinge axis = -y      opening direction  o = +x
# The hinge point is the moving_jaw body origin.  Design inputs from gripper_design.json:
# the beaker centre sits 70.97 mm out along the finger from the hinge (`centre2d[0]`), the
# fingers are 65 long x 24 wide, and the jaw travels 14 deg from contact to open on a 56 mm
# beaker.  The lateral placement is chosen so the beaker straddles the gripper axis.
from bench.motion.gripper_geom import (BEAKER_OUT, FINGER_L, FINGER_T, FINGER_W,  # noqa: E402
                                       FIXED_FACE_X, JAW_CONTACT, JAW_TRAVEL_DEG, SITE_GAP)

HINGE = (0.0202, 0.0188, -0.0234)      # moving_jaw body origin in the gripper body frame
JAW_TRAVEL = math.radians(JAW_TRAVEL_DEG)


def f(v) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.6g}"
    return " ".join(f"{x:.6g}" for x in v)


def el(parent, tag, **kw):
    e = ET.SubElement(parent, tag)
    for k, v in kw.items():
        if v is None:
            continue
        e.set(k.rstrip("_").replace("_", "" if k.endswith("_") else "_"), f(v) if not isinstance(v, str) else v)
    return e


def sub(parent, tag, **kw):
    """SubElement with float formatting and `class_` -> `class`."""
    e = ET.SubElement(parent, tag)
    for k, v in kw.items():
        if v is None:
            continue
        key = {"class_": "class", "type_": "type"}.get(k, k)
        e.set(key, v if isinstance(v, str) else f(v))
    return e


def box(parent, name, x0, x1, y0, y1, z0, z1, **kw):
    """Axis-aligned box from world-mm extents."""
    return sub(parent, "geom", name=name, type="box",
               pos=[(x0 + x1) / 2 * MM, (y0 + y1) / 2 * MM, (z0 + z1) / 2 * MM],
               size=[abs(x1 - x0) / 2 * MM, abs(y1 - y0) / 2 * MM, abs(z1 - z0) / 2 * MM], **kw)


def wall_ring(parent, name, cx, cy, z0, z1, r_in, r_out, n=16, **kw):
    """A thin annular wall (a beaker pocket) built from n box segments. mm in, metres out.

    `mass` is the TOTAL mass of the ring and is divided across the segments.
    """
    t = (r_out - r_in) / 2
    rm = (r_out + r_in) / 2
    w = math.pi * rm / n * 1.15          # slight overlap so there are no gaps
    if "mass" in kw and kw["mass"] is not None:
        kw = dict(kw, mass=float(kw["mass"]) / n)
    for i in range(n):
        a = 2 * math.pi * i / n
        # pocket walls locate the beaker but never wedge it: frictionless, and they win the
        # contact-parameter mix (priority) so a squeezed beaker just slides to the wall
        kw2 = dict({"condim": "1", "priority": "1", "solref": "0.01 1", "solimp": "0.8 0.9 0.002"}, **kw)
        sub(parent, "geom", name=f"{name}_{i}", type="box",
            pos=[(cx + rm * math.cos(a)) * MM, (cy + rm * math.sin(a)) * MM, (z0 + z1) / 2 * MM],
            size=[t * MM, w * MM, abs(z1 - z0) / 2 * MM],
            euler=[0, 0, a], **kw2)


# ---------------------------------------------------------------- SO-101 injection
def so101_defaults_and_assets(root: ET.Element) -> tuple[list[ET.Element], list[ET.Element]]:
    tree = ET.parse(SO101_XML)
    child = tree.getroot()
    defaults = [copy.deepcopy(d) for d in child.findall("default")]
    assets = []
    for a in child.findall("asset"):
        for e in a:
            e = copy.deepcopy(e)
            if e.tag == "mesh":
                # re-root the mesh path onto the parent's meshdir (the repo root)
                e.set("file", f"software/sim/assets/so101/assets/{e.get('file')}")
                if e.get("name") is None:
                    e.set("name", Path(e.get("file")).stem)
            assets.append(e)
    return defaults, assets


def pan_axis_in_base() -> tuple[float, float]:
    """Offset of the shoulder_pan axis from the SO-101 base body origin, in base-local metres."""
    child = ET.parse(SO101_XML).getroot()
    shoulder = child.find("worldbody/body/body")        # base -> shoulder
    x, y, _z = (float(v) for v in shoulder.get("pos").split())
    return x, y


def inject_arm(worldbody: ET.Element, prefix: str, pan_xy_mm, base_z_mm: float, yaw_deg: float):
    """Deep-copy the SO-101 base body, prefix every name, and mount it on the bench.

    `pan_xy_mm` is the documented ARM BASE AXIS - the shoulder_pan axis (demo_process.md 2.3),
    not the base plate origin - so the base body is shifted back by the pan offset.
    """
    child = ET.parse(SO101_XML).getroot()
    base = copy.deepcopy(child.find("worldbody/body"))
    for e in base.iter():
        if e.get("name"):
            e.set("name", prefix + e.get("name"))
    yaw = math.radians(yaw_deg)
    px, py = pan_axis_in_base()
    c, s_ = math.cos(yaw), math.sin(yaw)
    dx, dy = c * px - s_ * py, s_ * px + c * py        # pan offset rotated into world
    base.set("pos", f([pan_xy_mm[0] * MM - dx, pan_xy_mm[1] * MM - dy, base_z_mm * MM]))
    base.set("quat", f([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]))
    worldbody.append(base)
    return base


def add_fin_ray_gripper(base: ET.Element, prefix: str, rgba_body="0.15 0.15 0.18 1",
                        rgba_tpu="0.85 0.3 0.15 1"):
    """Replace the stock jaw collision geoms with the printed fin-ray gripper."""
    bodies = {b.get("name"): b for b in base.iter("body")}
    grip = bodies[prefix + "gripper"]
    jaw = bodies[prefix + "moving_jaw_so101_v1"]

    # the stock jaws are not what is bolted on - keep them visual only
    for body in (grip, jaw):
        for g in list(body.findall("geom")):
            if g.get("class") == "collision":
                body.remove(g)

    hx, hy, hz = HINGE
    z_mid = hz - FINGER_L / 2                       # finger spans hinge plane -> 65 mm out
    beaker_x = FIXED_FACE_X + 0.028 + SITE_GAP      # Phi56 beaker centre, SITE_GAP off the fixed face
    beaker_z = hz - BEAKER_OUT

    # fixed finger (GR-01 body + GR-03 finger) on the wrist-roll link
    sub(grip, "geom", name=f"{prefix}finger_fixed", type="box", contype="1", conaffinity="1",
        pos=[FIXED_FACE_X - FINGER_T / 2, hy, z_mid],
        size=[FINGER_T / 2, FINGER_W / 2, FINGER_L / 2], rgba=rgba_tpu,
        friction="1.2 0.02 0.001", solimp="0.9 0.95 0.001", solref="0.005 1")
    sub(grip, "geom", name=f"{prefix}palm", type="box", contype="1", conaffinity="1",
        pos=[(FIXED_FACE_X - 0.020), hy, hz - 0.012],
        size=[0.014, FINGER_W / 2 + 0.004, 0.014], rgba=rgba_body)
    # grasp frame: where IK puts the beaker centre
    sub(grip, "site", name=f"{prefix}grasp", pos=[beaker_x, hy, beaker_z], size=[0.004],
        rgba="0 1 0 0.35")
    sub(grip, "site", name=f"{prefix}hinge", pos=[hx, hy, hz], size=[0.003], rgba="0 0 1 0.3")

    # moving finger (GR-02 jaw + GR-03 finger).  Placed so that at JAW_CONTACT its inner face
    # touches a Phi56 beaker centred on the grasp site; the moving jaw body rotates about its
    # local z, which is -y in the gripper frame.
    target_face_x = beaker_x + 0.028
    cx, cz = target_face_x + FINGER_T / 2, z_mid     # desired centre in the gripper frame
    # gripper frame -> moving_jaw frame at angle 0 is the body transform; the joint then adds
    # a rotation of JAW_CONTACT about the jaw's local z.  Undo both to get the local placement.
    ux, uz = cx - hx, cz - hz                        # offset from the hinge, gripper frame
    # the joint at +q turns the finger by -q in the gripper x-z plane (measured), so pre-rotate
    # by +JAW_CONTACT for the finger to land on the beaker at exactly q = JAW_CONTACT
    a = JAW_CONTACT
    rx = ux * math.cos(a) + uz * math.sin(a)
    rz = -ux * math.sin(a) + uz * math.cos(a)
    # moving_jaw local axes: local x = gripper +x, local y = gripper +z, local z = gripper -y
    # ... and pre-rotate the box the same way, so the finger is PARALLEL to the fixed finger at
    # q = JAW_CONTACT (the joint turns it back by -JAW_CONTACT about the jaw's local z)
    sub(jaw, "geom", name=f"{prefix}finger_moving", type="box", contype="1", conaffinity="1",
        pos=[rx, rz, 0.0], euler=[0, 0, -JAW_CONTACT],
        size=[FINGER_T / 2, FINGER_L / 2, FINGER_W / 2], rgba=rgba_tpu,
        friction="1.2 0.02 0.001", solimp="0.9 0.95 0.001", solref="0.005 1")


# ---------------------------------------------------------------- bench furniture
def add_frame(wb: ET.Element, cfg):
    for name, (x0, x1, y0, y1, z0, z1) in cfg.at("frame.rails").items():
        box(wb, f"rail_{name}", x0, x1, y0, y1, z0, z1, rgba=ALU, group="0",
            friction="0.25 0.005 0.0001")


def add_rack(wb: ET.Element, cfg):
    r = cfg.at("stations.rack")
    z0, z1 = r["cup_z"]
    box(wb, "rack_spine", 239, 245, 290, 600, 0, 20, rgba="0.9 0.55 0.1 1")
    for nm, (cx, cy) in r["pockets"].items():
        sub(wb, "geom", name=f"rack_col_{nm}", type="cylinder",
            pos=[cx * MM, cy * MM, z0 / 2 * MM], size=[30.8 * MM, z0 / 2 * MM],
            rgba="0.9 0.55 0.1 1")
        wall_ring(wb, f"rack_cup_{nm}", cx, cy, z0, z1, r["cup_id"] / 2, r["cup_od"] / 2,
                  rgba="0.9 0.55 0.1 1")


def add_scale(wb: ET.Element, cfg):
    s = cfg.at("stations.scale")
    box(wb, "ws01_base", *s["base_box"], rgba="0.2 0.6 0.9 1")
    box(wb, "load_cell", *s["load_cell_box"], rgba="0.75 0.75 0.78 1")
    cx, cy = s["pan_xy"]
    # the pan hangs off the load cell: a stiff slide joint whose reaction force IS the reading
    pan = sub(wb, "body", name="scale_pan", pos=[cx * MM, cy * MM, 0])
    sub(pan, "joint", name="scale_flex", type="slide", axis="0 0 1", range="-0.004 0.004",
        stiffness="250000", damping="900", armature="0.0001")
    sub(pan, "geom", name="ws02_disc", type="cylinder",
        pos=[0, 0, (s["pan_disc_z"] + s["beaker_bottom_z"]) / 2 * MM],
        size=[s["pan_od"] / 2 * MM, (s["beaker_bottom_z"] - s["pan_disc_z"]) / 2 * MM],
        rgba="0.2 0.6 0.9 1", friction="1.0 0.01 0.001", mass="0.046")
    wall_ring(pan, "ws02_ring", 0, 0, s["beaker_bottom_z"], s["pan_top_z"],
              s["ring_id"] / 2, s["ring_id"] / 2 + 2.5, rgba="0.2 0.6 0.9 1", mass="0.001")
    sub(pan, "site", name="load_cell_site", pos=[0, 0, s["pan_disc_z"] * MM], size=[0.003],
        rgba="1 0 0 0.3")
    sub(pan, "site", name="scale_station", pos=[0, 0, s["beaker_bottom_z"] * MM], size=[0.003],
        rgba="1 1 0 0.3")


def add_carousel(wb: ET.Element, cfg):
    c = cfg.at("stations.carousel")
    cx, cy = c["centre"]
    box(wb, "tt01_base", cx - 55, cx + 55, cy - 55, cy + 55, 0, 43, rgba="0.35 0.35 0.4 1")
    deck = sub(wb, "body", name="carousel_deck", pos=[cx * MM, cy * MM, 0])
    sub(deck, "joint", name="carousel", type="hinge", axis="0 0 1", damping="4",
        armature="0.02", frictionloss="0.08")
    z0, z1 = c["deck_z"]
    sub(deck, "geom", name="tt02_deck", type="cylinder", pos=[0, 0, (z0 + z1) / 2 * MM],
        size=[c["deck_d"] / 2 * MM, (z1 - z0) / 2 * MM], rgba="0.9 0.9 0.92 1", mass="0.127")
    rz0, rz1 = c["ring_z"]
    # TT-04 web: the pocket floor, from the ring underside up to the beaker bottom
    zb = c["beaker_bottom_z"]
    sub(deck, "geom", name="tt04_web", type="cylinder", pos=[0, 0, (rz0 + zb) / 2 * MM],
        size=[100 * MM, (zb - rz0) / 2 * MM], rgba="0.95 0.5 0.1 1", mass="0.02")
    for nm, p in c["pockets"].items():
        a = math.radians(p["bearing_deg"])
        px, py = c["pocket_r"] * math.cos(a), c["pocket_r"] * math.sin(a)
        wall_ring(deck, f"pocket_{nm}", px, py, c["beaker_bottom_z"], rz1,
                  c["pocket_bore_r"], c["pocket_bore_r"] + 2.4, n=12,
                  rgba="0.95 0.5 0.1 1", mass="0.004")
        sub(deck, "site", name=f"pocket_{nm}_site",
            pos=[px * MM, py * MM, c["beaker_bottom_z"] * MM], size=[0.003], rgba="1 1 0 0.3")


def add_auger(wb: ET.Element, cfg):
    """PS-01 post + DH-01 head + DH-02 screw, laid out along the auger-pocket bearing.

    The real unit sits on E5 outboard of the carousel and cantilevers its outlet over the
    auger pocket (demo_process.md 2.4).  Building it along that bearing keeps it clear of the
    236 mm deck without having to re-derive the 220.6 deg rotation of the whole unit.
    """
    a = cfg.at("stations.auger")
    c = cfg.at("stations.carousel")
    ox, oy = a["outlet_xy"]
    th = math.radians(c["auger_bearing_deg"])
    ux, uy = math.cos(th), math.sin(th)          # outward, carousel centre -> auger pocket
    vx, vy = -uy, ux                             # sideways

    def along(d_out, d_side=0.0):
        return ox + ux * d_out + vx * d_side, oy + uy * d_out + vy * d_side

    # PS-01 v2 post, 40 x 32, outboard of the deck (deck radius 118, pocket at r 84)
    pxy = along(66.0)
    sub(wb, "geom", name="ps01_post", type="box",
        pos=[pxy[0] * MM, pxy[1] * MM, (a["post_z"][1] / 2) * MM],
        size=[20 * MM, 16 * MM, a["post_z"][1] / 2 * MM], euler=[0, 0, th],
        rgba="0.4 0.4 0.45 1")
    # DH-01 v5 bridge + tube, cantilevered back over the pocket
    bxy = along(40.0)
    sub(wb, "geom", name="dh01_bridge", type="box",
        pos=[bxy[0] * MM, bxy[1] * MM, (a["head_underside_z"] + 6.5) * MM],
        size=[45 * MM, 24.5 * MM, 6.5 * MM], euler=[0, 0, th], rgba="0.9 0.9 0.35 1")
    txy = along(30.0)
    sub(wb, "geom", name="dh01_tube", type="cylinder",
        pos=[txy[0] * MM, txy[1] * MM, a["bore_axis_z"] * MM],
        size=[11.5 * MM, 36 * MM], euler=[math.pi / 2, 0, th + math.pi / 2],
        rgba="0.9 0.9 0.35 1")
    hxy = along(52.0)
    sub(wb, "geom", name="dh01_hopper", type="box",
        pos=[hxy[0] * MM, hxy[1] * MM, 207.5 * MM], size=[20 * MM, 20 * MM, 22.5 * MM],
        euler=[0, 0, th], rgba="0.95 0.95 0.3 1")

    screw = sub(wb, "body", name="auger_screw",
                pos=[txy[0] * MM, txy[1] * MM, a["bore_axis_z"] * MM], euler=[0, 0, th])
    sub(screw, "joint", name="auger", type="hinge", axis="1 0 0", damping="0.05",
        armature="0.002")
    sub(screw, "geom", name="dh02_screw", type="cylinder", euler=[0, math.pi / 2, 0],
        size=[a["screw"]["flight_od"] / 2 * MM, a["screw"]["length"] / 2 * MM],
        rgba="0.8 0.8 0.85 1", contype="0", conaffinity="0", mass="0.007")
    sub(wb, "site", name="auger_outlet", pos=[ox * MM, oy * MM, a["outlet_z"] * MM],
        size=[a["outlet_d"] / 2 * MM], rgba="1 0.9 0 0.4")


def add_stage(wb: ET.Element, cfg):
    s = cfg.at("stations.stage")
    kx, ky = s["crank_xy"]
    box(wb, "st12_bridge", 357, 543, 35, 96, 20, 27.3, rgba="0.3 0.3 0.35 1")

    crank = sub(wb, "body", name="stage_crank", pos=[kx * MM, ky * MM, 51 * MM])
    sub(crank, "joint", name="stage_crank", type="hinge", axis="0 0 1", range=f"0 {math.radians(s['erupt_crank_deg']):.6g}",
        damping="0.6", armature="0.02")
    sub(crank, "geom", name="st13_crank", type="box",
        pos=[0, s["crank_r"] / 2 * MM, 0], size=[7 * MM, s["crank_r"] / 2 * MM, 3 * MM],
        rgba="0.8 0.2 0.2 1", contype="0", conaffinity="0", mass="0.007")
    rod = sub(crank, "body", name="stage_rod", pos=[0, s["crank_r"] * MM, 7 * MM])
    sub(rod, "joint", name="stage_rod", type="hinge", axis="0 0 1", damping="0.02",
        armature="0.002")
    sub(rod, "geom", name="st14_rod", type="box", pos=[0, s["rod_l"] / 2 * MM, 0],
        size=[7 * MM, s["rod_l"] / 2 * MM, 3 * MM], rgba="0.85 0.85 0.9 1",
        contype="0", conaffinity="0", mass="0.007")
    sub(rod, "site", name="rod_end", pos=[0, s["rod_l"] * MM, 0], size=[0.003])

    # the sled slides along +Y on S1/S2; the crank-slider loop is closed by an equality
    sled = sub(wb, "body", name="stage_sled", pos=[0, 0, 0])
    sub(sled, "joint", name="stage_sled", type="slide", axis="0 1 0",
        range=f"{-s['travel_mm'] * MM:.6g} 0.001", damping="12", armature="0.01")
    sz0, sz1 = s["sled_z"]
    box(sled, "st11_plate", 381, 519, 196, 350, sz0, sz1, rgba="0.55 0.55 0.6 1", mass="0.254")
    box(sled, "st11_rider_l", 357, 386, 196, 350, 20, 26, rgba="0.55 0.55 0.6 1", mass="0.02",
        friction="0.25 0.005 0.0001")
    box(sled, "st11_rider_r", 514, 543, 196, 350, 20, 26, rgba="0.55 0.55 0.6 1", mass="0.02",
        friction="0.25 0.005 0.0001")
    sub(sled, "site", name="sled_pin", pos=[kx * MM, s["work_pin_y"] * MM, 58 * MM], size=[0.003])

    fx, fy = s["flask"]["xy"]
    wz0, wz1 = s["well"]["z"]
    wall_ring(sled, "st07_well", fx, fy, wz0, wz1, s["well"]["d"] / 2 - 2, s["well"]["d"] / 2,
              n=20, rgba="0.9 0.9 0.95 0.35", mass="0.097")
    cz0, cz1 = s["collar_z"]
    wall_ring(sled, "st05_collar", fx, fy, cz0, cz1, 43.2, 63, n=16, rgba="0.2 0.7 0.3 1",
              mass="0.044")
    fz0, fz1 = s["flask"]["z"]
    sub(sled, "geom", name="flask", type="cylinder", pos=[fx * MM, fy * MM, (fz0 + fz1) / 2 * MM],
        size=[s["flask"]["d"] / 2 * MM, (fz1 - fz0) / 2 * MM], rgba="0.75 0.85 0.9 0.4",
        mass="0.15")
    fu = cfg.at("stations.funnel")
    ux, uy = fu["xy"]
    sub(sled, "geom", name="funnel", type="cylinder",
        pos=[ux * MM, uy * MM, (fu["rim_z"] - fu["height"] / 2) * MM],
        size=[fu["rim_d"] / 2 * MM, fu["height"] / 2 * MM], rgba="0.9 0.9 0.95 0.3",
        mass="0.06", contype="2", conaffinity="2")
    sub(sled, "site", name="funnel_rim", pos=[ux * MM, uy * MM, fu["rim_z"] * MM],
        size=[0.004], rgba="1 1 0 0.3")
    # liquid in the flask (visual only, from the chemistry model) and the foam column
    sub(sled, "geom", name="flask_liquid", type="cylinder", pos=[fx * MM, fy * MM, (fz0 + 0.5) * MM],
        size=[40 * MM, 0.0005], rgba="0.35 0.65 1 0.8", contype="0", conaffinity="0", mass="1e-6")
    # foam column, visual only, resized at runtime
    sub(sled, "geom", name="foam", type="cylinder", pos=[fx * MM, fy * MM, fz1 * MM],
        size=[0.02, 0.001], rgba="1 0.95 0.85 0.9", contype="0", conaffinity="0", mass="1e-6")


def add_beakers(wb: ET.Element, cfg) -> list[str]:
    b = cfg.at("beaker")
    car, rack = cfg.at("stations.carousel"), cfg.at("stations.rack")
    places = []
    for nm, pocket in (("P1", "pick"), ("P2", "p_right")):     # P2 one pocket (+90 deg) from the pick
        p = car["pockets"][pocket]
        places.append((nm, p["xy"], car["beaker_bottom_z"]))
    for nm in ("developer", "soap", "water"):
        places.append((nm, rack["pockets"][nm], rack["beaker_bottom_z"]))

    names = []
    for nm, (x, y), z in places:
        body = sub(wb, "body", name=f"beaker_{nm}", pos=[x * MM, y * MM, z * MM])
        sub(body, "freejoint", name=f"beaker_{nm}_free")
        sub(body, "geom", name=f"beaker_{nm}_geom", type="cylinder",
            pos=[0, 0, b["h"] / 2 * MM], size=[b["d"] / 2 * MM, b["h"] / 2 * MM],
            rgba="0.85 0.9 0.95 0.45", mass=b["mass_empty_g"] / 1000.0,
            friction="1.1 0.02 0.001", solimp="0.9 0.95 0.001", solref="0.005 1")
        # liquid column, visual only, resized every step by the chemistry model
        sub(body, "geom", name=f"beaker_{nm}_liquid", type="cylinder", pos=[0, 0, 0.0005],
            size=[(b["d"] / 2 - 1.5) * MM, 0.0005], rgba="0.3 0.6 1 0.75", contype="0",
            conaffinity="0", mass="1e-6")
        sub(body, "site", name=f"beaker_{nm}_rim", pos=[0, 0, b["h"] * MM], size=[0.002],
            rgba="1 0 1 0.3")
        sub(body, "site", name=f"beaker_{nm}_base", pos=[0, 0, 0], size=[0.002])
        names.append(nm)
    return names


def add_cameras(wb: ET.Element, cfg):
    fx, fy = cfg.at("stations.stage.flask.xy")
    sub(wb, "camera", name="overview", pos=[0.45, -0.45, 0.75], xyaxes="1 0 0 0 0.6 0.8")
    sub(wb, "camera", name="webcam", pos=[fx * MM, (fy - 420) * MM, 0.30],
        xyaxes="1 0 0 0 0.35 0.94")
    sub(wb, "camera", name="top", pos=[0.5, 0.45, 1.5], xyaxes="1 0 0 0 1 0")
    sub(wb, "camera", name="scale_cam", pos=[0.62, 0.10, 0.42], xyaxes="1 0 0 0 0.8 0.6")


# ---------------------------------------------------------------- visuals: the real parts
PLA = {"orange": "0.96 0.52 0.12 1", "white": "0.93 0.93 0.9 1", "blue": "0.2 0.55 0.9 1",
       "grey": "0.45 0.46 0.5 1", "yellow": "0.95 0.85 0.25 1", "green": "0.25 0.65 0.35 1",
       "black": "0.12 0.12 0.13 1", "dark": "0.22 0.22 0.25 1"}
GLASS = "0.82 0.92 1.0 0.32"
ALU = "0.74 0.75 0.78 1"
VIS = dict(contype="0", conaffinity="0", group="1", mass="0")


def _find_body(wb: ET.Element, name: str) -> ET.Element:
    for b in wb.iter("body"):
        if b.get("name") == name:
            return b
    raise KeyError(name)


def _mesh(asset: ET.Element, name: str, file: str, scale="0.001 0.001 0.001", refquat=None):
    e = sub(asset, "mesh", name=name, file=file, scale=scale)
    if refquat:
        e.set("refquat", refquat)


PLACED: list[tuple[str, str, np.ndarray, np.ndarray]] = []   # geom, mesh, pos(m), quat - STL frame


def _quat_euler_z(a: float) -> np.ndarray:
    return np.array([math.cos(a / 2), 0, 0, math.sin(a / 2)])


def _quat_mul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2,
                     w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2])


def _quat_zaxis(v) -> np.ndarray:
    import mujoco
    q = np.zeros(4); v = np.asarray(v, float); mujoco.mju_quatZ2Vec(q, v / np.linalg.norm(v)); return q


def place_mesh(parent, name, mesh, pos_m, quat=None, **kw):
    """A visual mesh geom whose `pos`/`quat` are meant for the STL's OWN origin.  MuJoCo
    re-centres meshes at compile time; fix_mesh_frames() corrects these after a first compile."""
    q = np.array([1.0, 0, 0, 0]) if quat is None else np.asarray(quat, float)
    g = sub(parent, "geom", name=name, type="mesh", mesh=mesh, pos=list(pos_m), quat=list(q), **kw)
    PLACED.append((name, mesh, np.asarray(pos_m, float), q))
    return g


def fix_mesh_frames(root: ET.Element) -> None:
    """MuJoCo re-centres (and may re-orient) every mesh asset at compile time, so a geom's pos
    refers to that internal frame, not the STL's origin.  Compile once, MEASURE the rigid map
    T: v_stl -> v_stored for each asset by matching vertex sets (robust to the exact
    convention), and rewrite every placed geom so the STL vertices land at the intended pose:
        world = p_g + R_g v_stored,  v_stored = Rt v_stl + t   =>   R_g = R0 Rt^T,  p_g = p0 - R_g t
    """
    import struct
    import mujoco
    from scipy.spatial import cKDTree
    xml = ET.tostring(root, encoding="unicode")
    m = mujoco.MjModel.from_xml_string(xml)

    def stl_verts(path, scale):
        with open(path, "rb") as fh:
            fh.read(80); n = struct.unpack("<I", fh.read(4))[0]
            arr = np.frombuffer(fh.read(n * 50), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
        return np.unique(arr["v"].reshape(-1, 3), axis=0) * scale

    maps = {}
    for i in range(m.nmesh):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, i)
        mp, mq = m.mesh_pos[i].copy(), m.mesh_quat[i].copy()
        stored = m.mesh_vert[m.mesh_vertadr[i]:m.mesh_vertadr[i] + m.mesh_vertnum[i]]
        file = ROOT / [e.get("file") for e in root.iter("mesh") if e.get("name") == nm][0]
        vs = stl_verts(file, 0.001)
        Rm = np.zeros(9); mujoco.mju_quat2Mat(Rm, mq); Rm = Rm.reshape(3, 3)
        tree = cKDTree(stored)
        best = None
        for Rt, t in ((Rm.T, -Rm.T @ mp), (Rm, -Rm @ mp), (Rm.T, -mp), (Rm, -mp), (np.eye(3), -mp)):
            err = tree.query((Rt @ vs.T).T + t)[0].mean()
            if best is None or err < best[0]:
                best = (err, Rt, t)
        err, Rt, t = best
        if err > 1e-4:
            print(f"  warning: mesh {nm} frame match residual {err * 1000:.2f} mm")
        maps[nm] = (Rt, t)
    geoms = {g.get("name"): g for g in root.iter("geom")}
    for name, mesh, p0, q0 in PLACED:
        Rt, t = maps[mesh]
        R0 = np.zeros(9); mujoco.mju_quat2Mat(R0, q0); R0 = R0.reshape(3, 3)
        Rg = R0 @ Rt.T
        pg = p0 - Rg @ t
        qg = np.zeros(4); mujoco.mju_mat2Quat(qg, Rg.ravel())
        g = geoms[name]
        g.set("pos", f(list(pg))); g.set("quat", f(list(qg)))
        for k in ("euler", "zaxis"):
            if k in g.attrib:
                del g.attrib[k]


def add_visual_parts(asset: ET.Element, wb: ET.Element, cfg) -> list[str]:
    """Visual-only geoms of the printed parts, servos and glassware, placed in each STL's own
    frame (measured: TT-01 origin at the servo axis; WS-01/PS-01/DH-01 corner origins; the
    rest centred) - fix_mesh_frames() reconciles that with MuJoCo's recentring.  Returns the
    names of the collision primitives these meshes replace visually."""
    P = "exports/prints_v2/"
    meshes = {
        "tt01": P + "TT-01_turntable-base-v2_qty1.stl", "tt02": "exports/prints/TT-02_carousel-deck_qty1.stl",
        "tt03": "exports/prints/TT-03_horn-spacer_qty1.stl", "tt04": P + "TT-04_beaker-ring-v4-4x100mL_qty1.stl",
        "ws01": P + "WS-01_scale-base-v4_E6-notch_qty1.stl", "ws02": P + "WS-02_scale-pan-v3-100mL_qty1.stl",
        "ps01": P + "PS-01_auger-post-v2_qty1.stl", "dh01": P + "DH-01_yeast-auger-head-v5_qty1.stl",
        "dh02": P + "DH-02_auger-screw-v4_qty2.stl", "st11": P + "ST-11_stage-sled_qty1_SUPPORTS.stl",
        "st12": P + "ST-12_servo-bridge_qty1.stl", "st13": P + "ST-13_crank_qty1.stl",
        "st14": P + "ST-14_connecting-rod_qty1.stl", "st05": P + "ST-05_flask-collar_qty1.stl",
        "st07": P + "ST-07_catch-well_qty1.stl", "rk03": P + "RK-03v2_reagent-stand_qty3.stl",
        "bk_wall": P + "_beaker_wall.stl", "bk_floor": P + "_beaker_floor.stl",
        "flask": "software/sim/assets/gen/flask_250.stl", "funnel": "software/sim/assets/gen/funnel_4in.stl",
        "servo": "software/sim/assets/gen/servo_std.stl",
    }
    for k, f_ in meshes.items():
        _mesh(asset, k, f_)

    hide: list[str] = []
    st = cfg.at("stations")
    Y2Z = np.array([0.7071068, 0.7071068, 0, 0])            # servo STL is Y-up: rotate Y -> Z
    # ---- carousel unit
    c = st["carousel"]; cx, cy = c["centre"]; th = math.radians(c["auger_bearing_deg"])
    place_mesh(wb, "v_tt01", "tt01", [cx * MM, cy * MM, 0], _quat_euler_z(th), rgba=PLA["dark"], **VIS)
    place_mesh(wb, "v_servo_carousel", "servo", [cx * MM, cy * MM, 2.7 * MM],
               _quat_mul(_quat_euler_z(th), Y2Z), rgba=PLA["black"], **VIS)
    deck = _find_body(wb, "carousel_deck")
    place_mesh(deck, "v_tt03", "tt03", [0, 0, 50.5 * MM], rgba=PLA["white"], **VIS)
    place_mesh(deck, "v_tt02", "tt02", [0, 0, c["deck_z"][0] * MM], rgba=PLA["white"], **VIS)
    phase = math.radians(c["pockets"]["pick"]["bearing_deg"] - 22.5)      # STL pockets at 22.5 + 90k
    place_mesh(deck, "v_tt04", "tt04", [0, 0, c["ring_z"][0] * MM], _quat_euler_z(phase), rgba=PLA["orange"], **VIS)
    hide += ["tt01_base", "tt02_deck", "tt04_web"] + [f"pocket_{n}_{i}" for n in c["pockets"] for i in range(12)]
    # ---- auger unit along the bearing u (carousel centre -> auger pocket).  DH-01 STL: x across
    # (0..90), y along the tube (bridge y 0..49 over the post, outlet at y 120, end 131), z up.
    # Local +y points inward (post -> pocket = -u).
    a = st["auger"]; ox, oy = a["outlet_xy"]
    u = np.array([math.cos(th), math.sin(th)])
    ang = th + math.pi / 2                                     # rotates local +y onto -u
    q_head = _quat_euler_z(ang)
    Rh = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    head_xy = np.array([ox, oy]) - Rh @ np.array([47.0, 120.0])
    place_mesh(wb, "v_dh01", "dh01", [head_xy[0] * MM, head_xy[1] * MM, a["head_underside_z"] * MM], q_head, rgba=PLA["yellow"], **VIS)
    post_xy = np.array([ox, oy]) + u * 96.0                    # bridge centre, 96 mm outboard of the outlet
    post_corner = post_xy - Rh @ np.array([20.0, 16.0])
    place_mesh(wb, "v_ps01", "ps01", [post_corner[0] * MM, post_corner[1] * MM, 0], q_head, rgba=PLA["grey"], **VIS)
    screw = _find_body(wb, "auger_screw")
    place_mesh(screw, "v_dh02", "dh02", [34.5 * MM, 0, 0], _quat_zaxis([-1, 0, 0]), rgba=ALU, **VIS)
    servo_xy = np.array([ox, oy]) + u * 122.0
    place_mesh(wb, "v_servo_auger", "servo", [servo_xy[0] * MM, servo_xy[1] * MM, a["bore_axis_z"] * MM],
               _quat_mul(_quat_zaxis([-u[0], -u[1], 0]), Y2Z), rgba=PLA["black"], **VIS)
    hide += ["ps01_post", "dh01_bridge", "dh01_tube", "dh01_hopper", "dh02_screw"]
    # ---- scale
    sc = st["scale"]; b = sc["base_box"]
    place_mesh(wb, "v_ws01", "ws01", [b[0] * MM, b[2] * MM, 0], rgba=PLA["blue"], **VIS)
    pan = _find_body(wb, "scale_pan")
    place_mesh(pan, "v_ws02", "ws02", [0, 0, sc["pan_disc_z"] * MM], rgba=PLA["blue"], **VIS)
    hide += ["ws01_base", "ws02_disc"] + [f"ws02_ring_{i}" for i in range(16)]
    # ---- rack
    for nm, (x, y) in st["rack"]["pockets"].items():
        place_mesh(wb, f"v_rk03_{nm}", "rk03", [x * MM, y * MM, 0], rgba=PLA["orange"], **VIS)
        hide += [f"rack_col_{nm}"] + [f"rack_cup_{nm}_{i}" for i in range(16)]
    # ---- stage
    sg = st["stage"]; kx, ky = sg["crank_xy"]; fx, fy = sg["flask"]["xy"]
    place_mesh(wb, "v_st12", "st12", [kx * MM, 65.0 * MM, 20.0 * MM], rgba=PLA["grey"], **VIS)
    place_mesh(wb, "v_servo_stage", "servo", [kx * MM, ky * MM, 4.7 * MM], _quat_mul(_quat_euler_z(math.pi), Y2Z),
               rgba=PLA["black"], **VIS)
    crank = _find_body(wb, "stage_crank"); rod = _find_body(wb, "stage_rod"); sled = _find_body(wb, "stage_sled")
    place_mesh(crank, "v_st13", "st13", [0, 0, -3 * MM], rgba=PLA["orange"], **VIS)
    place_mesh(rod, "v_st14", "st14", [0, 0, -3 * MM], rgba=PLA["white"], **VIS)
    place_mesh(sled, "v_st11", "st11", [fx * MM, fy * MM, 0], rgba=PLA["grey"], **VIS)
    place_mesh(sled, "v_st05", "st05", [fx * MM, fy * MM, sg["collar_z"][0] * MM], rgba=PLA["green"], **VIS)
    place_mesh(sled, "v_st07", "st07", [fx * MM, fy * MM, sg["well"]["z"][0] * MM], rgba="0.95 0.95 0.97 0.45", **VIS)
    place_mesh(sled, "v_flask", "flask", [fx * MM, fy * MM, sg["flask"]["z"][0] * MM], rgba=GLASS, **VIS)
    fu = st["funnel"]
    place_mesh(sled, "v_funnel", "funnel", [fu["xy"][0] * MM, fu["xy"][1] * MM, (fu["rim_z"] - fu["height"]) * MM],
               rgba="0.9 0.93 0.97 0.5", **VIS)
    hide += ["st12_bridge", "st13_crank", "st14_rod", "st11_plate", "st11_rider_l", "st11_rider_r", "flask", "funnel"]
    hide += [f"st07_well_{i}" for i in range(20)] + [f"st05_collar_{i}" for i in range(16)]
    # ---- beakers: glass wall + floor
    for nm in ("P1", "P2", "developer", "soap", "water"):
        body = _find_body(wb, f"beaker_{nm}")
        place_mesh(body, f"v_bk_{nm}_wall", "bk_wall", [0, 0, 0], rgba=GLASS, **VIS)
        place_mesh(body, f"v_bk_{nm}_floor", "bk_floor", [0, 0, 0], rgba="0.82 0.92 1.0 0.6", **VIS)
        hide.append(f"beaker_{nm}_geom")
    return hide


def hide_collision_primitives(wb: ET.Element, names: list[str]) -> None:
    """Collision stays; only the drawing goes (alpha 0) where a real part mesh now shows."""
    want = set(names)
    for g in wb.iter("geom"):
        if g.get("name") in want:
            g.set("rgba", "0 0 0 0")


def main() -> None:
    cfg = load()
    root = ET.Element("mujoco", model="wet_lab_bench")
    ET.SubElement(root, "compiler", angle="radian", meshdir=str(ROOT), autolimits="true",
                  balanceinertia="true")
    # 1 ms step, pyramidal cones: robust when a finger wedges a beaker against a pocket wall
    ET.SubElement(root, "option", timestep="0.001", integrator="implicitfast",
                  cone="elliptic", impratio="10")
    vis = ET.SubElement(root, "visual")
    ET.SubElement(vis, "headlight", diffuse="0.65 0.65 0.65", ambient="0.35 0.35 0.35",
                  specular="0.1 0.1 0.1")
    ET.SubElement(vis, "global", azimuth="140", elevation="-25", offwidth="1280", offheight="960")
    ET.SubElement(vis, "quality", shadowsize="4096")
    ET.SubElement(vis, "map", shadowclip="2.5", shadowscale="0.8")

    defaults, assets = so101_defaults_and_assets(root)
    for d in defaults:
        root.append(d)
    asset = ET.SubElement(root, "asset")
    for a in assets:
        asset.append(a)
    ET.SubElement(asset, "texture", type="skybox", builtin="gradient", rgb1="0.62 0.68 0.78",
                  rgb2="0.9 0.92 0.95", width="256", height="1024")
    ET.SubElement(asset, "texture", type="2d", name="tabletex", builtin="flat",
                  rgb1="0.56 0.47 0.36", width="64", height="64")
    ET.SubElement(asset, "material", name="table", texture="tabletex", texuniform="true",
                  specular="0.2", shininess="0.3", reflectance="0.08")

    wb = ET.SubElement(root, "worldbody")
    ET.SubElement(wb, "light", pos="0.3 -0.6 1.8", dir="0.15 0.55 -0.8", directional="true",
                  diffuse="0.55 0.55 0.52", specular="0.3 0.3 0.3", castshadow="true")
    ET.SubElement(wb, "light", pos="1.2 1.0 1.4", dir="-0.5 -0.45 -0.75", diffuse="0.35 0.36 0.4",
                  specular="0.1 0.1 0.1", castshadow="false")
    ET.SubElement(wb, "light", pos="-0.4 0.8 1.0", dir="0.6 -0.3 -0.7", diffuse="0.25 0.25 0.28",
                  castshadow="false")
    sub(wb, "geom", name="table", type="plane", pos=[0.45, 0.35, 0], size=[1.2, 0.8, 0.05],
        material="table", friction="0.9 0.01 0.001")
    # the folding table itself (30 in deep) and the floor
    sub(wb, "geom", name="table_slab", type="box", pos=[0.45, 0.37, -0.0225], size=[0.92, 0.381, 0.0225],
        rgba="0.6 0.5 0.38 1", **VIS)
    for lx, ly in ((-0.35, 0.05), (1.25, 0.05), (-0.35, 0.69), (1.25, 0.69)):
        sub(wb, "geom", name=f"leg_{lx:+.2f}_{ly:.2f}", type="cylinder", pos=[lx, ly, -0.385], size=[0.015, 0.34],
            rgba="0.3 0.3 0.32 1", **VIS)
    sub(wb, "geom", name="floor", type="plane", pos=[0.45, 0.35, -0.74], size=[4, 4, 0.1],
        rgba="0.55 0.55 0.57 1", **VIS)

    # pour streams: one visual capsule per beaker, moved into place while it pours
    for nm in ("P1", "P2", "developer", "soap", "water"):
        sub(wb, "geom", name=f"stream_{nm}", type="capsule", pos=[0, 0, -1.0],
            size=[0.0025, 0.001], rgba="0.4 0.7 1 0.85", contype="0", conaffinity="0")
    add_cameras(wb, cfg)
    add_frame(wb, cfg)
    add_rack(wb, cfg)
    add_scale(wb, cfg)
    add_carousel(wb, cfg)
    add_auger(wb, cfg)
    add_stage(wb, cfg)
    beakers = add_beakers(wb, cfg)

    hide = add_visual_parts(asset, wb, cfg)
    hide_collision_primitives(wb, hide)

    arms = {}
    for role in ("pourer", "transfer"):
        a = cfg.at(f"arms.{role}")
        prefix = f"{role}_"
        base = inject_arm(wb, prefix, a["base_xy"], a["base_z"], a["yaw_deg"])
        add_fin_ray_gripper(base, prefix)
        arms[role] = prefix

    # ---- equality: close the crank-slider loop, plus one dormant weld per (arm, beaker)
    eq = ET.SubElement(root, "equality")
    sub(eq, "connect", name="stage_loop", site1="rod_end", site2="sled_pin", solref="0.004 1")
    for role in arms:
        for nm in beakers:
            sub(eq, "weld", name=f"grasp_{role}_{nm}", body1=f"{role}_gripper",
                body2=f"beaker_{nm}", active="false", solref="0.004 1", torquescale="1")
        # a clamped beaker blocks the jaw: modelled as a joint lock that latches with the weld,
        # so the servo stalls against a constraint (load ~1000) instead of a contact fight
        sub(eq, "joint", name=f"lock_{role}_jaw", joint1=f"{role}_gripper", active="false",
            polycoef="0 0 0 0 0", solref="0.004 1")

    # ---- actuators
    act = ET.SubElement(root, "actuator")
    jl = cfg.at("arms.joint_limits_deg")
    for role, prefix in arms.items():
        for jn in cfg.at("arms.joint_names"):
            lo, hi = (math.radians(v) for v in jl[jn])
            # the jaw runs under the firmware's Torque_Limit (<= 50 %, architecture 3.5)
            fr = "-1.2 1.2" if jn == "gripper" else "-3.35 3.35"
            sub(act, "position", class_="sts3215", name=f"{prefix}{jn}", joint=f"{prefix}{jn}",
                forcerange=fr, ctrlrange=f"{lo:.5f} {hi:.5f}")
    sub(act, "position", name="carousel", joint="carousel", kp="40", kv="4",
        forcerange="-4.4 4.4", ctrlrange="-7 7")
    sub(act, "position", name="stage", joint="stage_crank", kp="30", kv="3",
        forcerange="-4.4 4.4", ctrlrange=f"0 {math.radians(cfg.at('stations.stage.erupt_crank_deg')):.5f}")
    sub(act, "velocity", name="auger", joint="auger", kv="0.4", forcerange="-1.5 1.5",
        ctrlrange="-12 12")

    # ---- sensors
    sen = ET.SubElement(root, "sensor")
    sub(sen, "force", name="load_cell", site="load_cell_site")
    sub(sen, "jointpos", name="carousel_pos", joint="carousel")
    sub(sen, "jointpos", name="auger_pos", joint="auger")
    sub(sen, "jointpos", name="stage_pos", joint="stage_crank")
    sub(sen, "jointpos", name="sled_pos", joint="stage_sled")
    for role in arms:
        sub(sen, "framepos", name=f"{role}_grasp_pos", objtype="site", objname=f"{role}_grasp")
        sub(sen, "framequat", name=f"{role}_grasp_quat", objtype="site", objname=f"{role}_grasp")

    # NOTE: MuJoCo's compiler already offsets a mesh geom's frame to compensate for the
    # recentring it applies to the asset, so STL-origin placement is what you see.
    # fix_mesh_frames(root) is kept for diagnosis only.
    ET.indent(root, space="  ")
    OUT.write_text("<?xml version='1.0'?>\n<!-- GENERATED by software/sim/build_scene.py -->\n"
                   + ET.tostring(root, encoding="unicode"))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
