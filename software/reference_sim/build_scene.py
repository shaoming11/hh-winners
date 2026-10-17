"""Build a MuJoCo scene from the Update-13 layout and pinned SO-101 assets."""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from bench import ROOT, load_layout


HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "assets" / "so101" / "so101_new_calib.xml"
OUT = HERE / "build" / "bench.xml"


def num(value: float) -> str:
    return f"{value:.6f}"


def v3(x: float, y: float, z: float) -> str:
    return f"{num(x)} {num(y)} {num(z)}"


def add_box(parent: ET.Element, name: str, lo: tuple[float, float, float],
            hi: tuple[float, float, float], rgba: str, *, collision: bool = True) -> None:
    pos = tuple((a + b) / 2 for a, b in zip(lo, hi))
    half = tuple((b - a) / 2 for a, b in zip(lo, hi))
    attrs = {
        "name": name, "type": "box", "pos": v3(*pos), "size": v3(*half), "rgba": rgba,
        "contype": "1" if collision else "0", "conaffinity": "1" if collision else "0",
    }
    ET.SubElement(parent, "geom", attrs)


def add_cylinder(parent: ET.Element, name: str, pos: tuple[float, float, float],
                 radius: float, half_height: float, rgba: str, *, collision: bool = True) -> None:
    attrs = {
        "name": name, "type": "cylinder", "pos": v3(*pos), "size": f"{num(radius)} {num(half_height)}",
        "rgba": rgba, "contype": "1" if collision else "0", "conaffinity": "1" if collision else "0",
    }
    if not collision:
        attrs["mass"] = "0"
    ET.SubElement(parent, "geom", attrs)


def prefix_robot_names(root: ET.Element, prefix: str) -> None:
    for elem in root.iter():
        if "name" in elem.attrib and elem.tag in {"body", "joint", "site", "actuator", "position"}:
            elem.attrib["name"] = prefix + elem.attrib["name"]
        if elem.tag == "position" and "joint" in elem.attrib:
            elem.attrib["joint"] = prefix + elem.attrib["joint"]


def add_robot(model: ET.Element, source: ET.Element, prefix: str, base_xy: tuple[float, float]) -> None:
    body = copy.deepcopy(source.find("worldbody/body"))
    assert body is not None
    body.attrib["pos"] = v3(base_xy[0], base_xy[1], 0.020)
    yaw = math.radians(-90)
    body.attrib["quat"] = f"{num(math.cos(yaw / 2))} 0 0 {num(math.sin(yaw / 2))}"
    prefix_robot_names(body, prefix)
    model.find("worldbody").append(body)

    source_act = source.find("actuator")
    target_act = model.find("actuator")
    assert source_act is not None and target_act is not None
    for actuator in source_act:
        clone = copy.deepcopy(actuator)
        prefix_robot_names(clone, prefix)
        target_act.append(clone)


def add_extrusions(world: ET.Element) -> None:
    # Final Update-13 2020 frame, all dimensions in mm in the source docs.
    rails = [
        ("Y_left", (245, 290, 0), (265, 690, 20)),
        ("Y_right", (665, 270, 0), (685, 670, 20)),
        ("X_front", (245, 572.5, 0), (685, 592.5, 20)),
        ("X_back", (245, 642.3, 0), (685, 662.3, 20)),
        ("E6", (265, 430, 0), (665, 450, 20)),
        ("S1", (360, 30, 0), (380, 430, 20)),
        ("S2", (520, 30, 0), (540, 430, 20)),
    ]
    for name, lo, hi in rails:
        add_box(world, f"rail_{name}", tuple(x / 1000 for x in lo), tuple(x / 1000 for x in hi),
                "0.28 0.30 0.33 1")


