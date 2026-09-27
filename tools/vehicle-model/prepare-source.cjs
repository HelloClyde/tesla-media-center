// Run with Node 22+ from the repository root, before build_model_y.py.
const { NodeIO } = require('../../web/node_modules/@gltf-transform/core');
const { ALL_EXTENSIONS } = require('../../web/node_modules/@gltf-transform/extensions');
const { MeshoptDecoder } = require('../../web/node_modules/meshoptimizer');
const fs = require('node:fs');
(async () => {
  await MeshoptDecoder.ready;
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
  const doc = await io.read('web/public/models/2021_tesla_model_y.glb');
  for (const extension of doc.getRoot().listExtensionsUsed()) {
    if (extension.extensionName === 'EXT_meshopt_compression') extension.dispose();
  }
  fs.mkdirSync('.local-data/model-y', { recursive: true });
  await io.write('.local-data/model-y/base.glb', doc);
})().catch(error => { console.error(error); process.exitCode = 1; });
