const { NodeIO } = require('../../web/node_modules/@gltf-transform/core');
const { ALL_EXTENSIONS } = require('../../web/node_modules/@gltf-transform/extensions');
const { dedup, meshopt } = require('../../web/node_modules/@gltf-transform/functions');
const { MeshoptEncoder, MeshoptDecoder } = require('../../web/node_modules/meshoptimizer');
(async () => {
  await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready]);
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
    'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder,
  });
  const path = 'web/public/models/2022_tesla_model_y.glb';
  const doc = await io.read(path);
  // Do not flatten or merge nodes: door hinges and wheel axles are API surface.
  await doc.transform(dedup(), meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
  await io.write(path, doc);
})().catch(error => { console.error(error); process.exitCode = 1; });
