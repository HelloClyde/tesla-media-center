import {BufferAttribute, BufferGeometry, Box3, Sphere, Vector3} from 'three';

/** The map meshes have matching, non-interleaved attributes. Copy their large
 * buffers in slices rather than merging every building in one UI task. */
export function* mergeMapGeometries(geometries: BufferGeometry[]): Generator<void, BufferGeometry | undefined> {
  if (!geometries.length) return undefined;
  const result = new BufferGeometry();
  let complete = false;
  try {
    const names = Object.keys(geometries[0].attributes);
    const indexed = geometries[0].index !== null;
    let vertexCount = 0;
    for (const geometry of geometries) {
      if ((geometry.index !== null) !== indexed || Object.keys(geometry.attributes).length !== names.length
          || names.some(name => !(geometry.getAttribute(name) instanceof BufferAttribute)))
        throw new Error('incompatible map geometry');
      vertexCount += geometry.getAttribute('position').count;
      yield;
    }
    for (const name of names) {
      const first = geometries[0].getAttribute(name) as BufferAttribute;
      const ArrayType = first.array.constructor as typeof Float32Array;
      const array = new ArrayType(vertexCount * first.itemSize);
      let offset = 0;
      for (const geometry of geometries) {
        const source = geometry.getAttribute(name) as BufferAttribute;
        if (source.itemSize !== first.itemSize || source.normalized !== first.normalized
            || source.array.constructor !== first.array.constructor)
          throw new Error('incompatible map attribute');
        for (let start = 0; start < source.array.length; start += 16384) {
          const end = Math.min(start + 16384, source.array.length);
          array.set(source.array.subarray(start, end), offset + start);
          yield;
        }
        offset += source.array.length;
      }
      result.setAttribute(name, new BufferAttribute(array, first.itemSize, first.normalized));
    }
    if (indexed) {
      const size = geometries.reduce((sum, geometry) => sum + geometry.index!.count, 0);
      const indices = vertexCount > 65535 ? new Uint32Array(size) : new Uint16Array(size);
      let at = 0, offset = 0;
      for (const geometry of geometries) {
        const source = geometry.index!;
        for (let i = 0; i < source.count; i++) {
          indices[at++] = source.getX(i) + offset;
          if ((i & 8191) === 8191) yield;
        }
        offset += geometry.getAttribute('position').count;
        yield;
      }
      result.setIndex(new BufferAttribute(indices, 1));
    }
    // Three otherwise scans the full position buffer on its first render.
    const position = result.getAttribute('position');
    const box = new Box3(), point = new Vector3();
    for (let i = 0; i < position.count; i++) {
      point.fromBufferAttribute(position, i); box.expandByPoint(point);
      if ((i & 2047) === 2047) yield;
    }
    result.boundingBox = box;
    result.boundingSphere = new Sphere(box.getCenter(new Vector3()), box.getSize(new Vector3()).length() / 2);
    complete = true;
    return result;
  } finally {
    if (!complete) result.dispose();
  }
}
