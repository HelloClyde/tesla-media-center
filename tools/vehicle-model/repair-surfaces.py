"""Offline, bounded local quadratic normal fitting. Requires numpy; no runtime dependency.

Positions, indices, UVs, materials and articulated pivots are preserved. Neighborhoods
are restricted by normal orientation so opposite faces/creases are not averaged.
"""
import json
import numpy as np
from itertools import product
from pathlib import Path
def fit_surface(item):
    points=np.array(item['points']); normals=np.array(item['normals'])
    if item['material']=='Pearl_White_Clearcoat':
        tri=np.array(item['indices']).reshape(-1,3)
        cross=np.cross(points[tri[:,1]]-points[tri[:,0]],points[tri[:,2]]-points[tri[:,0]])
        sums=np.zeros_like(normals)
        for corner in range(3):
            ids=tri[:,corner]
            valid=np.sum(normals[ids]*cross,axis=1)>.5*np.linalg.norm(cross,axis=1)
            np.add.at(sums,ids[valid],cross[valid])
        lengths=np.linalg.norm(sums,axis=1);valid=lengths>1e-15
        normals[valid]=sums[valid]/lengths[valid,None]
    out=normals.copy()
    radius=.12 if item['material']=='Pearl_White_Clearcoat' else .025
    grid={}
    cells=np.floor(points/radius).astype(int)
    for i,cell in enumerate(cells):grid.setdefault(tuple(cell),[]).append(i)
    offsets=list(product((-1,0,1),repeat=3))
    for i,cell in enumerate(cells):
        if item['material']=='Pearl_White_Clearcoat':
            _,height,longitudinal=points[i]
            if height<.45 or (longitudinal>1.45 and height<1.0) or (longitudinal< -1.45 and height<1.08):continue
        ids=np.array([j for off in offsets for j in grid.get(tuple(cell+off),[])],dtype=int)
        ds=np.linalg.norm(points[ids]-points[i],axis=1)
        valid=ds<radius;ids=ids[valid];ds=ds[valid]
        order=np.argsort(ds)[:80];ids=ids[order];ds=ds[order]
        valid=(normals[ids]@normals[i])>.8;ids=ids[valid];ds=ds[valid]
        if len(ids)<8: continue
        n=normals[i];axis=np.array([1.,0,0]) if abs(n[0])<.8 else np.array([0.,1,0])
        u=np.cross(n,axis);u/=np.linalg.norm(u);v=np.cross(n,u)
        delta=(points[ids]-points[i])/radius
        x=delta@u;y=delta@v;z=delta@n
        a=np.column_stack([np.ones(len(x)),x,y,x*x,x*y,y*y])
        weight=np.exp(-3*(ds/radius)**2)
        try:
            coef,_,rank,_=np.linalg.lstsq(a*weight[:,None],z*weight,rcond=1e-5)
            if rank<6: continue
            candidate=n-u*coef[1]-v*coef[2];candidate/=np.linalg.norm(candidate)
            if candidate@n>.92: out[i]=candidate
        except np.linalg.LinAlgError: pass
    item['normals']=out.tolist()
    print(item['name'],len(points),'fitted',int(np.sum(np.linalg.norm(out-normals,axis=1)>.001)))
    return item

if __name__ == '__main__':
    items=json.loads(Path('.local-data/model-y/surface-input.json').read_text())
    result=[fit_surface(item) for item in items]
    Path('.local-data/model-y/surface-output.json').write_text(json.dumps(result))
