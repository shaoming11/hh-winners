import adsk.core as C, adsk.fusion as F, math, os
root = design.rootComponent
VI = lambda mm: C.ValueInput.createByReal(mm / 10)
NEW, JOIN, CUT = F.FeatureOperations.NewBodyFeatureOperation, F.FeatureOperations.JoinFeatureOperation, F.FeatureOperations.CutFeatureOperation
log = []

def make(name, origin):
    for o in list(root.occurrences):
        if o.component.name == name: o.deleteMe()
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(origin[0] / 10, origin[1] / 10, origin[2] / 10)
    o = root.occurrences.addNewComponent(m); o.component.name = name
    return o.component, origin

class Part:
    def __init__(self, name, origin):
        self.c, self.o = make(name, origin); self.body = None
    def P(self, x, y): return C.Point3D.create((x - self.o[0]) / 10, (y - self.o[1]) / 10, 0)
    def plane(self, z):
        pi = self.c.constructionPlanes.createInput(); pi.setByOffset(self.c.xYConstructionPlane, VI(z - self.o[2]))
        pl = self.c.constructionPlanes.add(pi); pl.isLightBulbOn = False; return pl
    def _ext(self, sk, sel, h, op):
        col = C.ObjectCollection.create()
        for p in sk.profiles:
            if sel(p): col.add(p)
        ei = self.c.features.extrudeFeatures.createInput(col, NEW if self.body is None else op)
        ei.setDistanceExtent(False, VI(h))
        if self.body is not None and op != NEW: ei.participantBodies = [self.body]
        f = self.c.features.extrudeFeatures.add(ei)
        if self.body is None: self.body = f.bodies.item(0)
        return f
    def box(self, x0, y0, z0, x1, y1, z1, op=JOIN):
        sk = self.c.sketches.add(self.plane(z0)); sk.sketchCurves.sketchLines.addTwoPointRectangle(self.P(x0, y0), self.P(x1, y1))
        return self._ext(sk, lambda p: True, z1 - z0, op)
    def cyl(self, x, y, z0, z1, r, op=JOIN, r_in=None):
        sk = self.c.sketches.add(self.plane(z0)); sk.sketchCurves.sketchCircles.addByCenterRadius(self.P(x, y), r / 10)
        if r_in: sk.sketchCurves.sketchCircles.addByCenterRadius(self.P(x, y), r_in / 10)
        sel = (lambda p: p.profileLoops.count == 2) if r_in else (lambda p: True)
        if r_in is None:
            sel = lambda p: True
        return self._ext(sk, sel, z1 - z0, op)
    def holes(self, pts, z0, z1, d):
        sk = self.c.sketches.add(self.plane(z0))
        for (x, y) in pts: sk.sketchCurves.sketchCircles.addByCenterRadius(self.P(x, y), d / 20)
        return self._ext(sk, lambda p: True, z1 - z0, CUT)
    def ycyl(self, x, z, y0, y1, r, op=JOIN):
        """cylinder along +Y, axis at (x, z)"""
        sgn = self.c.xZConstructionPlane.geometry.normal.y
        pi = self.c.constructionPlanes.createInput(); pi.setByOffset(self.c.xZConstructionPlane, VI((y0 - self.o[1]) * sgn))
        pl = self.c.constructionPlanes.add(pi); pl.isLightBulbOn = False
        sk = self.c.sketches.add(pl)
        cp = sk.modelToSketchSpace(C.Point3D.create((x - self.o[0]) / 10, (y0 - self.o[1]) / 10, (z - self.o[2]) / 10))
        sk.sketchCurves.sketchCircles.addByCenterRadius(cp, r / 10)
        col = C.ObjectCollection.create(); col.add(sk.profiles.item(0))
        ei = self.c.features.extrudeFeatures.createInput(col, NEW if self.body is None else op)
        ei.setDistanceExtent(False, VI((y1 - y0) * sgn))
        if self.body is not None: ei.participantBodies = [self.body]
        f = self.c.features.extrudeFeatures.add(ei)
        bb = f.bodies.item(0).boundingBox if f.bodies.count else None
        # extrude direction check: if it went the wrong way, flip
        if f.bodies.count and op != CUT:
            pass
        if self.body is None: self.body = f.bodies.item(0)
        return f
    def ychk(self, f, y0, y1):
        pass