def add_scale(world: ET.Element) -> None:
    # WS-01 base and load cell are represented by the measured envelope.
    add_box(world, "scale_base", (0.547, 0.3867, 0.0), (0.664, 0.4545, 0.045), "0.16 0.19 0.22 1")
    # Flexure block is rendered but not a hard support, so pan load passes through its spring.
    add_box(world, "load_cell", (0.584, 0.401, 0.045), (0.659, 0.4137, 0.0577),
            "0.68 0.70 0.72 1", collision=False)
    pan = ET.SubElement(world, "body", {"name": "scale_pan", "pos": "0.620 0.407 0.0577"})
    ET.SubElement(pan, "inertial", {"pos": "0 0 0.004", "mass": "0.10",
                                    "diaginertia": "0.0001 0.0001 0.0001"})
    ET.SubElement(pan, "joint", {"name": "scale_flex", "type": "slide", "axis": "0 0 1",
                                  "range": "-0.003 0.003", "limited": "true", "stiffness": "20000",
                                  "damping": "60"})
    # The central weighing surface sits at Z=63.7 mm; the outer locating ring rises to 71.7.
    add_cylinder(pan, "scale_pan_geom", (0, 0, 0.003), 0.052, 0.003, "0.68 0.72 0.75 1")
    # The 56.6 mm locating bore clears a 56 mm beaker by 0.3 mm per side.
    ring_inner_radius, ring_height, ring_wall, segments = 0.0283, 0.008, 0.001, 64
    ring_radius = (ring_inner_radius + ring_wall / 2) / math.cos(math.pi / segments)
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        px, py = ring_radius * math.cos(angle), ring_radius * math.sin(angle)
        arc_half = ring_radius * math.sin(math.pi / segments) * 0.98
        quat = f"{num(math.cos(angle / 2))} 0 0 {num(math.sin(angle / 2))}"
        ET.SubElement(pan, "geom", {
            "name": f"scale_locating_ring_{i:02d}", "type": "box",
            "pos": v3(px, py, 0.010), "quat": quat,
            "size": v3(ring_wall / 2, arc_half, ring_height / 2),
            "rgba": "0.68 0.72 0.75 0.55",
        })
    ET.SubElement(pan, "site", {"name": "scale_sensor_site", "pos": "0 0 0", "size": "0.002"})


def add_beaker(parent: ET.Element, name: str, xy: tuple[float, float], bottom_z: float,
               *, dynamic: bool, local: bool = False) -> ET.Element:
    """Thin wall segments keep the beaker open and make the 56 x 74 mm envelope explicit."""
    attrs = {"name": name, "pos": v3(xy[0], xy[1], bottom_z)}
    body = ET.SubElement(parent, "body", attrs)
    if dynamic:
        ET.SubElement(body, "freejoint", {"name": f"{name}_free"})
        ET.SubElement(body, "inertial", {"pos": "0 0 0.037", "mass": "0.015",
                                         "diaginertia": "0.000008 0.000008 0.000004"})
    add_cylinder(body, f"{name}_floor", (0, 0, 0.001), 0.0274, 0.001,
                 "0.77 0.90 0.95 0.22", collision=dynamic)
    radius, wall, height, segments = 0.0274, 0.0012, 0.074, 12
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        px, py = radius * math.cos(angle), radius * math.sin(angle)
        arc_half = radius * math.sin(math.pi / segments) * 0.94
        quat = f"{num(math.cos(angle / 2))} 0 0 {num(math.sin(angle / 2))}"
        ET.SubElement(body, "geom", {
            "name": f"{name}_wall_{i:02d}", "type": "box", "pos": v3(px, py, height / 2),
            "quat": quat, "size": v3(wall / 2, arc_half, height / 2),
            "rgba": "0.77 0.90 0.95 0.18", "contype": "1" if dynamic else "0",
            "conaffinity": "1" if dynamic else "0",
        })
    ET.SubElement(body, "site", {"name": f"{name}_grasp", "pos": "0 0 0.052",
                                  "size": "0.002", "rgba": "0.9 0.1 0.1 0.6"})
    return body


def add_rack_and_auger(world: ET.Element) -> None:
    layout = load_layout()
    rack = layout["rack_stands"]
    for i, pocket in enumerate(rack):
        x, y = (v / 1000 for v in pocket["xy"])
        add_cylinder(world, f"rack_pocket_{i + 1}", (x, y, 0.0582), 0.0283, 0.002,
                     "0.17 0.37 0.43 1")
        add_beaker(world, f"rack_beaker_{i + 1}", (x, y), 0.0602, dynamic=True)
    # DH-01 outlet over the carousel's auger pocket, mounted on PS-01.
    ax, ay = (v / 1000 for v in layout["carousel"]["auger"])
    # The structural column is offset from the rotating deck; a short cantilever places
    # the outlet over the auger pocket while leaving the carousel's sweep unobstructed.
    post_x = ax + 0.150
    add_cylinder(world, "auger_post", (post_x, ay, 0.080), 0.018, 0.080, "0.20 0.22 0.24 1")
    add_box(world, "auger_cantilever", (ax - 0.010, ay - 0.008, 0.158),
            (post_x + 0.018, ay + 0.008, 0.174), "0.20 0.22 0.24 1")
    add_cylinder(world, "auger_head", (ax, ay, 0.164), 0.026, 0.008, "0.86 0.70 0.22 1")
    add_cylinder(world, "auger_outlet", (ax, ay, 0.1685), 0.005, 0.002, "0.15 0.15 0.15 1")


