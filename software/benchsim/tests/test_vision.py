import math

import mujoco
import numpy as np
import pytest

from benchsim import vision
from benchsim.backends.sim import SimWorld


def teleport(w, beaker, xyz_mm):
    a = w.m.joint('beaker_' + beaker).qposadr[0]
    w.d.qpos[a:a + 3] = np.asarray(xyz_mm, float) / 1000; w.d.qpos[a + 3:a + 7] = [1, 0, 0, 0]
    mujoco.mj_forward(w.m, w.d)


@pytest.fixture
def world(built):
    model, b = built
    return SimWorld(model=model, builder=b)                      # fresh MjData on the shared compiled model


def test_pick_pocket_beaker_present_then_absent(world):
    cam = vision.SimCamera(world, 'bench_cam', 640, 480)
    assert isinstance(cam, vision.Camera)
    roi = cam.pinhole().beaker_roi(vision.site_mm(world.m, world.d, 'pocket0'))
    img, meta = cam.grab()
    assert img.shape == (480, 640, 3) and img.dtype == np.uint8
    assert meta['camera'] == 'bench_cam' and meta['source'] == 'sim' and meta['intrinsics']['width'] == 640
    with_p1 = vision.beaker_check(img, roi)
    assert with_p1['present'], with_p1
    teleport(world, 'P1', [-500, -500, 50])
    img2, _ = cam.grab()
    without = vision.beaker_check(img2, roi)
    assert not without['present'], without
    # the projected ROI is where the beaker is: most of the pixels that change when P1 leaves lie inside it
    changed = np.abs(img.astype(int) - img2.astype(int)).sum(-1) > 30
    x0, y0, x1, y1 = roi
    assert changed[y0:y1, x0:x1].sum() / changed.sum() > 0.8
    cam.close()


def test_reference_test_at_the_scale(world):
    cam = vision.SimCamera(world, 'bench_cam', 640, 480)
    roi = cam.pinhole().beaker_roi(vision.site_mm(world.m, world.d, 'scale_centre'))
    empty, _ = cam.grab()
    assert not vision.beaker_present(empty, roi, reference=empty)
    teleport(world, 'P1', vision.site_mm(world.m, world.d, 'scale_centre') + [0, 0, 1])
    img, _ = cam.grab()
    chk = vision.beaker_check(img, roi, reference=empty)
    assert chk['present'] and chk['test'] == 'reference', chk
    cam.close()


def test_pinhole_projection():
    # camera at (0, 0, 1000) mm looking straight down (-z), camera x = world x, camera y = world y
    pin = vision.PinholeCamera.from_fovy([0, 0, 1000], np.eye(3), 60.0, 640, 480)
    f = 240 / math.tan(math.radians(30))
    u, v, z = pin.project([100, 50, 0])[0]
    assert abs(z - 1000) < 1e-9 and abs(u - (320 + f * 0.1)) < 1e-9 and abs(v - (240 - f * 0.05)) < 1e-9
    assert abs(pin.mm_per_px([0, 0, 0]) - 1000 / f) < 1e-12
    x0, y0, x1, y1 = pin.roi_cylinder([0, 0, 0], 28, 74)
    assert x0 < 320 < x1 and y0 < 240 < y1
    with pytest.raises(ValueError):
        pin.roi_cylinder([0, 0, 2000], 28, 74)                     # behind the camera


def test_foam_height_synthetic():
    img = np.full((100, 60, 3), 30, np.uint8)
    roi = (10, 0, 50, 100)
    assert vision.foam_height_px(img, roi) == 0
    img[40:100, 20:40] = (250, 248, 240)                            # 60-row column, half the ROI width
    assert vision.foam_height_px(img, roi) == 60
    img[50:52, 20:40] = 30                                          # a 2-row gap is tolerated
    assert vision.foam_height_px(img, roi) == 60
    img[30:34, 20:40] = (250, 248, 240)                             # a separate blob above a 6-row gap is not counted
    assert vision.foam_height_px(img, roi) == 60
    assert abs(vision.foam_height_mm(img, roi, 0.8) - 48.0) < 1e-9
    img[95:100, 20:40] = 30                                         # nothing at the neck: no column
    assert vision.foam_height_px(img, roi) == 0


def test_real_camera_is_lazy():
    cam = vision.RealCamera(0)
    assert isinstance(cam, vision.Camera) and cam.cap is None and cam.pinhole() is None
    cam.close()
