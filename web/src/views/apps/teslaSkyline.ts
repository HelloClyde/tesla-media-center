import * as T from 'three';

/** Repeated city blocks: shared window atlases and instancing keep the skyline cheap. */
export function createVehicleSkyline() {
  const group = new T.Group(); group.name = 'City_skyline';
  let seed = 91823;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const facade = document.createElement('canvas'), lights = document.createElement('canvas');
  facade.width = lights.width = 256; facade.height = lights.height = 1024;
  const ctx = facade.getContext('2d')!, glow = lights.getContext('2d')!;
  ctx.fillStyle = '#69747b'; ctx.fillRect(0, 0, 256, 1024);
  glow.fillStyle = '#000'; glow.fillRect(0, 0, 256, 1024);
  for (let floor = 0; floor < 48; floor++) {
    const y = floor * 21;
    ctx.fillStyle = floor % 5 === 0 ? '#59636a' : '#767f84';
    ctx.fillRect(0, y, 256, 2);
    ctx.fillStyle = '#424f58';
    ctx.fillRect(0, y + 19, 256, 2);
    for (let column = 0; column < 12; column++) {
      const x = column * 21 + 3;
      const shade = 30 + Math.floor(random() * 42);
      ctx.fillStyle = '#454e54'; ctx.fillRect(x - 2, y + 2, 19, 18);
      ctx.fillStyle = `rgb(${shade},${shade + 13},${shade + 22})`;
      ctx.fillRect(x, y + 4, 15, 14);
      ctx.fillStyle = `rgba(154,177,187,${.15 + random() * .2})`;
      ctx.fillRect(x + 1, y + 5, 5, 11);
      ctx.fillStyle = '#344149'; ctx.fillRect(x + 7, y + 4, 1, 14);
      if (random() > .72) {
        ctx.fillStyle = '#888d86'; ctx.fillRect(x + 8, y + 10, 7, 8);
      }
      ctx.fillStyle = '#9aa6ab'; ctx.fillRect(x - 2, y + 18, 19, 1);
      if (random() > .64) {
        glow.fillStyle = random() > .3 ? '#e4bc7c' : '#b3d0df';
        glow.fillRect(x, y + 4, 15, 14);
      }
    }
  }
  // Small stains and uneven concrete soften the repeated grid without adding
  // a per-building texture or more draw calls.
  for (let i = 0; i < 1600; i++) {
    const x = Math.floor(random() * 256), y = Math.floor(random() * 1024);
    ctx.fillStyle = random() > .5 ? 'rgba(24,30,32,.09)' : 'rgba(198,200,190,.06)';
    ctx.fillRect(x, y, 1 + Math.floor(random() * 3), 2 + Math.floor(random() * 8));
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
    // Keep the carriageway clear while allowing the skyline to read beyond
    // the street; the old 170 m gap left the vanishing point empty.
    const onRoadAxis = Math.abs(Math.cos(angle) * 280) < 24;
    if (onRoadAxis) pose.scale.setScalar(0);
    else pose.scale.set(12 + random() * 12, height, 24 + random() * 10);
    pose.updateMatrix(); horizon.setMatrixAt(i, pose.matrix);
  }
  horizon.computeBoundingSphere();
  // Carry the street frontages towards the horizon. Keep them beyond the
  // sidewalks and opaque: transparent instances were sorted after the car's
  // glass and appeared across its panoramic roof.
  const farFacade = document.createElement('canvas'), farLights = document.createElement('canvas');
  farFacade.width = farLights.width = 256; farFacade.height = farLights.height = 384;
  const farCtx = farFacade.getContext('2d')!, farGlow = farLights.getContext('2d')!;
  farCtx.fillStyle = '#777c7b'; farCtx.fillRect(0, 0, 256, 384);
  farGlow.fillStyle = '#000'; farGlow.fillRect(0, 0, 256, 384);
  for (let floor = 0; floor < 6; floor++) {
    const y = floor * 64;
    farCtx.fillStyle = '#444d51'; farCtx.fillRect(0, y, 256, 5);
    farCtx.fillStyle = '#afb0a8'; farCtx.fillRect(0, y + 59, 256, 3);
    for (let column = 0; column < 4; column++) {
      const x = column * 64 + 11;
      const shade = 27 + Math.floor(random() * 31);
      farCtx.fillStyle = '#41494d'; farCtx.fillRect(x - 4, y + 8, 48, 44);
      farCtx.fillStyle = `rgb(${shade},${shade + 11},${shade + 20})`;
      farCtx.fillRect(x, y + 12, 40, 36);
      farCtx.fillStyle = 'rgba(169,187,191,.25)'; farCtx.fillRect(x + 3, y + 13, 10, 31);
      farCtx.fillStyle = '#303b40'; farCtx.fillRect(x + 19, y + 12, 2, 36);
      if (random() > .7) {
        farCtx.fillStyle = '#8a8e88'; farCtx.fillRect(x + 21, y + 29, 19, 19);
      }
      if (random() > .68) {
        farGlow.fillStyle = random() > .25 ? '#dcb67d' : '#abc5ce';
        farGlow.fillRect(x, y + 12, 40, 36);
      }
    }
  }
  for (let i = 0; i < 500; i++) {
    farCtx.fillStyle = random() > .5 ? 'rgba(28,35,38,.1)' : 'rgba(201,196,180,.08)';
    farCtx.fillRect(random() * 256, random() * 384, 2 + random() * 4, 2 + random() * 9);
  }
  const farMap = new T.CanvasTexture(farFacade), farEmissiveMap = new T.CanvasTexture(farLights);
  farMap.colorSpace = farEmissiveMap.colorSpace = T.SRGBColorSpace;
  farMap.anisotropy = farEmissiveMap.anisotropy = 4;
  const farMaterial = material.clone();
  farMaterial.map = farMap;
  farMaterial.emissiveMap = farEmissiveMap;
  farMaterial.color.set('#d1d0c8');
  farMaterial.roughness = .92;
  farMaterial.metalness = 0;
  farMaterial.fog = false;
  const farHaze = { value: .43 };
  farMaterial.onBeforeCompile = shader => {
    shader.uniforms.cityHazeColor = hazeColor;
    shader.uniforms.cityFarHaze = farHaze;
    shader.fragmentShader = 'uniform vec3 cityHazeColor; uniform float cityFarHaze;\n' + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <tonemapping_fragment>',
      'gl_FragColor.rgb = mix(gl_FragColor.rgb, cityHazeColor, smoothstep(75.0, 260.0, length(vViewPosition)) * cityFarHaze);\n#include <tonemapping_fragment>');
  };
  farMaterial.customProgramCacheKey = () => 'city-far-haze-v1';
  const farBlocks = new T.InstancedMesh(geometry, farMaterial, 48);
  farBlocks.name = 'Distant_street_frontage';
  farBlocks.castShadow = farBlocks.receiveShadow = false;
  const farUpper = new T.InstancedMesh(geometry, farMaterial, 48);
  farUpper.name = 'Distant_street_setbacks';
  farUpper.castShadow = farUpper.receiveShadow = false;
  const farRoofs = new T.InstancedMesh(geometry, roofMaterial, 48);
  farRoofs.name = 'Distant_roof_cornices';
  farRoofs.castShadow = farRoofs.receiveShadow = false;
  let farIndex = 0;
  pose.rotation.set(0, 0, 0);
  for (const direction of [-1, 1]) for (const side of [-1, 1]) for (let i = 0; i < 12; i++) {
    const height = 12 + random() * 18 + (i % 5 === 0 ? 8 : 0);
    const width = 9 + random() * 4;
    const depth = 13 + random() * 8;
    const x = side * (19 + random() * 6);
    const z = direction * (79 + i * 17 + random() * 5);
    pose.position.set(x, height / 2, z);
    pose.scale.set(width, height, depth);
    pose.updateMatrix(); farBlocks.setMatrixAt(farIndex, pose.matrix);
    const tint = new T.Color(['#a3adb2', '#aeb4af', '#8d9ca7', '#b0a9a0', '#9ba4a7'][farIndex % 5]);
    farBlocks.setColorAt(farIndex, tint);
    const upperHeight = i % 4 === 0 ? 4 + random() * 5 : 0;
    pose.position.y = height + upperHeight / 2;
    pose.scale.set(width * .74, upperHeight, depth * .75);
    pose.updateMatrix(); farUpper.setMatrixAt(farIndex, pose.matrix);
    farUpper.setColorAt(farIndex, tint);
    pose.position.y = height + upperHeight + .12;
    pose.scale.set((upperHeight ? width * .74 : width) + .35, .24, (upperHeight ? depth * .75 : depth) + .35);
    pose.updateMatrix(); farRoofs.setMatrixAt(farIndex, pose.matrix);
    farIndex++;
  }
  farBlocks.computeBoundingSphere();
  farUpper.computeBoundingSphere();
  farRoofs.computeBoundingSphere();
  group.add(towers, spires, horizon, farBlocks, farUpper, farRoofs);
  return { group, advance(distance: number) {
    if (!Number.isFinite(distance) || !distance) return;
    offset = (offset + distance) % 720; update();
  }, setNight(night: boolean) {
    material.emissiveIntensity = night ? 1.4 : 0;
    farMaterial.emissiveIntensity = night ? 1.2 : 0;
    hazeColor.value.set(night ? '#070e20' : '#c6d9e5'); hazeAmount.value = night ? .55 : .48;
    horizonMaterial.color.set(night ? '#152334' : '#8da5b7');
    horizonMaterial.emissiveIntensity = night ? .28 : 0;
  }, setWeather(mode: 'clear' | 'cloudy' | 'rain' | 'fog' | 'snow', night: boolean) {
    hazeColor.value.set(night ? '#070e20' : mode === 'fog' ? '#b8c1c7' : mode === 'clear' ? '#c6d9e5' : '#9daab5');
    hazeAmount.value = night ? .55 : mode === 'rain' ? .26 : mode === 'snow' ? .38 : .48;
    farHaze.value = night ? .52 : mode === 'fog' ? .62 : mode === 'rain' ? .35 : .43;
    horizonMaterial.color.set(night ? '#152334' : mode === 'rain' ? '#687b87' : '#8da5b7');
  }, dispose() {
    horizon.dispose(); horizonMaterial.dispose(); towers.dispose(); spires.dispose(); farBlocks.dispose(); farUpper.dispose(); farRoofs.dispose(); geometry.dispose(); spireGeometry.dispose();
    material.dispose(); farMaterial.dispose(); roofMaterial.dispose(); map.dispose(); emissiveMap.dispose(); farMap.dispose(); farEmissiveMap.dispose(); group.removeFromParent();
  }};
}