def add_carousel(world: ET.Element, actuator: ET.Element) -> None:
    cfg = load_layout()["carousel"]
    cx, cy = (v / 1000 for v in cfg["centre"])
    deck_z = 0.0546
    body = ET.SubElement(world, "body", {"name": "carousel", "pos": v3(cx, cy, deck_z)})
    ET.SubElement(body, "inertial", {"pos": "0 0 0.01", "mass": "2.0",
                                     "diaginertia": "0.0022 0.0022 0.0044"})
    ET.SubElement(body, "joint", {"name": "carousel_hinge", "type": "hinge", "axis": "0 0 1",
                                  "range": "-6.28319 6.28319", "limited": "true", "damping": "0.4"})
    # The deck supports four independent free beakers in the pocket ring.
    add_cylinder(body, "carousel_deck", (0, 0, 0.0035), 0.118, 0.0035,
                 "0.45 0.47 0.50 1")
    add_cylinder(body, "carousel_ring", (0, 0, 0.010), 0.105, 0.006,
                 "0.75 0.77 0.80 1", collision=False)
    initial = math.radians(cfg["rotation_deg"])
    for i in range(4):
        angle = initial + i * math.pi / 2
        px, py = 0.084 * math.cos(angle), 0.084 * math.sin(angle)
        # Four low locator rings around the beakers; the deck itself supports the bottoms.
        for j in range(12):
            a = 2 * math.pi * j / 12
            rr = 0.0283
            lx, ly = px + rr * math.cos(a), py + rr * math.sin(a)
            half_tangent = rr * math.sin(math.pi / 12) * 0.9
            quat = f"{num(math.cos(a / 2))} 0 0 {num(math.sin(a / 2))}"
            ET.SubElement(body, "geom", {
                "name": f"pocket_{i + 1}_{j:02d}", "type": "box", "pos": v3(lx, ly, 0.013),
                "quat": quat, "size": v3(0.001, half_tangent, 0.006),
                "rgba": "0.18 0.39 0.48 1",
            })
    ET.SubElement(actuator, "position", {"name": "carousel_position", "joint": "carousel_hinge",
                                         "kp": "8", "kv": "1.5", "forcerange": "-3.43 3.43",
                                         "ctrlrange": "-6.28319 6.28319"})


def add_carousel_beakers(world: ET.Element) -> None:
    """Use free bodies on the rotating deck so an arm can actually pick a beaker."""
    cfg = load_layout()["carousel"]
    cx, cy = (v / 1000 for v in cfg["centre"])
    radius = 0.084
    initial = math.radians(cfg["rotation_deg"])
    for i in range(4):
        angle = initial + i * math.pi / 2
        xy = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        add_beaker(world, f"carousel_beaker_{i + 1}", xy, cfg["beaker_bottom_z"] / 1000,
                   dynamic=True)


def add_stage(world: ET.Element, actuator: ET.Element) -> None:
    body = ET.SubElement(world, "body", {"name": "stage_sled", "pos": "0.450 0.282 0.004"})
    ET.SubElement(body, "inertial", {"pos": "0 0 0.08", "mass": "0.69",
                                     "diaginertia": "0.008 0.008 0.008"})
    ET.SubElement(body, "joint", {"name": "stage_slide", "type": "slide", "axis": "0 1 0",
                                  "range": "-0.0973 0", "limited": "true", "damping": "35"})
    add_box(body, "stage_plate", (-0.07, -0.07, -0.001), (0.07, 0.07, 0.005), "0.24 0.27 0.29 1")
    add_cylinder(body, "flask", (0, 0, 0.088), 0.043, 0.074, "0.70 0.86 0.93 0.25", collision=False)
    add_cylinder(body, "catch_well", (0, 0, 0.045), 0.065, 0.045, "0.60 0.63 0.67 0.25", collision=False)
    funnel = ET.SubElement(body, "body", {"name": "funnel", "pos": "0 0 0.229"})
    add_cylinder(funnel, "funnel_rim", (0, 0, 0.004), 0.051, 0.004, "0.20 0.66 0.42 0.75", collision=False)
    add_cylinder(funnel, "funnel_stem", (0, 0, -0.027), 0.012, 0.027, "0.20 0.66 0.42 0.75", collision=False)
    ET.SubElement(actuator, "position", {"name": "stage_position", "joint": "stage_slide",
                                         "kp": "400", "kv": "40", "ctrlrange": "-0.0973 0"})


