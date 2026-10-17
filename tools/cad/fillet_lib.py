import adsk.core as C, adsk.fusion as F, math
def classify(body, e):
    """returns 'convex'/'concave'/None for a linear edge between two planar faces"""
    if e.faces.count!=2: return None
    f1,f2=e.faces.item(0),e.faces.item(1)
    p=e.pointOnEdge
    for f in (f1,f2):
        g=f.geometry
        if isinstance(g,(C.Cone,C.Torus,C.NurbsSurface,C.Sphere,C.EllipticalCylinder,C.EllipticalCone)): return None
        if isinstance(g,C.Cylinder):
            ok,nn=f.evaluator.getNormalAtPoint(p)
            ax=g.axis; o=g.origin
            v=C.Vector3D.create(p.x-o.x,p.y-o.y,p.z-o.z)
            t=v.dotProduct(ax)/ax.dotProduct(ax); r=C.Vector3D.create(v.x-ax.x*t,v.y-ax.y*t,v.z-ax.z*t)
            if nn.dotProduct(r)<0: return None   # hole / bore / socket: keep sharp
    ok,n1=f1.evaluator.getNormalAtPoint(p); ok,n2=f2.evaluator.getNormalAtPoint(p)
    if abs(n1.dotProduct(n2))>0.98: return None
    b=n1.copy(); b.subtract(n2); b.normalize(); b.scaleBy(0.02)
    q=p.copy(); q.translateBy(b)
    return 'concave' if body.pointContainment(q)==F.PointContainment.PointInsidePointContainment else 'convex'
def in_boxes(e, boxes):
    bb=e.boundingBox
    for (x0,y0,z0,x1,y1,z1) in boxes:
        if bb.minPoint.x*10>=x0-0.01 and bb.maxPoint.x*10<=x1+0.01 and bb.minPoint.y*10>=y0-0.01 and bb.maxPoint.y*10<=y1+0.01 and bb.minPoint.z*10>=z0-0.01 and bb.maxPoint.z*10<=z1+0.01: return True
    return False
def edge_len(e): return e.length*10
def try_fillet(comp, body, edges, r):
    if not edges: return 0
    fe=comp.features.filletFeatures
    col=C.ObjectCollection.create()
    for e in edges: col.add(e)
    try:
        fi=fe.createInput(); fi.addConstantRadiusEdgeSet(col, C.ValueInput.createByReal(r/10), False)
        fe.add(fi); return len(edges)
    except Exception:
        n=0
        for e in edges:
            for rr in (r, r*0.5):
                try:
                    if not e.isValid: break
                    c2=C.ObjectCollection.create(); c2.add(e)
                    fi=fe.createInput(); fi.addConstantRadiusEdgeSet(c2, C.ValueInput.createByReal(rr/10), False); fe.add(fi); n+=1; break
                except Exception: pass
        return n
def try_chamfer(comp, edges, d):
    if not edges: return 0
    ce=comp.features.chamferFeatures
    col=C.ObjectCollection.create()
    for e in edges: col.add(e)
    try:
        ci=ce.createInput2(); ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, C.ValueInput.createByReal(d/10), False); ce.add(ci); return len(edges)
    except Exception:
        n=0
        for e in edges:
            try:
                if not e.isValid: continue
                c2=C.ObjectCollection.create(); c2.add(e); ci=ce.createInput2(); ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(c2, C.ValueInput.createByReal(d/10), False); ce.add(ci); n+=1
            except Exception: pass
        return n
