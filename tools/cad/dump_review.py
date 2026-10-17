import adsk.core as C, adsk.fusion as F, json, os
root=design.rootComponent
parts=[]; seen=set()
def rad_list(comp):
    fr=[]; ch=[]
    for f in comp.features.filletFeatures:
        if f.isSuppressed: continue
        try:
            for es in f.edgeSets:
                try: fr.append(round(es.radius.value*10,2))
                except Exception:
                    try: fr.append(round(es.startRadius.value*10,2))
                    except Exception: pass
        except Exception: pass
    for f in comp.features.chamferFeatures:
        if f.isSuppressed: continue
        try:
            for es in f.edgeSets:
                try: ch.append(round(es.distance.value*10,2))
                except Exception:
                    try: ch.append(round(es.distanceOne.value*10,2))
                    except Exception: pass
        except Exception: pass
    return fr,ch
for o in root.allOccurrences:
    c=o.component
    if c.name in seen: continue
    seen.add(c.name)
    if not c.bRepBodies.count or 'HW-LIB' in o.fullPathName: continue
    p=o.fullPathName
    if 'REF-SO101-STOCK' in p and not c.name.startswith(('Wrist','Moving')): continue
    bodies=[b for b in c.bRepBodies]
    mats=sorted(set(b.material.name for b in bodies))
    try: vol=sum(b.volume for b in bodies)*1000
    except Exception: vol=-1
    bb=o.boundingBox
    fr,ch=rad_list(c)
    qty=sum(1 for x in root.allOccurrences if x.component==c)
    parts.append({'name':c.name,'path':p.split('+')[0],'qty':qty,'materials':mats,'vol_mm3':round(vol),'bbox_mm':[round((bb.maxPoint.asArray()[i]-bb.minPoint.asArray()[i])*10,1) for i in range(3)],
                  'world_min':[round(v*10,1) for v in bb.minPoint.asArray()],'fillet_r':sorted(set(fr)),'n_fillet_sets':len(fr),'chamfer':sorted(set(ch)),'visible':o.isVisible})
joints=[{'name':j.name,'type':str(j.jointMotion.jointType)} for j in root.asBuiltJoints]+[{'name':j.name,'type':str(j.jointMotion.jointType)} for j in root.joints]
params=[{'name':p.name,'expr':p.expression,'comment':p.comment} for p in design.userParameters]
json.dump({'parts':parts,'joints':joints,'params':params},open(os.path.join(os.path.expanduser('~'),'fusion_bridge','review_dump.json'),'w'),indent=1)
print(len(parts),'components', len(joints),'joints', len(params),'params')