def build() -> Path:
    if not UPSTREAM.exists():
        raise FileNotFoundError(f"SO-101 assets missing; run {HERE / 'fetch_so101.py'}")
    source = ET.parse(UPSTREAM).getroot()
    model = ET.Element("mujoco", {"model": "wet_lab_reference"})
    ET.SubElement(model, "compiler", {"angle": "radian", "meshdir": "../assets/so101", "autolimits": "true"})
    ET.SubElement(model, "option", {"timestep": "0.002", "integrator": "implicitfast", "iterations": "60",
                                     "cone": "elliptic", "gravity": "0 0 -9.81"})
    ET.SubElement(model, "size", {"njmax": "5000", "nconmax": "2000"})
    for default in source.findall("default"):
        model.append(copy.deepcopy(default))
    asset = ET.SubElement(model, "asset")
    source_asset = source.find("asset")
    assert source_asset is not None
    asset.extend(copy.deepcopy(list(source_asset)))
    world = ET.SubElement(model, "worldbody")
    ET.SubElement(world, "light", {"name": "key", "pos": "0.2 -0.5 1.7", "dir": "0.3 0.5 -1", "diffuse": "0.8 0.8 0.8"})
    ET.SubElement(world, "geom", {"name": "table_top", "type": "box", "pos": "0.60 0.38 -0.025",
                                  "size": "0.62 0.40 0.025", "rgba": "0.49 0.38 0.27 1", "friction": "0.8 0.01 0.001"})
    add_extrusions(world)
    add_scale(world)
    add_rack_and_auger(world)
    actuator = ET.SubElement(model, "actuator")
    add_carousel(world, actuator)
    add_carousel_beakers(world)
    add_stage(world, actuator)

    layout = load_layout()
    add_robot(model, source, "pourer_", tuple(v / 1000 for v in layout["pourer_base"]["xy"]))
    add_robot(model, source, "transfer_", tuple(v / 1000 for v in layout["transfer_base"]["xy"]))

    equality = ET.SubElement(model, "equality")
    pickable = ["rack_beaker_1", "rack_beaker_2", "rack_beaker_3"] + \
               [f"carousel_beaker_{i}" for i in range(1, 5)]
    for arm in ("pourer", "transfer"):
        for beaker in pickable:
            ET.SubElement(equality, "weld", {
                "name": f"weld_{arm}_{beaker}", "site1": f"{arm}_gripperframe",
                "site2": f"{beaker}_grasp", "active": "false",
                "solref": "0.01 1", "solimp": "0.95 0.99 0.001",
            })

    # Proximity plus the weld is the grasp abstraction. Do not let the stock jaw
    # geometry fight that constraint against the thin beaker wall meshes.
    contact = ET.SubElement(model, "contact")
    for arm in ("pourer", "transfer"):
        for beaker in pickable:
            for gripper_body in (f"{arm}_gripper", f"{arm}_moving_jaw_so101_v1"):
                ET.SubElement(contact, "exclude", {
                    "body1": gripper_body, "body2": beaker,
                })

    sensor = ET.SubElement(model, "sensor")
    ET.SubElement(sensor, "jointpos", {"name": "scale_deflection", "joint": "scale_flex"})
    ET.SubElement(sensor, "jointactuatorfrc", {"name": "stage_motor_force", "joint": "stage_slide"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(model, space="  ")
    ET.ElementTree(model).write(OUT, encoding="utf-8", xml_declaration=True)
    return OUT


if __name__ == "__main__":
    print(build())
