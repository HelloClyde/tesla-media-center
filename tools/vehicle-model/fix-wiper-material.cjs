const { NodeIO } = require("../../web/node_modules/@gltf-transform/core");
const {
  ALL_EXTENSIONS,
} = require("../../web/node_modules/@gltf-transform/extensions");
const {
  dequantize,
  meshopt,
} = require("../../web/node_modules/@gltf-transform/functions");
const {
  MeshoptDecoder,
  MeshoptEncoder,
} = require("../../web/node_modules/meshoptimizer");
const T = require("../../web/node_modules/three");
(async () => {
  await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
  const io = new NodeIO()
    .registerExtensions(ALL_EXTENSIONS)
    .registerDependencies({
      "meshopt.decoder": MeshoptDecoder,
      "meshopt.encoder": MeshoptEncoder,
    });
  const path = process.argv[2] || "web/public/models/2022_tesla_model_y.glb";
  const doc = await io.read(path);
  if (
    doc
      .getRoot()
      .listMaterials()
      .some((m) => m.getName() === "Wiper_Matte_Black")
  )
    throw new Error("Wipers already repaired");
  let count = 0;
  const black = doc
    .createMaterial("Wiper_Matte_Black")
    .setBaseColorFactor([0.006, 0.007, 0.008, 1])
    .setMetallicFactor(0.05)
    .setRoughnessFactor(0.8);
  await doc.transform(dequantize());
  for (const node of doc.getRoot().listNodes()) {
    if (node.getName() !== "Body_Static") continue;
    for (const prim of node.getMesh().listPrimitives()) {
      if (!prim.getMaterial().getName().startsWith("Palette")) continue;
      const p = prim.getAttribute("POSITION"),
        idx = prim.getIndices().getArray(),
        matrix = new T.Matrix4().fromArray(node.getWorldMatrix());
      const parent = Array.from({ length: p.getCount() }, (_, i) => i),
        find = (i) => (parent[i] === i ? i : (parent[i] = find(parent[i])));
      const keys = new Map(),
        points = [];
      for (let i = 0; i < p.getCount(); i++) {
        const v = new T.Vector3()
          .fromArray(p.getElement(i, []))
          .applyMatrix4(matrix);
        points.push(v);
        const k = v
          .toArray()
          .map((x) => Math.round(x * 10000))
          .join(",");
        if (keys.has(k)) parent[find(i)] = find(keys.get(k));
        else keys.set(k, i);
      }
      for (let i = 0; i < idx.length; i += 3) {
        parent[find(idx[i + 1])] = find(idx[i]);
        parent[find(idx[i + 2])] = find(idx[i]);
      }
      const groups = new Map();
      for (let i = 0; i < idx.length; i += 3) {
        const root = find(idx[i]);
        if (!groups.has(root)) groups.set(root, { box: new T.Box3(), tri: [] });
        const g = groups.get(root);
        g.tri.push(i);
        for (let j = 0; j < 3; j++) g.box.expandByPoint(points[idx[i + j]]);
      }
      const selected = new Set();
      for (const [id, g] of groups) {
        const { min, max } = g.box;
        if (
          min.y > 1.02 &&
          max.y < 1.14 &&
          min.z > 1.09 &&
          max.z < 1.4 &&
          max.x - min.x < 0.65
        ) {
          g.tri.forEach((i) => selected.add(i));
          count++;
        }
      }
      if (selected.size) {
        const keep = [],
          wipers = [];
        for (let i = 0; i < idx.length; i += 3)
          (selected.has(i) ? wipers : keep).push(
            idx[i],
            idx[i + 1],
            idx[i + 2]
          );
        const buffer = prim.getIndices().getBuffer();
        const split = prim
          .clone()
          .setMaterial(black)
          .setIndices(
            doc
              .createAccessor()
              .setType("SCALAR")
              .setArray(new Uint32Array(wipers))
              .setBuffer(buffer)
          );
        node.getMesh().addPrimitive(split);
        prim.setIndices(
          doc
            .createAccessor()
            .setType("SCALAR")
            .setArray(new Uint32Array(keep))
            .setBuffer(buffer)
        );
        console.log(
          "Assigned",
          wipers.length / 3,
          "triangles to black wiper material"
        );
      }
    }
  }
  if (count !== 8)
    throw new Error("Expected eight wiper components, found " + count);
  await doc.transform(meshopt({ encoder: MeshoptEncoder, level: "medium" }));
  await io.write(path, doc);
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