def process(comp, keep_boxes, r_out=1.5, r_in=2.0, ch=0.6, min_len=3.0):
    body=comp.bRepBodies.item(0)
    v0=body.volume
    # 1) bed chamfer: convex edges lying at z=0
    bed=[e for e in body.edges if classify(body,e)=='convex' and abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4]
    nc=try_chamfer(comp, bed, ch)
    body=comp.bRepBodies.item(0)
    # 2) concave edges (not in fit boxes)
    conc=[e for e in body.edges if classify(body,e)=='concave' and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len]
    ni=try_fillet(comp, body, conc, r_in)
    body=comp.bRepBodies.item(0)
    # 3) convex edges not at bed, not in fit boxes
    conv=[e for e in body.edges if classify(body,e)=='convex' and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len and not (abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4)]
    no=try_fillet(comp, body, conv, r_out)
    body=comp.bRepBodies.item(0)
    return 'chamfer %d/%d, inner fillet %d/%d, outer fillet %d/%d, vol %.1f->%.1f'%(nc,len(bed),ni,len(conc),no,len(conv),v0,body.volume)

def clear(comp):
    for coll in (comp.features.filletFeatures, comp.features.chamferFeatures):
        for i in range(coll.count-1,-1,-1):
            try: coll.item(i).deleteMe()
            except Exception: pass

def sig(e):
    p=e.pointOnEdge; return (round(p.x*100),round(p.y*100),round(p.z*100))
def iterative(comp, kind, keep_boxes, r, min_len, skip_bed=True, max_iter=400):
    failed=set(); n=0
    for it in range(max_iter):
        body=comp.bRepBodies.item(0)
        cands=[e for e in body.edges if classify(body,e)==kind and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len and sig(e) not in failed
               and not (skip_bed and abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4)]
        if not cands: break
        # try a big batch of vertical edges first, then the rest
        def vert(e):
            bb=e.boundingBox; return abs(bb.maxPoint.x-bb.minPoint.x)<1e-4 and abs(bb.maxPoint.y-bb.minPoint.y)<1e-4
        groups=[[e for e in cands if vert(e)],[e for e in cands if not vert(e)]]
        progressed=False
        for g in groups:
            if len(g)>1:
                col=C.ObjectCollection.create()
                for e in g: col.add(e)
                try:
                    fi=comp.features.filletFeatures.createInput(); fi.addConstantRadiusEdgeSet(col, C.ValueInput.createByReal(r/10), False)
                    comp.features.filletFeatures.add(fi); n+=len(g); progressed=True; break
                except Exception: pass
        if progressed: continue
        e=cands[0]; ok=False
        for rr in (r, r*0.6, r*0.35):
            try:
                col=C.ObjectCollection.create(); col.add(e)
                fi=comp.features.filletFeatures.createInput(); fi.addConstantRadiusEdgeSet(col, C.ValueInput.createByReal(rr/10), False)
                comp.features.filletFeatures.add(fi); n+=1; ok=True; break
            except Exception: pass
        if not ok: failed.add(sig(e))
    return n, len(failed)
def process2(comp, keep_boxes, r_out=1.5, r_in=2.0, ch=0.6, min_len=3.0):
    body=comp.bRepBodies.item(0); v0=body.volume
    bed=[e for e in body.edges if classify(body,e)=='convex' and abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4]
    nc=try_chamfer(comp, bed, ch)
    ni,fi=iterative(comp,'concave',keep_boxes,r_in,min_len)
    no,fo=iterative(comp,'convex',keep_boxes,r_out,min_len)
    return 'bed chamfer %d/%d | inner fillets %d (failed %d) | outer fillets %d (failed %d) | vol %.1f->%.1f'%(nc,len(bed),ni,fi,no,fo,v0,comp.bRepBodies.item(0).volume)

