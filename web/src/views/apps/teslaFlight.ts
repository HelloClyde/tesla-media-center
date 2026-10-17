import * as THREE from 'three';
import { vehicleLocalBounds } from './teslaModelBounds';

export type VehicleFlightPhase = 'idle' | 'ignition' | 'ascent' | 'hover' | 'landing';
const FLIGHT_HEIGHT = 1.35;
const smooth = (value: number) => {
  const t = THREE.MathUtils.clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
};

function createGasTexture() {
  const size = 64;
  const pixels = new Uint8Array(size * size * 4);
  const hash = (x: number, y: number) => {
    let value = Math.imul(x, 374761393) ^ Math.imul(y, 668265263);
    value = Math.imul(value ^ (value >>> 13), 1274126177);
    return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
  };
  const noise = (x: number, y: number) => {
    const ix = Math.floor(x), iy = Math.floor(y);
    const fx = smooth(x - ix), fy = smooth(y - iy);
    return THREE.MathUtils.lerp(
      THREE.MathUtils.lerp(hash(ix, iy), hash(ix + 1, iy), fx),
      THREE.MathUtils.lerp(hash(ix, iy + 1), hash(ix + 1, iy + 1), fx), fy,
    );
  };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const u = (x + .5) / size, v = (y + .5) / size;
    const radius = Math.hypot(u * 2 - 1, v * 2 - 1);
    const billow = noise(u * 3.6, v * 3.6) * .65 + noise(u * 7.5, v * 7.5) * .35;
    const edge = 1 - THREE.MathUtils.smoothstep(radius, .2 + billow * .2, .84 + billow * .16);
    const i = (y * size + x) * 4;
    pixels[i] = pixels[i + 1] = pixels[i + 2] = Math.round(232 + billow * 23);
    pixels[i + 3] = Math.round(255 * edge * (.55 + billow * .45));
  }
  const texture = new THREE.DataTexture(pixels, size, size, THREE.RGBAFormat);
  texture.generateMipmaps = true;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  return texture;
}

/** Local scene animation only; elapsed time pauses whenever the viewer pauses. */
export function createFlightTimeline() {
  let time = 0;
  let phase: VehicleFlightPhase = 'idle';
  let height = 0;
  let power = 0;
  let landing: { time: number; height: number; power: number; duration: number } | null = null;
  const reset = () => { time = height = power = 0; phase = 'idle'; landing = null; };
  const land = () => {
    if (phase === 'idle' || landing) return;
    landing = { time: 0, height, power, duration: Math.max(.6, 1.9 * height / FLIGHT_HEIGHT) };
    phase = 'landing';
  };
  return {
    get phase() { return phase; },
    get active() { return phase !== 'idle'; },
    start() {
      if (phase !== 'idle') return false;
      reset();
      phase = 'ignition';
      return true;
    },
    land,
    reset,
    update(delta: number) {
      const dt = Number.isFinite(delta) ? THREE.MathUtils.clamp(delta, 0, .1) : 0;
      if (phase !== 'idle') {
        time += dt;
        if (time >= 6.8 && !landing) land();
        if (landing) {
          landing.time += dt;
          height = landing.height * (1 - smooth(landing.time / landing.duration));
          power = landing.power * (1 - smooth((landing.time - landing.duration) / .6));
          if (landing.time >= landing.duration + .6) reset();
        } else {
          power = smooth(time / .65);
          height = FLIGHT_HEIGHT * smooth((time - .65) / 1.8);
          phase = time < .65 ? 'ignition' : time < 2.45 ? 'ascent' : 'hover';
          // Ease in the small hover motion instead of snapping at the end of ascent.
          height += Math.sin((time - 2.45) * 2.4) * .022 * smooth((time - 2.45) / .7);
        }
      }
      return { phase, height, power, time };
    },
  };
}

