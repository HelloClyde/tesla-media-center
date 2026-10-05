import { describe, it, expect } from 'vitest';
import { createLaneMesh, inferredLaneMarkings, laneViewportTiles, navigationLaneBoundaries } from './teslaLanes';
import { nearestRoadHeight } from './teslaRoadLevels';

describe('real lane boundary ground layer', () => {
  it('requests every tile intersecting the view when the car crosses a tile corner', () => {
    const n = 2 ** 15;
    const corner: [number, number] = [-180 + 26979 * 360 / n, 90 - 9119 * 180 / n];
    const tiles = laneViewportTiles(corner);
    for (const x of [26978, 26979]) for (const y of [9118, 9119]) {
      expect(tiles).toContainEqual([x, y]);
    }
    expect(tiles.length).toBe(4);
  });
  it('clips crossing lines, deduplicates reversed boundaries and ignores source height', () => {
    const mesh = createLaneMesh([[[115.99,40,99999],[116.01,40,-99999]],[[116.01,40,0],[115.99,40,0]]], [116,40]);
    expect(mesh?.userData.segmentCount).toBe(1);
    const position = mesh!.geometry.getAttribute('position');
    for(let i=0;i<position.count;i++) {
      expect(Math.abs(position.getX(i))).toBeLessThanOrEqual(300.1);
      expect(position.getY(i)).toBeCloseTo(.04);
    }
    mesh!.geometry.dispose(); mesh!.material.dispose();
  });
  it('does not render empty, distant, invalid or degenerate segments', () => {
    expect(createLaneMesh([[],[[117,40],[118,40]],[[116,40],[116,40]],[[NaN,40],[116,40]]],[116,40])).toBeUndefined();
  });
  it('places an LNDS boundary above a matched road deck without interpreting source Z', () => {
    const mesh=createLaneMesh([[[116,40,99999],[116.0001,40,-99999]]],[116,40],600,
      () => 4.06);
    const position=mesh!.geometry.getAttribute('position');
    for(let i=0;i<position.count;i++) expect(position.getY(i)).toBeCloseTo(4.10);
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('samples a long boundary inside the segment when it crosses a bridge deck', () => {
    const halfLongitude = 50 / (111319.49079327358 * Math.cos(40 * Math.PI / 180));
    const sampled: number[] = [];
    const mesh = createLaneMesh([[[116 - halfLongitude, 40], [116 + halfLongitude, 40]]],
      [116, 40], 600, x => { sampled.push(x); return Math.abs(x) < 25 ? 4 : 0; });
    const position = mesh!.geometry.getAttribute('position');
    const heights = Array.from({ length: position.count }, (_, index) => position.getY(index));
    expect(sampled.some(x => Math.abs(x) < 10)).toBe(true);
    expect(Math.min(...heights)).toBeCloseTo(.04);
    expect(Math.max(...heights)).toBeCloseTo(4.04);
    expect(mesh!.userData.segmentCount).toBe(1);
    mesh!.geometry.dispose(); mesh!.material.dispose();
  });
  it('keeps a previously resolved bridge level across an overlapping ground road',()=>{
    const lon30=30/(111319.49079327358*Math.cos(40*Math.PI/180));
    const elevated={a:[0,0] as [number,number],b:[25,0] as [number,number],from:4,to:4,width:4,level:1};
    const ground={a:[10,0] as [number,number],b:[30,0] as [number,number],from:.06,to:.06,width:4,level:0};
    const mesh=createLaneMesh([[[116,40],[116+lon30,40]]],[116,40],600,
      (x,z,direction,previous)=>nearestRoadHeight([ground,elevated],x,z,direction,previous));
    const position=mesh!.geometry.getAttribute('position');
    const heightsAt=(low:number,high:number)=>Array.from({length:position.count},(_,i)=>i)
      .filter(i=>position.getX(i)>low && position.getX(i)<high).map(i=>position.getY(i));
    expect(heightsAt(12,18).every(y=>y>4)).toBe(true);
    expect(heightsAt(27,31).some(y=>y<.2)).toBe(true);
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('does not carry bridge height onto an unrelated boundary starting in overlap',()=>{
    const lon30=30/(111319.49079327358*Math.cos(40*Math.PI/180));
    const elevated={a:[0,0] as [number,number],b:[30,0] as [number,number],from:4,to:4,width:4,level:1};
    const ground={...elevated,a:[10,0] as [number,number],from:.06,to:.06,level:0};
    const mesh=createLaneMesh([[[116,40],[116+lon30,40]],
      [[116+lon30/2,40],[116+lon30,40]]],[116,40],600,
      (x,z,direction,previous)=>nearestRoadHeight([ground,elevated],x,z,direction,previous));
    const position=mesh!.geometry.getAttribute('position');
    expect(position.getY(0)).toBeCloseTo(4.04);
    expect(position.getY(position.count-1)).toBeCloseTo(.10);
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('keeps only nearby boundaries aligned with the active route', () => {
    const route = { id: 1, path: [[116,40],[116.01,40]] as [number,number][],
      steps: [{ start: 0, end: 1, road: '测试路' }], breaks: [], distance: 853, labels: [] };
    const lines = [
      [[115.999,40],[116.004,40]],
      [[116.001,39.999],[116.001,40.001]],
      [[116.001,40.001],[116.003,40.001]],
      [[116.008,40],[116.009,40]],
    ];
    const selectedKinds:number[]=[];
    const selected = navigationLaneBoundaries(lines,route,0,[116,40],[3,1,1,1],selectedKinds);
    expect(selected.length).toBeGreaterThan(0);
    expect(selectedKinds).toHaveLength(selected.length);
    expect(selectedKinds.every(kind=>kind===3)).toBe(true);
    expect(selected[0].length).toBeGreaterThan(2);
    expect(selected.some(line => line[0][1] !== 40 || line[1][1] !== 40)).toBe(false);
    expect(selected.some(line => line[0][0] >= 116.008)).toBe(false);
  });
  it('infers interior dividers only when parallel boundaries exist on both sides', () => {
    const lat=40, delta=3/111319.49079327358;
    const lines=Array.from({length:4},(_,index)=>[[116,lat+index*delta],[116.0004,lat+index*delta]]);
    expect(inferredLaneMarkings(lines,[116,lat])).toEqual(['solid','dashed','dashed','solid']);
    expect(inferredLaneMarkings(lines,[116,lat],undefined,[1,3,3,1]))
      .toEqual(['solid','dashed','dashed','solid']);
    expect(inferredLaneMarkings(lines,[116,lat],undefined,[1,1,1,1]))
      .toEqual(['solid','solid','solid','solid']);
    expect(inferredLaneMarkings([lines[1]], [116,lat])).toEqual(['solid']);
    expect(inferredLaneMarkings(lines,[116,lat],(_x,z)=>Math.abs(z)>4.5?4:0))
      .toEqual(['solid','solid','solid','solid']);
  });
});
