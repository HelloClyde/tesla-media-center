import {describe,it,expect} from 'vitest';
import {roadSpans,roadDeckGeometry,nearestRoadHeight} from './teslaRoadLevels';

describe('App road levels',()=>{
  const points=[[116,40],[116.001,40],[116.002,40],[116.003,40]];
  it('ends an elevated span at -1 without turning it into a tunnel',()=>{
    const spans=roadSpans(points,[[0,1],[1,-1],[3,0]]);
    expect(spans.map(s=>s.level)).toEqual([1,0]);
    expect(spans[0].points).toEqual(points.slice(0,2));
    expect(spans[0].rampStart).toBe(false);
    expect(spans[0].rampEnd).toBe(true);
  });
  it('retains level at a tile boundary and avoids inventing missing markers',()=>{
    const span=roadSpans(points,[[0,1],[3,0]])[0];
    expect(span.rampEnd).toBe(false);
    expect(roadSpans(points)[0].level).toBe(0);
    expect(roadSpans(points,[[4,1]])[0].level).toBe(0);
    expect(roadSpans(points,[[1,1],[0,-1]])[0].level).toBe(0);
  });
  it('creates a finite upward deck, smooth ending ramp and source corner positions',()=>{
    const span=roadSpans(points,[[0,1],[2,-1]])[0];
    const g=roadDeckGeometry(span,[116,40],5)!;
    const positions=g.getAttribute('position');
    expect(Array.from(positions.array).every(Number.isFinite)).toBe(true);
    expect(positions.getY(0)).toBeCloseTo(4.06);
    expect(positions.getY(positions.count-1)).toBeCloseTo(.06);
    expect(g.getAttribute('normal').getY(0)).toBeGreaterThan(0);
    g.dispose();
  });
  it('rejects degenerate and nonfinite geometry',()=>{
    expect(roadDeckGeometry({points:[[0,0],[0,0]],level:1,rampStart:false,rampEnd:false},[0,0],4)).toBeUndefined();
    expect(roadDeckGeometry({points:[[NaN,0],[0,0]],level:1,rampStart:false,rampEnd:false},[0,0],4)).toBeUndefined();
  });
  it('keeps a ground lane beside a parallel flyover on the ground deck',()=>{
    const elevated={a:[0,2] as [number,number],b:[30,2] as [number,number],from:4,to:4,width:4,level:1};
    const surface={a:[0,0] as [number,number],b:[30,0] as [number,number],from:.06,to:.06,width:4,level:0};
    expect(nearestRoadHeight([elevated,surface],15,0,[1,0])).toBeCloseTo(.06);
    expect(nearestRoadHeight([surface,elevated],15,2,[1,0])).toBeCloseTo(4);
    expect(nearestRoadHeight([elevated,surface],15,0,[0,1])).toBe(0);
    expect(nearestRoadHeight([{...elevated,a:surface.a,b:surface.b},surface],15,0,[1,0])).toBeCloseTo(.06);
  });
  it('carries a confirmed bridge level through exact XY overlap without overriding a closer road',()=>{
    const elevated={a:[0,0] as [number,number],b:[30,0] as [number,number],from:4,to:4,width:4,level:1};
    const ground={...elevated,from:.06,to:.06,level:0};
    expect(nearestRoadHeight([elevated,ground],15,0,[1,0])).toBeCloseTo(.06);
    expect(nearestRoadHeight([ground,elevated],15,0,[1,0],4)).toBeCloseTo(4);
    expect(nearestRoadHeight([ground,elevated],15,0,[1,0],.06)).toBeCloseTo(.06);
    expect(nearestRoadHeight([{...ground,a:[0,0],b:[30,0]},
      {...elevated,a:[0,3],b:[30,3]}],15,0,[1,0],4)).toBeCloseTo(.06);
  });
});
