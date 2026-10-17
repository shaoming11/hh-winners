"""Camera interface and the image checks shared by simulated and webcam frames.

A ``Camera`` returns ``(image, metadata)``: an HxWx3 uint8 RGB array and a dict with the time (s), the camera name, the
source ('sim' or 'real') and the pinhole intrinsics in pixels. ``SimCamera`` renders a MuJoCo camera of a ``SimWorld``.
``RealCamera`` reads a USB webcam through OpenCV, which is imported and opened only on the first ``grab()`` (tests never
open it).

The image checks are plain numpy on RGB arrays and take a region of interest ``roi = (x0, y0, x1, y1)`` in pixels (x1, y1
exclusive). The same functions run on sim renders and webcam frames:
    beaker_check / beaker_present   colour test: the fraction of bright, unsaturated pixels (clear or white PP wall) in
                                    the ROI. With an empty-station reference frame it is instead the mean absolute
                                    difference to that frame (needed where the background is itself white, e.g. the pan)
    foam_height_px / foam_height_mm rows of foam-coloured pixels rising from the bottom edge of the ROI (the flask neck)
Thresholds are in bench_params.toml [vision]. They were calibrated on sim renders and are assumptions for the webcam
until measured on the bench (real print colours and lighting).

ROIs come from projecting world points (mm) through ``PinholeCamera``: built from a MuJoCo camera (pose + fovy) with
``mujoco_pinhole``, or for the webcam from a calibrated pose and intrinsics. The projection is an ideal pinhole with no
lens distortion (approximation for a webcam).
"""
import math
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from . import layout
from .units import mm


def _params(params):
    return params or layout.load_params()


# ======================================================================= pinhole model
@dataclass
class PinholeCamera:
    """ideal pinhole in mm and pixels. ``pos``: camera centre (mm, world). ``R``: 3x3, columns are the camera x (right),
    y (up) and z (backward) axes in world coordinates; the camera looks along -z (MuJoCo convention). Rows grow downward."""
    pos: np.ndarray
    R: np.ndarray
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @staticmethod
    def from_fovy(pos_mm, R, fovy_deg, width, height):
        """square pixels, principal point at the image centre (how MuJoCo renders a camera)"""
        f = (height / 2) / math.tan(math.radians(fovy_deg) / 2)
        return PinholeCamera(np.asarray(pos_mm, float), np.asarray(R, float).reshape(3, 3), f, f, width / 2, height / 2, width, height)

    def intrinsics(self):
        return dict(fx=round(self.fx, 3), fy=round(self.fy, 3), cx=self.cx, cy=self.cy, width=self.width, height=self.height)

    def project(self, p_mm):
        """world points (mm, shape (3,) or (N, 3)) -> array (N, 3) of (u, v, depth_mm); depth <= 0 is behind the camera"""
        pc = (np.atleast_2d(np.asarray(p_mm, float)) - self.pos) @ self.R
        z = -pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.c_[self.cx + self.fx * pc[:, 0] / z, self.cy - self.fy * pc[:, 1] / z, z]

    def mm_per_px(self, p_mm):
        """size of one pixel (mm) at the depth of world point p (vertical direction)"""
        return float(self.project(p_mm)[0, 2]) / self.fy

    def roi_cylinder(self, base_mm, radius_mm, height_mm, margin_px=0, n=24):
        """pixel bounding box of an upright cylinder standing on ``base_mm`` (e.g. a beaker on a pocket floor), clipped to
        the image; ValueError if any of it is behind the camera or the box is empty"""
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        ring = np.c_[radius_mm * np.cos(a), radius_mm * np.sin(a), np.zeros(n)]
        pts = np.r_[ring, ring + [0, 0, height_mm]] + np.asarray(base_mm, float)
        uvz = self.project(pts)
        if np.any(uvz[:, 2] <= 0): raise ValueError('ROI is behind the camera')
        x0 = max(0, int(math.floor(uvz[:, 0].min())) - margin_px); y0 = max(0, int(math.floor(uvz[:, 1].min())) - margin_px)
        x1 = min(self.width, int(math.ceil(uvz[:, 0].max())) + margin_px); y1 = min(self.height, int(math.ceil(uvz[:, 1].max())) + margin_px)
        if x1 <= x0 or y1 <= y0: raise ValueError('ROI is outside the image')
        return x0, y0, x1, y1

    def beaker_roi(self, base_mm, params=None):
        """ROI of a beaker standing on ``base_mm`` (beaker size from [beaker], padding from [vision])"""
        P = _params(params); B = P['beaker']
        return self.roi_cylinder(base_mm, B['od'] / 2, B['height'], P['vision']['roi_margin_px'])


def mujoco_pinhole(model, data, camera, width, height):
    """PinholeCamera of a MuJoCo camera at its current pose (call mj_forward first if the pose changed)"""
    cid = model.camera(camera).id
    return PinholeCamera.from_fovy(mm(data.cam_xpos[cid].copy()), data.cam_xmat[cid].reshape(3, 3).copy(), float(model.cam_fovy[cid]), width, height)


def site_mm(model, data, site):
    """world position of a MuJoCo site in mm (e.g. 'pocket0', 'scale_centre', 'flask_neck_top')"""
    return mm(data.site(site).xpos.copy())