/** Four cold-gas jets, road-level spray and a separate rig preserve the model's authored transforms. */
export function createVehicleFlight(model: THREE.Group, groundY: number) {
  const parent = model.parent!;
  const bounds = vehicleLocalBounds(model);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const rig = new THREE.Group();
  rig.name = 'Vehicle_flight_rig';
  parent.add(rig);
  rig.add(model);
  const exhaust = new THREE.Group();
  exhaust.name = 'Vehicle_flight_exhaust';
  exhaust.visible = false;
  parent.add(exhaust);
  const timeline = createFlightTimeline();
  const anchors = [-1, 1].flatMap(x => [-1, 1].map(z => new THREE.Vector3(
    center.x + x * size.x * .31, bounds.min.y + size.y * .17, center.z + z * size.z * .3,
  )));
  const gasTexture = createGasTexture();
  const uniforms = {
    time: { value: 0 }, power: { value: 0 }, lift: { value: 0 },
    vehicleMatrix: { value: model.matrix.clone() },
    groundY: { value: groundY }, gasMap: { value: gasTexture },
  };
  const nozzleGeometry = new THREE.CylinderGeometry(.085, .065, .09, 16, 1, true);
  const nozzleMaterial = new THREE.MeshStandardMaterial({ color: '#2b3f48', metalness: .8, roughness: .3, side: THREE.DoubleSide });
  const nozzles = new THREE.InstancedMesh(nozzleGeometry, nozzleMaterial, 4);
  nozzles.frustumCulled = false;
  nozzles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  exhaust.add(nozzles);

  // Soft billboards overlap into a turbulent white gas jet. They use ordinary
  // alpha blending, so the exhaust has no luminous core or projected light pool.
  // A tiny baked sprite replaces per-fragment procedural noise. Larger, denser
  // puffs preserve the white plume with much less transparent overdraw.
  const jetCount = 128;
  const count = jetCount + 96;
  const nozzleAnchors = new Float32Array(count * 3);
  const seeds = new Float32Array(count * 4);
  const directions = new Float32Array(count * 2);
  const groundClouds = new Float32Array(count);
  let seed = 981723;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < count; i++) {
    const anchor = anchors[i % 4];
    nozzleAnchors.set([anchor.x, anchor.y, anchor.z], i * 3);
    // Independent birth phases avoid an apparent rotating wave across fixed rays.
    const angle = random() * Math.PI * 2;
    seeds.set([random(), 0, random(), random()], i * 4);
    directions.set([Math.cos(angle), Math.sin(angle)], i * 2);
    groundClouds[i] = i >= jetCount ? 1 : 0;
  }
  const quad = new THREE.PlaneGeometry(1, 1);
  const gasGeometry = new THREE.InstancedBufferGeometry();
  gasGeometry.setIndex(quad.index!.clone());
  gasGeometry.setAttribute('position', quad.getAttribute('position').clone());
  gasGeometry.setAttribute('uv', quad.getAttribute('uv').clone());
  quad.dispose();
  gasGeometry.setAttribute('nozzleAnchor', new THREE.InstancedBufferAttribute(nozzleAnchors, 3));
  gasGeometry.setAttribute('particleSeed', new THREE.InstancedBufferAttribute(seeds, 4));
  gasGeometry.setAttribute('flowDirection', new THREE.InstancedBufferAttribute(directions, 2));
  gasGeometry.setAttribute('groundCloud', new THREE.InstancedBufferAttribute(groundClouds, 1));
  gasGeometry.instanceCount = count;
  const gasMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.NormalBlending, toneMapped: false,
    vertexShader: `
      attribute vec3 nozzleAnchor;attribute vec4 particleSeed;attribute vec2 flowDirection;attribute float groundCloud;
      uniform float time;uniform float power;uniform float lift;uniform float groundY;uniform mat4 vehicleMatrix;
      varying vec2 vUv;varying float vAlpha;
      void main(){
        float age=fract(time*mix(2.6,.75,groundCloud)+particleSeed.x);
        vec3 nozzle=(vehicleMatrix*vec4(nozzleAnchor,1.)).xyz+vec3(0.,lift,0.);
        float distanceToRoad=max(.04,nozzle.y-groundY-.025);
        float spread=.035+age*age*(.2+lift*.13);
        vec3 jet=nozzle+vec3(flowDirection.x*spread,-age*distanceToRoad,flowDirection.y*spread);
        jet.y=max(groundY+.025,jet.y);
        float radius=age*(1.45+lift*.55)*(.65+particleSeed.z*.5);
        vec3 mist=vec3(nozzle.x+flowDirection.x*radius,
          groundY+.06+age*(1.-age)*(.72+particleSeed.w*.48),nozzle.z+flowDirection.y*radius);
        vec3 center=mix(jet,mist,groundCloud);
        float size=mix(.16+age*.7,.55+age*1.35,groundCloud)*(.8+particleSeed.w*.4);
        size*=.5+.5*power;
        vec4 view=modelViewMatrix*vec4(center,1.);
        view.xy+=position.xy*size;
        gl_Position=projectionMatrix*view;
        vUv=mix(uv,1.-uv,step(vec2(.5),particleSeed.zw));
        float fade=smoothstep(0.,.08,age)*(1.-smoothstep(.68,1.,age));
        vAlpha=fade*power*mix(.52,.3,groundCloud);
      }`,
    fragmentShader: `
      varying vec2 vUv;varying float vAlpha;uniform sampler2D gasMap;
      void main(){
        vec4 puff=texture2D(gasMap,vUv);float alpha=puff.a*vAlpha;
        if(alpha<.008)discard;
        gl_FragColor=vec4(puff.rgb,alpha);
      }`,
  });
  const gas = new THREE.Mesh(gasGeometry, gasMaterial);
  gas.name = 'Vehicle_white_gas';
  gas.frustumCulled = false;
  exhaust.add(gas);
  const transform = new THREE.Object3D();
  const nozzle = new THREE.Vector3();
  function update(dt: number) {
    const state = timeline.update(dt);
    rig.position.y = state.height;
    rig.rotation.set(0, 0, 0);
    rig.updateMatrix();
    exhaust.visible = timeline.active;
    uniforms.time.value = state.time;
    uniforms.power.value = state.power;
    uniforms.lift.value = state.height;
    if (model.matrixAutoUpdate) model.updateMatrix();
    uniforms.vehicleMatrix.value.copy(model.matrix);
    if (exhaust.visible) anchors.forEach((anchor, i) => {
      nozzle.copy(anchor).applyMatrix4(uniforms.vehicleMatrix.value);
      nozzle.y += state.height;
      transform.rotation.set(0, 0, 0);
      transform.position.copy(nozzle);
      transform.scale.setScalar(1);
      transform.updateMatrix();
      nozzles.setMatrixAt(i, transform.matrix);
    });
    nozzles.instanceMatrix.needsUpdate = true;
    return state;
  }
  return {
    get active() { return timeline.active; },
    matrixRoots: [rig, exhaust] as readonly THREE.Object3D[],
    start: timeline.start,
    land: timeline.land,
    update,
    reset() { timeline.reset(); update(0); },
    dispose() {
      timeline.reset();
      parent.add(model);
      rig.removeFromParent();
      exhaust.removeFromParent();
      nozzleGeometry.dispose(); nozzleMaterial.dispose();
      gasGeometry.dispose(); gasMaterial.dispose();
      gasTexture.dispose();
      nozzles.dispose();
    },
  };
}
