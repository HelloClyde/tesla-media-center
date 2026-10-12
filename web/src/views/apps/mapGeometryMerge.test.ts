import {afterEach, expect, it, vi} from 'vitest';
import {BoxGeometry, BufferGeometry, PlaneGeometry, Vector3} from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import {mergeMapGeometries} from './mapGeometryMerge';

afterEach(() => vi.restoreAllMocks());
function finish(work: ReturnType<typeof mergeMapGeometries>) {
  let step = work.next(), yields = 0;
  while (!step.done) { yields++; step = work.next(); }
  return {geometry: step.value!, yields};
}

it.each([true, false])('preserves all attributes, faces and bounds for indexed=%s mesh batches', indexed => {
  const geometries = [0, 1, 2].map(index => {
    const box = new BoxGeometry(2, 4, 6).translate(index * 5, 0, 0);
    if (indexed) return box;
    const flat = box.toNonIndexed(); box.dispose(); return flat;
  });
  const expected = mergeGeometries(geometries, false)!;
  const {geometry, yields} = finish(mergeMapGeometries(geometries));
  expect(yields).toBeGreaterThan(geometries.length);
  for (const name of Object.keys(expected.attributes))
    expect(geometry.getAttribute(name).array).toEqual(expected.getAttribute(name).array);
  expect(geometry.index?.array).toEqual(expected.index?.array);
  const positions = geometry.getAttribute('position'), point = new Vector3();
  for (let i = 0; i < positions.count; i++) {
    point.fromBufferAttribute(positions, i);
    expect(geometry.boundingBox!.containsPoint(point)).toBe(true);
    expect(geometry.boundingSphere!.containsPoint(point)).toBe(true);
  }
  geometries.forEach(item => item.dispose()); expected.dispose(); geometry.dispose();
});

it('uses 32-bit indices across the 65,535-vertex boundary and yields while copying', () => {
  const geometries = Array.from({length: 7}, () => new PlaneGeometry(1, 1, 100, 100));
  const {geometry, yields} = finish(mergeMapGeometries(geometries));
  expect(geometry.index!.array).toBeInstanceOf(Uint32Array);
  const offset = geometries[0].index!.count;
  expect(geometry.index!.getX(offset)).toBe(geometries[0].getAttribute('position').count + geometries[1].index!.getX(0));
  expect(yields).toBeGreaterThan(50);
  geometries.forEach(item => item.dispose()); geometry.dispose();
});

it('releases a partially allocated result when switching viewports', () => {
  const source = new BoxGeometry(), dispose = vi.spyOn(BufferGeometry.prototype, 'dispose');
  const work = mergeMapGeometries([source]);
  work.next(); work.return(undefined);
  expect(dispose).toHaveBeenCalledTimes(1);
  expect(dispose.mock.instances[0]).not.toBe(source);
  source.dispose();
});
