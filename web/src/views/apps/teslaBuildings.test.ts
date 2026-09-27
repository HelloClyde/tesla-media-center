import { describe, expect, it } from 'vitest';
import { createBuildingMeshes } from './teslaBuildings';

describe('App building extrusion', () => {
  const ring = [[116,40],[116.0001,40],[116.0001,40.0001],[116,40.0001]];
  it('preserves metre heights, roof base and geographic orientation, deduplicating tiles', () => {
    const building = { id:'1', parts:[{ring,base:12,height:8}] };
    const {mesh,count} = createBuildingMeshes([building,building],[116,40]);
    expect(count).toBe(1);
    mesh!.geometry.computeBoundingBox();
    const box=mesh!.geometry.boundingBox!;
    expect(box.min.y).toBeCloseTo(12); expect(box.max.y).toBeCloseTo(20);
    expect(box.max.x).toBeGreaterThan(8); expect(box.min.z).toBeLessThan(-11);
    expect(mesh!.castShadow).toBe(true);
    mesh!.geometry.dispose(); mesh!.material.dispose();
  });
  it('rejects invalid heights and buildings outside the visible neighbourhood', () => {
    expect(createBuildingMeshes([{id:'x',parts:[{ring,base:0,height:NaN}]}],[116,40]).count).toBe(0);
    expect(createBuildingMeshes([{id:'x',parts:[{ring,base:0,height:20}]}],[117,41]).count).toBe(0);
  });
});
