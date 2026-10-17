"""Camera checks with OpenCV: is a beaker where the plan expects one, and how tall is the foam.

The same functions run on a webcam frame and on the sim's rendered "webcam" camera, so the
thresholds get exercised before the real camera exists.  Both are deliberately simple colour /
contour tests (docs/plan_36h.md: "simple colour/contour test").
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# Default ROI for the bench "webcam" camera (640x480, looking at the flask from the south):
# the column of pixels above the flask mouth, where foam and nothing else appears.
FOAM_ROI = (240, 40, 400, 250)


def foam_height_px(img: np.ndarray, roi=None, baseline: np.ndarray | None = None) -> tuple[int, np.ndarray | None]:
    """Height in pixels of the cream-coloured foam column above the flask, within `roi`
    (x0, y0, x1, y1).  If a `baseline` frame (same camera, before the reaction) is given, only
    pixels that CHANGED count, which rejects pale bench parts.  Returns (height_px, mask)."""
    if cv2 is None:
        return 0, None
    x0, y0, x1, y1 = roi or FOAM_ROI
    crop = img[y0:y1, x0:x1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    # foam: bright, low saturation, warm hue
    mask = cv2.inRange(hsv, (0, 0, 190), (40, 90, 255))
    if baseline is not None:
        diff = cv2.absdiff(crop, baseline[y0:y1, x0:x1]).max(axis=2)
        mask = cv2.bitwise_and(mask, (diff > 40).astype(np.uint8) * 255)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cols = mask.sum(axis=1)
    rows = np.where(cols > 0.25 * mask.shape[1] * 255)[0]
    if len(rows) == 0:
        return 0, mask
    return int(rows.max() - rows.min() + 1), mask


def beaker_present(img: np.ndarray, roi) -> tuple[bool, float]:
    """Is there a tall, pale, roughly vertical object in the ROI?  Returns (present, score)."""
    if cv2 is None:
        return True, 1.0
    x0, y0, x1, y1 = roi
    crop = img[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = 0.0
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if h > 0.35 * crop.shape[0] and w > 0.15 * crop.shape[1]:
            best = max(best, h / crop.shape[0])
    return best > 0.35, best
