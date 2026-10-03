import * as T from 'three';

/** Lamp anchors use the authored 2022 Model Y coordinates (+Z is forward). */
export function createVehicleLights(model: T.Object3D) {
  model.updateWorldMatrix(true, true);
  const body: T.Object3D[] = []; model.traverse(o => { if (o instanceof T.Mesh) body.push(o); });
  const group = new T.Group(); group.name = 'Vehicle_display_lights'; model.add(group);
  const front = new T.MeshStandardMaterial({ color: '#dcecff', emissive: '#dcecff', emissiveIntensity: 0, roughness: .2, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  const rear = new T.MeshStandardMaterial({ color: '#9c0810', emissive: '#ff1824', emissiveIntensity: 0, roughness: .3, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  const beams: T.SpotLight[] = [];
  const markers: T.PointLight[] = [];
  const lenses: T.Mesh[] = [];
  // This asset packs its lamp faces into the body palette. Select the actual
  // coloured lens triangles, not an approximate ribbon projected onto the body.
  const inverseModel = model.matrixWorld.clone().invert();
  for (const object of body) {
    const mesh = object as T.Mesh;
    if (Array.isArray(mesh.material) || !(mesh.material instanceof T.MeshStandardMaterial)) continue;
    if (!mesh.material.name.startsWith('PaletteMaterial') || !mesh.material.map) continue;
    const image = mesh.material.map.image as HTMLImageElement;
    const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
    const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const geometry = mesh.geometry, positions = geometry.getAttribute('position');
    const uv = geometry.getAttribute('uv'), indices = geometry.index;
    if (!uv) continue;
    const transform = inverseModel.clone().multiply(mesh.matrixWorld);
    const selected = { front: [] as number[], rear: [] as number[] };
    const center = new T.Vector3(), point = new T.Vector3();
    for (let i = 0; i < (indices?.count ?? positions.count); i += 3) {
      const ids = [0, 1, 2].map(j => indices ? indices.getX(i + j) : i + j);
      center.set(0, 0, 0);
      for (const id of ids) center.add(point.fromBufferAttribute(positions, id).applyMatrix4(transform));
      center.divideScalar(3);
      if (Math.abs(center.x) < .3 || Math.abs(center.x) > .87) continue;
      const x = T.MathUtils.clamp(Math.floor(uv.getX(ids[0]) * canvas.width), 0, canvas.width - 1);
      const v = mesh.material.map.flipY ? 1 - uv.getY(ids[0]) : uv.getY(ids[0]);
      const y = T.MathUtils.clamp(Math.floor(v * canvas.height), 0, canvas.height - 1);
      const pixel = (y * canvas.width + x) * 4;
      const r = pixels[pixel], g = pixels[pixel + 1], b = pixels[pixel + 2];
      if (center.z > 1.65 && center.y > .72 && center.y < 1.03
          && r > 130 && Math.abs(r - g) < 12 && Math.abs(g - b) < 12) selected.front.push(...ids);
      if (center.z < -1.8 && center.y > .94 && center.y < 1.17
          && r > 100 && r > g * 3 && r > b * 3) selected.rear.push(...ids);
    }
    for (const kind of ['front', 'rear'] as const) {
      if (!selected[kind].length) continue;
      const surface = new T.BufferGeometry();
      // Independent buffers allow cleanup without disposing the original model.
      for (const name of ['position', 'normal', 'uv']) {
        const attribute = geometry.getAttribute(name);
        if (attribute) surface.setAttribute(name, attribute.clone());
      }
      surface.setIndex(selected[kind]);
      surface.computeBoundingSphere();
      const lens = new T.Mesh(surface, kind === 'front' ? front : rear);
      lens.name = kind === 'front' ? 'Headlamp_full_lens' : 'Rear_red_marker_lens';
      lens.castShadow = false; lens.receiveShadow = false;
      mesh.add(lens); lenses.push(lens);
    }
  }
  for (const side of [-1, 1]) {
    const beam = new T.SpotLight('#e5efff', 0, 42, .3, .65, 2);
    beam.position.set(side*.68,.76,2.2);
    beam.target.position.set(side*1.6, -.2, 22);
    // One shadow caster keeps the beam from shining through roadside objects.
    beam.castShadow = side === -1;
    beam.shadow.mapSize.set(1024,1024);beam.shadow.bias=-.00015;beam.shadow.normalBias=.025;
    beam.shadow.camera.near=.15;
    group.add(beam,beam.target);beams.push(beam);
    const glow = new T.PointLight('#ff1525',0,1.5,2);
    glow.position.set(side*.7,1,-2.4);group.add(glow);markers.push(glow);
  }
  return { setEnabled(enabled: boolean) {
    front.emissiveIntensity=enabled ? 3 : 0;
    rear.emissiveIntensity=enabled ? 1.6 : 0;
    // Keep the light group in the scene with zero intensity while off.
    beams.forEach(light=>light.intensity=enabled ? 420 : 0);
    markers.forEach(light=>light.intensity=enabled ? .08 : 0);
    lenses.forEach(lens => { lens.visible = enabled; });
  }, dispose() {
    beams.forEach(light=>light.shadow.dispose());
    lenses.forEach(lens => { lens.geometry.dispose(); lens.removeFromParent(); });
    front.dispose();rear.dispose();group.removeFromParent();
  }};
}
