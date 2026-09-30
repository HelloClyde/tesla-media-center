import { expect, it } from 'vitest';
import * as T from 'three';
import { repairSurfaceGeometry, repairHoodEdgeNormals, repairRearQuarterNormals, repairRoofGlassNormals } from './teslaSurfaceRepair';

it('corrects reversed faces and removes zero-area faces without changing shape or UVs', () => {
  const g = new T.BufferGeometry();
  g.setAttribute('position',new T.Float32BufferAttribute([0,0,0, 1,0,0, 0,1,0],3));
  g.setAttribute('normal',new T.Float32BufferAttribute([0,0,1, 0,0,1, 0,0,1],3));
  g.setAttribute('uv',new T.Float32BufferAttribute([0,0,1,0,0,1],2));
  g.setIndex([0,2,1, 0,0,1]);
  const repaired = repairSurfaceGeometry(g);
  expect(Array.from(repaired.index!.array)).toEqual([0,1,2]);
  expect(Array.from(g.index!.array)).toEqual([0,2,1,0,0,1]);
  for(const key of ['position','normal','uv']) expect(Array.from(repaired.getAttribute(key).array)).toEqual(Array.from(g.getAttribute(key).array));
  expect(repaired.userData.surfaceRepair).toEqual({reversed:1,degenerate:1});
});

it('preserves intentional perpendicular crease normals and is idempotent', () => {
  const g = new T.BufferGeometry();
  g.setAttribute('position',new T.Float32BufferAttribute([0,0,0, 1,0,0, 0,1,0],3));
  g.setAttribute('normal',new T.Float32BufferAttribute([1,0,0, 1,0,0, 1,0,0],3));
  const first = repairSurfaceGeometry(g), second = repairSurfaceGeometry(first);
  expect(Array.from(first.index!.array)).toEqual([0,1,2]);
  expect(second.userData.surfaceRepair).toEqual({reversed:0,degenerate:0});
});

it('removes nearly collinear bumper slivers while preserving nearby valid faces', () => {
  const g = new T.BufferGeometry();
  g.setAttribute('position', new T.Float32BufferAttribute([
    0, 0, 0, 1, 0, 0, .5, .000001, 0, 0, 1, 0,
  ], 3));
  g.setAttribute('normal', new T.Float32BufferAttribute(Array(4).fill([0, 0, 1]).flat(), 3));
  g.setIndex([0, 1, 2, 0, 1, 3]);
  const fixed = repairSurfaceGeometry(g);
  expect(Array.from(fixed.index!.array)).toEqual([0, 1, 3]);
  expect(fixed.userData.surfaceRepair).toEqual({ reversed: 0, degenerate: 1 });
});

it('repairs a hood-top normal without changing the shared vertical lip or geometry', () => {
  const g=new T.BufferGeometry();
  g.setAttribute('position',new T.Float32BufferAttribute([0,1,1, .1,1,1, 0,1,.9, 0,.9,.9],3));
  g.setAttribute('normal',new T.Float32BufferAttribute([0,1,0, 0,1,0, -1,0,0, -1,0,0],3));
  g.setAttribute('uv',new T.Float32BufferAttribute([0,0, 1,0, 0,1, 1,1],2));
  g.setIndex([0,1,2, 0,2,3]);
  const fixed=repairHoodEdgeNormals(g,new T.Matrix4());
  expect(fixed.userData.hoodCornersCorrected).toBe(1);
  expect(Array.from(fixed.index!.array)).toEqual([0,1,4,0,2,3]);
  const position=fixed.getAttribute('position'),normal=fixed.getAttribute('normal');
  expect([normal.getX(4),normal.getY(4),normal.getZ(4)]).toEqual([0,1,0]);
  expect([normal.getX(2),normal.getY(2),normal.getZ(2)]).toEqual([-1,0,0]);
  expect([position.getX(4),position.getY(4),position.getZ(4)]).toEqual([position.getX(2),position.getY(2),position.getZ(2)]);
  expect(repairHoodEdgeNormals(g,new T.Matrix4().makeTranslation(2,0,0)).index!.count).toBe(6);
  expect(g.getAttribute('position').count).toBe(4);
});

it.each([-1, 1])('repairs rear shoulder corners on side %s without moving the seam', side => {
  const g=new T.BufferGeometry();
  g.setAttribute('position',new T.Float32BufferAttribute([side*.7,1,-1, side*.794,.965,-1, side*.7,1,-1.1],3));
  const n=new T.Vector3(side*.35,.94,0).normalize();
  g.setAttribute('normal',new T.Float32BufferAttribute([...n.toArray(),...n.toArray(),0,-1,0],3));
  g.setIndex(side===1?[0,1,2]:[0,2,1]);
  const result=repairRearQuarterNormals(g,new T.Matrix4());
  expect(result.userData.rearQuarterCornersCorrected).toBe(1);
  const positions=result.getAttribute('position'),normal=result.getAttribute('normal');
  expect(normal.getY(3)).toBeGreaterThan(.9);
  expect(normal.getX(3)*side).toBeGreaterThan(.3);
  for(let c=0;c<3;c++)expect(positions.getComponent(3,c)).toBe(positions.getComponent(2,c));
  const untouched=repairRearQuarterNormals(g,new T.Matrix4().makeTranslation(0,0,3));
  expect(untouched.getAttribute('position').count).toBe(3);
});

it('repairs an inverted normal on the lower rear bumper', () => {
  const g = new T.BufferGeometry();
  g.setAttribute('position', new T.Float32BufferAttribute([
    -.84, .52, -1.97, -.87, .53, -1.94, -.85, .54, -2.02,
  ], 3));
  const p = g.getAttribute('position');
  const face = new T.Vector3(p.getX(1) - p.getX(0), p.getY(1) - p.getY(0), p.getZ(1) - p.getZ(0))
    .cross(new T.Vector3(p.getX(2) - p.getX(0), p.getY(2) - p.getY(0), p.getZ(2) - p.getZ(0))).normalize();
  g.setAttribute('normal', new T.Float32BufferAttribute([...face.toArray(), ...face.toArray(), ...face.clone().negate().toArray()], 3));
  g.setIndex([0, 1, 2]);
  const fixed = repairRearQuarterNormals(g, new T.Matrix4());
  expect(fixed.userData.rearQuarterCornersCorrected).toBe(1);
  expect(fixed.getAttribute('normal').count).toBe(4);
});

it('repairs a roof-glass normal outlier while keeping the original edge vertex', () => {
  const g = new T.BufferGeometry();
  g.setAttribute('position', new T.Float32BufferAttribute([
    0, 1.55, -1.2, .1, 1.55, -1.2, 0, 1.55, -1.3,
  ], 3));
  g.setAttribute('normal', new T.Float32BufferAttribute([
    0, 1, 0, 0, 1, 0, 0, .6, -.8,
  ], 3));
  g.setIndex([0, 1, 2]);
  const fixed = repairRoofGlassNormals(g, new T.Matrix4());
  expect(fixed.userData.roofGlassCornersCorrected).toBe(1);
  expect(fixed.getAttribute('position').count).toBe(4);
  expect(fixed.getAttribute('normal').getY(3)).toBeCloseTo(1);
  expect(g.getAttribute('normal').getY(2)).toBeCloseTo(.6);
});
