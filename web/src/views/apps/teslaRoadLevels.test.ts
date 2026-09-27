import {describe,it,expect} from 'vitest';
import {roadSpans,roadDeckGeometry} from './teslaRoadLevels';

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
});
