import * as T from 'three';

/** Repeated city blocks: shared window atlases and instancing keep the skyline cheap. */
export function createVehicleSkyline() {
  const group = new T.Group(); group.name = 'City_skyline';
  let seed = 91823;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const facade = document.createElement('canvas'), lights = document.createElement('canvas');
  facade.width = lights.width = 256; facade.height = lights.height = 1024;
  const ctx = facade.getContext('2d')!, glow = lights.getContext('2d')!;
  ctx.fillStyle = '#637580'; ctx.fillRect(0, 0, 256, 1024);
  glow.fillStyle = '#000'; glow.fillRect(0, 0, 256, 1024);
  for (let floor = 0; floor < 48; floor++) for (let column = 0; column < 12; column++) {
    const x = column * 21 + 3, y = floor * 21 + 3;
    const shade = 44 + Math.floor(random() * 48);
    ctx.fillStyle = `rgb(${shade},${shade + 16},${shade + 25})`;
    ctx.fillRect(x, y, 15, 16);
    ctx.fillStyle = '#91a1aa'; ctx.fillRect(x, y, 15, 1);
    if (random() > .57) {
      glow.fillStyle = random() > .3 ? '#e4bc7c' : '#b3d0df';
      glow.fillRect(x, y, 15, 16);
    }
  }
  const map = new T.CanvasTexture(facade), emissiveMap = new T.CanvasTexture(lights);
  map.colorSpace = emissiveMap.colorSpace = T.SRGBColorSpace;
  map.anisotropy = emissiveMap.anisotropy = 4;
  const material = new T.MeshStandardMaterial({ map, emissiveMap, emissive: '#ffffff',
    emissiveIntensity: 0, roughness: .58, metalness: .18 });
  const roofMaterial = new T.MeshStandardMaterial({ color: '#71818e', metalness: .4, roughness: .5 });
  const geometry = new T.BoxGeometry(1, 1, 1), spireGeometry = new T.CylinderGeometry(0, 1, 1, 5);
  const blocks: { x: number; z: number; width: number; depth: number; height: number; tier: number }[] = [];
  // Three rows behind each low-rise street frontage, with a varied stepped silhouette.
  for (const side of [-1, 1]) for (let row = 0; row < 3; row++) for (let i = 0; i < 20; i++) {
    blocks.push({ x: side * (42 + row * 40 + random() * 14), z: i * 36 - 342 + random() * 8,
      width: 14 + random() * 13, depth: 18 + random() * 10,
      height: 25 + row * 12 + random() * 65 + (i % 7 === 0 ? 40 : 0), tier: i % 3 });
  }
  // Lower buildings fill the gaps behind the shop fronts, below the tower skyline.
  for (const side of [-1, 1]) for (let i = 0; i < 30; i++) {
    blocks.push({ x: side * 30, z: i * 24 - 348, width: 12, depth: 24,
      height: 16 + random() * 16, tier: 1 });
  }
  const towers = new T.InstancedMesh(geometry, material, blocks.length * 3);
  const spires = new T.InstancedMesh(spireGeometry, roofMaterial, blocks.length);
  towers.name = 'City_towers'; spires.name = 'City_spires';
  // Distant buildings do not need shadow maps; nearby buildings still cast shadows.
  towers.castShadow = spires.castShadow = false;
  towers.instanceMatrix.setUsage(T.DynamicDrawUsage); spires.instanceMatrix.setUsage(T.DynamicDrawUsage);
  const pose = new T.Object3D(); let offset = 0;
  function update() {
    pose.rotation.set(0, 0, 0);
    blocks.forEach((block, index) => {
      const z = ((block.z + offset + 360) % 720 + 720) % 720 - 360;
      for (let tier = 0; tier < 3; tier++) {
        const height = tier === 0 ? block.height : block.height * .10;
        const base = tier === 0 ? 0 : block.height * (1 + (tier - 1) * .10);
        const scale = tier === 0 ? 1 : 1 - tier * .22;
        pose.position.set(block.x, base + height / 2, z);
        pose.scale.set(block.width * scale, height, block.depth * scale);
        pose.updateMatrix(); towers.setMatrixAt(index * 3 + tier, pose.matrix);
      }
      const height = block.tier === 0 ? 14 : 2;
      pose.position.set(block.x, block.height * 1.2 + height / 2, z);
      pose.scale.set(block.tier === 0 ? 1.1 : .4, height, block.tier === 0 ? 1.1 : .4);
      pose.updateMatrix(); spires.setMatrixAt(index, pose.matrix);
    });
    towers.instanceMatrix.needsUpdate = spires.instanceMatrix.needsUpdate = true;
  }
  blocks.forEach((block, index) => {
    const color = new T.Color(['#c1ccd4', '#b3c4d4', '#d7cbbb', '#9caeba'][index % 4]);
    for (let tier = 0; tier < 3; tier++) towers.setColorAt(index * 3 + tier, color);
  });
  update();
  // Fixed conservative bounds stay valid when instances wrap during travel.
  const bounds = new T.Sphere(new T.Vector3(0, 80, 0), 430);
  towers.boundingSphere = bounds.clone(); spires.boundingSphere = bounds.clone();
  // A distant skyline closes the street's vanishing point instead of an empty horizon.
  // It is an atmospheric backdrop, so the foreground fog must not erase it entirely.
  const horizonMaterial = new T.MeshStandardMaterial({ map, emissiveMap, emissive: '#8eafd0',
    emissiveIntensity: 0, color: '#8da5b7', roughness: 1, fog: false });
  const hazeColor = { value: new T.Color('#c6d9e5') }, hazeAmount = { value: .48 };
  horizonMaterial.onBeforeCompile = shader => {
    shader.uniforms.cityHazeColor = hazeColor; shader.uniforms.cityHazeAmount = hazeAmount;
    shader.fragmentShader = 'uniform vec3 cityHazeColor; uniform float cityHazeAmount;\n' + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <tonemapping_fragment>',
      'gl_FragColor.rgb = mix(gl_FragColor.rgb, cityHazeColor, cityHazeAmount);\n#include <tonemapping_fragment>');
  };
  horizonMaterial.customProgramCacheKey = () => 'city-horizon-haze-v1';
  const horizon = new T.InstancedMesh(geometry, horizonMaterial, 96);
  horizon.name = 'Distant_city_horizon';
  for (let i = 0; i < 96; i++) {
    const angle = i * Math.PI * 2 / 96;
    const height = 25 + random() * 60;
    pose.position.set(Math.cos(angle) * 280, height / 2 - 15, Math.sin(angle) * 280);
    pose.rotation.y = -angle;
    pose.scale.set(12 + random() * 12, height, 24 + random() * 10);
    pose.updateMatrix(); horizon.setMatrixAt(i, pose.matrix);
  }
  horizon.computeBoundingSphere();
  group.add(towers, spires, horizon);
  return { group, advance(distance: number) {
    if (!Number.isFinite(distance) || !distance) return;
    offset = (offset + distance) % 720; update();
  }, setNight(night: boolean) {
    material.emissiveIntensity = night ? 1.4 : 0;
    hazeColor.value.set(night ? '#070e20' : '#c6d9e5'); hazeAmount.value = night ? .55 : .48;
    horizonMaterial.color.set(night ? '#152334' : '#8da5b7');
    horizonMaterial.emissiveIntensity = night ? .28 : 0;
  }, dispose() {
    horizon.dispose(); horizonMaterial.dispose(); towers.dispose(); spires.dispose(); geometry.dispose(); spireGeometry.dispose();
    material.dispose(); roofMaterial.dispose(); map.dispose(); emissiveMap.dispose(); group.removeFromParent();
  }};
}