def process3(comp, keep_boxes, r_out=1.5, r_in=2.0, ch=0.6, min_len=3.0, r_top=None):
    r_top = r_top or r_out
    body=comp.bRepBodies.item(0); v0=body.volume
    def vert(e):
        bb=e.boundingBox; return abs(bb.maxPoint.x-bb.minPoint.x)<1e-4 and abs(bb.maxPoint.y-bb.minPoint.y)<1e-4
    # 1 vertical convex edges in one batch (fallback iterative)
    body=comp.bRepBodies.item(0)
    vc=[e for e in body.edges if vert(e) and classify(body,e)=='convex' and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len]
    nv=try_fillet(comp, body, vc, r_out)
    ni,fi=iterative(comp,'concave',keep_boxes,r_in,min_len)
    no,fo=iterative(comp,'convex',keep_boxes,r_top,min_len)
    body=comp.bRepBodies.item(0)
    bed=[e for e in body.edges if abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4 and classify(body,e)=='convex']
    nc=try_chamfer(comp, bed, ch)
    return 'vert %d/%d | inner %d (fail %d) | top/other %d (fail %d) | bed chamfer %d/%d | vol %.1f->%.1f'%(nv,len(vc),ni,fi,no,fo,nc,len(bed),v0,comp.bRepBodies.item(0).volume)

def guarded_add(comp, kind, edges, r):
    """add fillet/chamfer; undo if body count or volume changes badly"""
    b0=comp.bRepBodies.count; v0=comp.bRepBodies.item(0).volume
    col=C.ObjectCollection.create()
    for e in edges: col.add(e)
    try:
        if kind=='fillet':
            fi=comp.features.filletFeatures.createInput(); fi.addConstantRadiusEdgeSet(col, C.ValueInput.createByReal(r/10), True); f=comp.features.filletFeatures.add(fi)
        else:
            ci=comp.features.chamferFeatures.createInput2(); ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, C.ValueInput.createByReal(r/10), True); f=comp.features.chamferFeatures.add(ci)
    except Exception:
        return False
    v1=comp.bRepBodies.item(0).volume
    if comp.bRepBodies.count!=b0 or v1<=0 or abs(v1-v0)/v0>0.015 or f.healthState!=0:
        f.deleteMe(); return False
    return True
def iterative_g(comp, kind, keep_boxes, r, min_len, skip_bed=True, max_iter=300):
    failed=set(); n=0
    for it in range(max_iter):
        body=comp.bRepBodies.item(0)
        cands=[e for e in body.edges if classify(body,e)==kind and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len and sig(e) not in failed
               and not (skip_bed and abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4)]
        if not cands: break
        if len(cands)>1 and guarded_add(comp,'fillet',cands,r): n+=len(cands); continue
        e=cands[0]; ok=False
        for rr in (r, r*0.6, r*0.35):
            if guarded_add(comp,'fillet',[e],rr): n+=1; ok=True; break
        if not ok: failed.add(sig(e))
    return n,len(failed)
def process4(comp, keep_boxes, r_out=1.5, r_in=2.0, ch=0.6, min_len=3.0, r_top=None):
    r_top=r_top or r_out
    body=comp.bRepBodies.item(0); v0=body.volume
    def vert(e):
        bb=e.boundingBox; return abs(bb.maxPoint.x-bb.minPoint.x)<1e-4 and abs(bb.maxPoint.y-bb.minPoint.y)<1e-4
    vc=[e for e in body.edges if vert(e) and classify(body,e)=='convex' and not in_boxes(e,keep_boxes) and edge_len(e)>=min_len]
    nv=len(vc) if (vc and guarded_add(comp,'fillet',vc,r_out)) else 0
    ni,fi=iterative_g(comp,'concave',keep_boxes,r_in,min_len)
    no,fo=iterative_g(comp,'convex',keep_boxes,r_top,min_len)
    body=comp.bRepBodies.item(0)
    bed=[e for e in body.edges if abs(e.boundingBox.minPoint.z)<1e-4 and abs(e.boundingBox.maxPoint.z)<1e-4 and classify(body,e)=='convex']
    nc=0
    if bed and guarded_add(comp,'chamfer',bed,ch): nc=len(bed)
    else:
        for e in bed:
            if e.isValid and guarded_add(comp,'chamfer',[e],ch): nc+=1
    return 'vert %d | inner %d (fail %d) | top %d (fail %d) | bed chamfer %d/%d | vol %.1f->%.1f'%(nv,ni,fi,no,fo,nc,len(bed),v0,comp.bRepBodies.item(0).volume)