# ======================================================================= cameras
@runtime_checkable
class Camera(Protocol):
    name: str

    def grab(self):
        """-> (HxWx3 uint8 RGB image, dict(t, camera, source, intrinsics, ...))"""
        ...


class SimCamera:
    """offscreen render of a named MuJoCo camera of a SimWorld ('bench_cam', 'foam_cam', 'overview', 'top')"""

    def __init__(self, world, name, width=640, height=480):
        from .render import Renderer
        self.w = world; self.name = name; self.width = width; self.height = height
        self.r = Renderer(world.m, width, height)

    def pinhole(self):
        return mujoco_pinhole(self.w.m, self.w.d, self.name, self.width, self.height)

    def grab(self):
        img = self.r.frame(self.w.d, self.name)
        return img, dict(t=round(self.w.time, 4), camera=self.name, source='sim', intrinsics=self.pinhole().intrinsics())

    def close(self): self.r.close()


class RealCamera:
    """USB webcam through OpenCV (placeholder; not used in tests). OpenCV is imported and the device opened on the first
    ``grab()``. ``pinhole``: a calibrated PinholeCamera for ROIs and intrinsics, or None (intrinsics then unknown)."""

    def __init__(self, device_index=0, name='webcam', width=None, height=None, pinhole=None, clock=time.monotonic):
        self.device_index = device_index; self.name = name; self.width = width; self.height = height
        self.pin = pinhole; self.clock = clock; self.cap = None

    def pinhole(self): return self.pin

    def open(self):
        import cv2
        cap = cv2.VideoCapture(self.device_index)
        if self.width: cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height: cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened(): raise RuntimeError('webcam %s did not open' % self.device_index)
        self.cap = cap

    def grab(self):
        if self.cap is None: self.open()
        ok, frame = self.cap.read()
        if not ok: raise RuntimeError('webcam %s returned no frame' % self.device_index)
        img = np.ascontiguousarray(frame[..., ::-1])                  # OpenCV BGR -> RGB
        return img, dict(t=round(self.clock(), 4), camera=self.name, source='real',
                         intrinsics=self.pin.intrinsics() if self.pin else None)

    def close(self):
        if self.cap is not None: self.cap.release(); self.cap = None


# ======================================================================= image checks (shared by sim and webcam)
def crop(img, roi):
    x0, y0, x1, y1 = roi
    return np.asarray(img)[y0:y1, x0:x1, :3]


def sat_val(img):
    """HSV saturation and value in 0..1 of an RGB uint8 array"""
    x = np.asarray(img)[..., :3].astype(np.float32) / 255.0
    mx = x.max(-1); mn = x.min(-1)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0), mx


def beaker_fraction(img, roi, params=None):
    """fraction of ROI pixels that look like a clear/white PP beaker wall: bright and unsaturated"""
    V = _params(params)['vision']; s, v = sat_val(crop(img, roi))
    return float(((s < V['beaker_s_max']) & (v > V['beaker_v_min'])).mean())


def reference_difference(img, reference, roi):
    """mean absolute difference (0..255) between the ROI of a frame and of an empty-station reference frame"""
    a = crop(img, roi).astype(np.float32); b = crop(reference, roi).astype(np.float32)
    if a.shape != b.shape: raise ValueError('frame and reference differ in size')
    return float(np.abs(a - b).mean())


def beaker_check(img, roi, reference=None, params=None):
    """-> dict(present, test, value, threshold, roi). Colour test by default; difference test with a reference frame."""
    V = _params(params)['vision']
    if reference is None:
        val = beaker_fraction(img, roi, params); thr = V['beaker_min_frac']; test = 'colour'
    else:
        val = reference_difference(img, reference, roi); thr = V['reference_diff_min']; test = 'reference'
    return dict(present=bool(val >= thr), test=test, value=round(val, 4), threshold=thr, roi=[int(r) for r in roi])


def beaker_present(img, roi, reference=None, params=None):
    return beaker_check(img, roi, reference, params)['present']


def foam_mask(img, params=None):
    """pixels within ``foam_rgb_tol`` (Euclidean RGB) of ``foam_rgb``"""
    V = _params(params)['vision']
    d = np.asarray(img)[..., :3].astype(np.float32) - np.asarray(V['foam_rgb'], np.float32)
    return np.sqrt((d * d).sum(-1)) <= V['foam_rgb_tol']


def foam_height_px(img, roi, params=None):
    """height of the foam column in pixels: rows (from the bottom edge of the ROI upward) in which at least
    ``foam_row_min_frac`` of the pixels are foam-coloured, stopping at the first gap longer than ``foam_max_gap_rows``.
    Put the ROI's bottom edge on the flask neck top. 0 if the bottom row has no foam."""
    V = _params(params)['vision']
    rows = foam_mask(crop(img, roi), params).mean(axis=1) >= V['foam_row_min_frac']
    top = None; gap = 0
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]: top = i; gap = 0
        elif top is None: break
        else:
            gap += 1
            if gap > V['foam_max_gap_rows']: break
    return 0 if top is None else len(rows) - top


def foam_height_mm(img, roi, mm_per_px, params=None):
    """foam column height in mm; ``mm_per_px`` from PinholeCamera.mm_per_px at the flask neck (small-angle approximation:
    the column is treated as lying in the plane at that depth)"""
    return foam_height_px(img, roi, params) * float(mm_per_px)
