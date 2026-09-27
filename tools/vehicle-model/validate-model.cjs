const assert = require('node:assert/strict');
const { NodeIO } = require('../../web/node_modules/@gltf-transform/core');
const { ALL_EXTENSIONS } = require('../../web/node_modules/@gltf-transform/extensions');
const { MeshoptDecoder } = require('../../web/node_modules/meshoptimizer');
(async () => {
  await MeshoptDecoder.ready;
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
  const doc = await io.read('web/public/models/2022_tesla_model_y.glb');
  const nodes = doc.getRoot().listNodes();
  const groups = {};
  const animated = new Set(doc.getRoot().listAnimations().flatMap(a => a.listChannels().map(c => c.getTargetNode()?.getName())));
  for (const kind of ['Door', 'Wheel']) for (const corner of ['FL', 'FR', 'RL', 'RR']) {
    const name = `${kind}_${corner}`;
    const matches = nodes.filter(n => n.getName() === name);
    assert.equal(matches.length, 1, `${name} must be unique`);
    const node = groups[name] = matches[0];
    assert(node.listChildren().some(n => n.getMesh()), `${name} must own geometry`);
    const [x, y, z] = node.getTranslation();
    assert(corner.endsWith('L') ? x < 0 : x > 0, `${name} side`);
    assert(corner.startsWith('F') ? z > 0 : z < 0, `${name} front/rear`);
    assert(y > 0 && y < 1.5, `${name} pivot height`);
    assert.equal(node.getExtras().rotationAxis, kind === 'Door' ? 'y' : 'x');
    if (kind === 'Door') {
      assert(animated.has(name), `${name} open animation`);
      assert.equal(Math.sign(node.getExtras().openAngle), corner.endsWith('L') ? 1 : -1);
    } else assert.equal(node.getExtras().spinDirection, 1);
  }
  assert(Math.abs(groups.Wheel_FL.getTranslation()[2] - groups.Wheel_RL.getTranslation()[2] - 2.894) < .01, 'wheelbase');
  assert(nodes.some(n => n.getName() === 'Body_Static'), 'static body survives optimization');
  for (const mesh of doc.getRoot().listMeshes()) for (const primitive of mesh.listPrimitives()) {
    const positions = primitive.getAttribute('POSITION').getArray();
    assert(positions.every(Number.isFinite), 'finite geometry');
  }
  console.log('Validated: 4 hinged doors, 4 axle groups, animations, side/orientation, wheelbase and decoded geometry.');
})().catch(error => { console.error(error); process.exitCode = 1; });
