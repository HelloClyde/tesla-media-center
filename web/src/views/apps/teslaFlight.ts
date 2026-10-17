import * as THREE from 'three';

export type VehicleFlightPhase = 'idle' | 'ignition' | 'ascent' | 'hover' | 'landing';
const FLIGHT_HEIGHT = 1.35;
const smooth = (value: number) => {
  const t = THREE.MathUtils.clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
};

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
  parent.updateWorldMatrix(true, true);
  const bounds = new THREE.Box3().setFromObject(model).applyMatrix4(parent.matrixWorld.clone().invert());
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
  const uniforms = {
    time: { value: 0 }, power: { value: 0 }, lift: { value: 0 },
    rigMatrix: { value: new THREE.Matrix4() }, groundY: { value: groundY },
  };
  const nozzleGeometry = new THREE.CylinderGeometry(.085, .065, .09, 16, 1, true);
  const nozzleMaterial = new THREE.MeshStandardMaterial({ color: '#2b3f48', metalness: .8, roughness: .3, side: THREE.DoubleSide });
  const nozzles = new THREE.InstancedMesh(nozzleGeometry, nozzleMaterial, 4);
  nozzles.frustumCulled = false;
  nozzles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  exhaust.add(nozzles);

  // Soft billboards overlap into a turbulent white gas jet. They use ordinary
  // alpha blending, so the exhaust has no luminous core or projected light pool.
  // All particles move on the GPU; no textures or per-frame particle uploads.
  const jetCount = 448;
  const count = jetCount + 320;
  const nozzleAnchors = new Float32Array(count * 3);
  const seeds = new Float32Array(count * 4);
  const groundClouds = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const anchor = anchors[i % 4];
    nozzleAnchors.set([anchor.x, anchor.y, anchor.z], i * 3);
    seeds.set([(i * .618034) % 1, i * 2.39996, (i * .414214) % 1, (i * .732051) % 1], i * 4);
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
  gasGeometry.setAttribute('groundCloud', new THREE.InstancedBufferAttribute(groundClouds, 1));
  gasGeometry.instanceCount = count;
  const gasMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.NormalBlending, toneMapped: false,
    vertexShader: `
      attribute vec3 nozzleAnchor;attribute vec4 particleSeed;attribute float groundCloud;
      uniform float time;uniform float power;uniform float lift;uniform float groundY;uniform mat4 rigMatrix;
      varying vec2 vUv;varying float vAlpha;varying float vAge;varying vec2 vNoiseOffset;
      void main(){
        float age=fract(time*mix(2.6,.75,groundCloud)+particleSeed.x);
        vec3 nozzle=(rigMatrix*vec4(nozzleAnchor,1.)).xyz;
        float distanceToRoad=max(.04,nozzle.y-groundY-.025);
        float spread=.035+age*age*(.2+lift*.13);
        float swirl=particleSeed.y+age*8.+time*1.4;
        vec3 jet=nozzle+vec3(cos(swirl)*spread,-age*distanceToRoad,sin(swirl)*spread);
        jet.y=max(groundY+.025,jet.y);
        float radius=age*(1.45+lift*.55)*(.65+particleSeed.z*.5);
        float angle=particleSeed.y+age*.8;
        vec3 mist=vec3(nozzle.x+cos(angle)*radius,
          groundY+.06+sin(age*3.14159)*(.18+particleSeed.w*.12)
          +sin(age*14.+particleSeed.y)*.025,nozzle.z+sin(angle)*radius);
        vec3 center=mix(jet,mist,groundCloud);
        float size=mix(.14+age*.68,.5+age*1.3,groundCloud)*(.8+particleSeed.w*.4);
        size*=.5+.5*power;
        vec4 view=modelViewMatrix*vec4(center,1.);
        view.xy+=position.xy*size;
        gl_Position=projectionMatrix*view;
        vUv=uv;vAge=age;vNoiseOffset=particleSeed.zw*23.;
        float fade=smoothstep(0.,.08,age)*(1.-smoothstep(.68,1.,age));
        vAlpha=fade*power*mix(.25,.12,groundCloud);
      }`,
    fragmentShader: `
      varying vec2 vUv;varying float vAlpha;varying float vAge;varying vec2 vNoiseOffset;
      float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
      float noise(vec2 p){
        vec2 cell=floor(p),f=fract(p);f=f*f*(3.-2.*f);
        return mix(mix(hash(cell),hash(cell+vec2(1.,0.)),f.x),
          mix(hash(cell+vec2(0.,1.)),hash(cell+vec2(1.,1.)),f.x),f.y);
      }
      void main(){
        vec2 p=vUv*2.-1.;float r=length(p);
        if(r>1.)discard;
        vec2 flow=vUv*3.6+vNoiseOffset+vec2(vAge*.8,-vAge*1.5);
        float billow=.65*noise(flow)+.35*noise(flow*2.1);
        float edge=1.-smoothstep(.22+billow*.18,.86+billow*.14,r);
        float alpha=edge*(.5+billow*.5)*vAlpha;
        gl_FragColor=vec4(vec3(.88+billow*.12),alpha);
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
    const lift = state.height / FLIGHT_HEIGHT;
    rig.rotation.x = Math.sin(state.time * 1.8) * .012 * lift;
    rig.rotation.z = Math.sin(state.time * 2.1) * .009 * lift;
    rig.updateMatrix();
    exhaust.visible = timeline.active;
    uniforms.time.value = state.time;
    uniforms.power.value = state.power;
    uniforms.lift.value = state.height;
    uniforms.rigMatrix.value.copy(rig.matrix);
    if (exhaust.visible) anchors.forEach((anchor, i) => {
      nozzle.copy(anchor).applyMatrix4(rig.matrix);
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
      nozzles.dispose();
    },
  };
}
