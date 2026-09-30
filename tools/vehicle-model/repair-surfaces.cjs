const fs = require("fs"),
  cp = require("child_process");
const { NodeIO } = require("../../web/node_modules/@gltf-transform/core");
const {
  ALL_EXTENSIONS,
} = require("../../web/node_modules/@gltf-transform/extensions");
const {
  dequantize,
  meshopt,
} = require("../../web/node_modules/@gltf-transform/functions");
const {
  MeshoptEncoder,
  MeshoptDecoder,
} = require("../../web/node_modules/meshoptimizer");
const T = require("../../web/node_modules/three");
(async () => {
  await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready]);
  const io = new NodeIO()
    .registerExtensions(ALL_EXTENSIONS)
    .registerDependencies({
      "meshopt.encoder": MeshoptEncoder,
      "meshopt.decoder": MeshoptDecoder,
    });
  const doc = await io.read(
    process.argv[2] || "web/public/models/2022_tesla_model_y.glb"
  );
  if (
    doc
      .getRoot()
      .listNodes()
      .some((n) => n.getExtras().surfaceRevision === 2)
  )
    throw new Error(
      "Use the unbaked Blender export, not an already repaired model."
    );
  fs.mkdirSync(".local-data/model-y", { recursive: true });
  await doc.transform(dequantize());
  let data = [],
    targets = [];
  for (const node of doc.getRoot().listNodes()) {
    for (const p of node.getMesh()?.listPrimitives() || []) {
      const mat = p.getMaterial()?.getName();
      if (!["Pearl_White_Clearcoat", "Wheel_Graphite_Alloy"].includes(mat))
        continue;
      const matrix = new T.Matrix4().fromArray(node.getWorldMatrix()),
        nm = new T.Matrix3().getNormalMatrix(matrix);
      const pos = p.getAttribute("POSITION"),
        norm = p.getAttribute("NORMAL");
      const points = [],
        normals = [];
      for (let i = 0; i < pos.getCount(); i++) {
        points.push(
          new T.Vector3()
            .fromArray(pos.getElement(i, []))
            .applyMatrix4(matrix)
            .toArray()
        );
        normals.push(
          new T.Vector3()
            .fromArray(norm.getElement(i, []))
            .applyMatrix3(nm)
            .normalize()
            .toArray()
        );
      }
      data.push({
        name: node.getName(),
        material: mat,
        indices: Array.from(p.getIndices().getArray()),
        points,
        normals,
      });
      targets.push({ p, matrix, nm });
    }
  }
  fs.writeFileSync(
    ".local-data/model-y/surface-input.json",
    JSON.stringify(data)
  );
  cp.execFileSync(
    process.env.PYTHON || "python",
    ["tools/vehicle-model/repair-surfaces.py"],
    { stdio: "inherit" }
  );
  const result = JSON.parse(
    fs.readFileSync(".local-data/model-y/surface-output.json")
  );
  result.forEach((entry, j) => {
    const { p, matrix, nm } = targets[j],
      inv = matrix.clone().invert(),
      normalInv = nm.clone().invert();
    entry.points.forEach((point, i) =>
      p
        .getAttribute("POSITION")
        .setElement(
          i,
          new T.Vector3().fromArray(point).applyMatrix4(inv).toArray()
        )
    );
    entry.normals.forEach((normal, i) =>
      p
        .getAttribute("NORMAL")
        .setElement(
          i,
          new T.Vector3()
            .fromArray(normal)
            .applyMatrix3(normalInv)
            .normalize()
            .toArray()
        )
    );
  });
  for (const scene of doc.getRoot().listScenes())
    scene.setExtras({ ...scene.getExtras(), surfaceRevision: 2 });
  for (const node of doc.getRoot().listNodes())
    if (node.getName() === "Model_Y_2022")
      node.setExtras({ ...node.getExtras(), surfaceRevision: 2 });
  await doc.transform(meshopt({ encoder: MeshoptEncoder, level: "medium" }));
  await io.write(".local-data/model-y/surface-repaired.glb", doc);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
