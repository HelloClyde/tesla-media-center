import { NodeIO } from '../../web/node_modules/@gltf-transform/core/dist/index.modern.js';
import { ALL_EXTENSIONS } from '../../web/node_modules/@gltf-transform/extensions/dist/index.modern.js';
import { MeshoptDecoder, MeshoptEncoder } from '../../web/node_modules/meshoptimizer/index.js';
import { Matrix4, Vector3 } from '../../web/node_modules/three/build/three.core.js';

// The source model contains two long, dark rocker panels below the doors.
// In the viewer's low side angle they appear as detached, rectangular bars.
const modelPath = 'web/public/models/2022_tesla_model_y.glb';
await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder,
  'meshopt.encoder': MeshoptEncoder,
});
const document = await io.read(modelPath);
const body = document.getRoot().listNodes().find(node => node.getName() === 'Body_Static');
if (!body) throw new Error('Body_Static was not found');
const primitive = body.getMesh()?.listPrimitives().find(item => item.getMaterial()?.getName() === 'PaletteMaterial001');
if (!primitive) throw new Error('Body palette primitive was not found');
const positions = primitive.getAttribute('POSITION');
const indices = primitive.getIndices();
if (!positions || !indices) throw new Error('Body geometry is missing positions or indices');
const original = indices.getArray();
const parent = Array.from({ length: positions.getCount() }, (_, i) => i);
function find(i) {
  while (parent[i] !== i) {
    parent[i] = parent[parent[i]];
    i = parent[i];
  }
  return i;
}
for (let i = 0; i < original.length; i += 3) {
  const root = find(original[i]);
  parent[find(original[i + 1])] = root;
  parent[find(original[i + 2])] = root;
}
const components = new Map();
const world = new Matrix4().fromArray(body.getWorldMatrix());
const point = new Vector3();
for (let i = 0; i < positions.getCount(); i++) {
  const root = find(i);
  let bounds = components.get(root);
  if (!bounds) {
    bounds = { count: 0, min: new Vector3(Infinity, Infinity, Infinity), max: new Vector3(-Infinity, -Infinity, -Infinity) };
    components.set(root, bounds);
  }
  point.fromArray(positions.getElement(i, [])).applyMatrix4(world);
  bounds.min.min(point);
  bounds.max.max(point);
  bounds.count++;
}
const rails = [...components].filter(([, b]) =>
  b.count > 300 && b.count < 600 &&
  b.min.y > .19 && b.min.y < .22 &&
  b.max.y > .32 && b.max.y < .35 &&
  b.min.z > -1.1 && b.min.z < -0.9 &&
  b.max.z > 0.9 && b.max.z < 1.1 &&
  (b.min.x > .7 || b.max.x < -.7));
if (rails.length !== 2 || Math.sign(rails[0][1].min.x) === Math.sign(rails[1][1].min.x)) {
  throw new Error(`Expected one oversized rocker on each side, found ${rails.length}`);
}
const railRoots = new Set(rails.map(([root]) => root));
const kept = [];
for (let i = 0; i < original.length; i += 3) {
  if (!railRoots.has(find(original[i]))) kept.push(original[i], original[i + 1], original[i + 2]);
}
indices.setArray(new original.constructor(kept));
const removedTriangles = (original.length - kept.length) / 3;
if (removedTriangles < 100) throw new Error(`Unexpectedly few rocker triangles: ${removedTriangles}`);
await io.write(modelPath, document);
console.log(`Removed two oversized rocker panels (${removedTriangles} triangles).`);
