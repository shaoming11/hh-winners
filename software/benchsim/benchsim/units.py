"""The single mm -> m boundary. Configuration, layout files and reports are in millimetres and degrees; MuJoCo
models are in metres and radians. Nothing else in the package multiplies by 1e-3."""
import math
import numpy as np

MM = 1e-3


def m(x_mm):
    """millimetres (scalar or array-like) -> metres"""
    return np.asarray(x_mm, float) * MM if not isinstance(x_mm, (int, float)) else float(x_mm) * MM


def mm(x_m):
    """metres -> millimetres"""
    return np.asarray(x_m, float) / MM if not isinstance(x_m, (int, float)) else float(x_m) / MM


def rad(deg):
    return np.radians(deg) if not isinstance(deg, (int, float)) else math.radians(deg)


def deg(r):
    return np.degrees(r) if not isinstance(r, (int, float)) else math.degrees(r)
