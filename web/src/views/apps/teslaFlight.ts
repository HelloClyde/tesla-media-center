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
  const uniforms = { time: { value: 0 }, power: { value: 0 } };
  const plumeGeometry = new THREE.CylinderGeometry(.055, .24, 1, 18, 1, true);
  const plumeMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending, toneMapped: false,
    vertexShader: `varying vec2 vUv;
      void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position,1.);}`,
    fragmentShader: `uniform float time;uniform float power;varying vec2 vUv;
      void main(){
        float downstream=1.-vUv.y;
        float streak=.7+.3*sin(vUv.x*75.+sin(downstream*16.-time*22.)*1.5);
        float pulse=.86+.14*sin(time*47.+downstream*25.);
        float fade=smoothstep(0.,.14,vUv.y)*(.7+.3*vUv.y);
        vec3 color=mix(vec3(.36,.73,1.),vec3(.85,.96,1.),vUv.y);
        gl_FragColor=vec4(color,fade*streak*pulse*power*.46);
      }`,
  });
  const jets = new THREE.InstancedMesh(plumeGeometry, plumeMaterial, 4);
  const cores = new THREE.InstancedMesh(plumeGeometry, plumeMaterial, 4);
  const nozzleGeometry = new THREE.CylinderGeometry(.085, .065, .09, 16, 1, true);
  const nozzleMaterial = new THREE.MeshStandardMaterial({ color: '#2b3f48', metalness: .8, roughness: .3, side: THREE.DoubleSide });
  const nozzles = new THREE.InstancedMesh(nozzleGeometry, nozzleMaterial, 4);
  const glowGeometry = new THREE.PlaneGeometry(1, 1);
  const glowMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    vertexShader: `varying vec2 vUv;
      void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position,1.);}`,
    fragmentShader: `uniform float time;uniform float power;varying vec2 vUv;
      void main(){float r=length(vUv*2.-1.);
        float band=(r-.55-.035*sin(time*12.))*9.;float ring=exp(-band*band);
        float center=exp(-r*r*12.);
        gl_FragColor=vec4(.42,.72,.87,(ring*.12+center*.23)*power*(1.-smoothstep(.8,1.,r)));
      }`,
  });
  const glows = new THREE.InstancedMesh(glowGeometry, glowMaterial, 4);
  for (const mesh of [jets, cores, nozzles, glows]) {
    mesh.frustumCulled = false;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    exhaust.add(mesh);
  }
  const count = 160;
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const anchor = anchors[i % 4];
    positions.set([anchor.x, groundY + .025, anchor.z], i * 3);
    seeds.set([i * 2.39996, .6 + (i % 11) / 20, (i * .618034) % 1], i * 3);
  }
  const sprayGeometry = new THREE.BufferGeometry();
  sprayGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  sprayGeometry.setAttribute('seed', new THREE.BufferAttribute(seeds, 3));
  const sprayMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, toneMapped: false,
    vertexShader: `attribute vec3 seed;uniform float time;uniform float power;varying float alpha;
      void main(){float age=fract(time*.8+seed.z);float radius=age*1.9*seed.y;
        vec3 p=position+vec3(cos(seed.x)*radius,sin(age*3.14159)*.22,sin(seed.x)*radius);
        vec4 view=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*view;
        gl_PointSize=clamp((18.+age*34.)/max(1.,-view.z),1.,13.);
        alpha=sin(age*3.14159)*(1.-age)*power*.34;
      }`,
    fragmentShader: `varying float alpha;
      void main(){float r=length(gl_PointCoord*2.-1.);if(r>1.)discard;
        gl_FragColor=vec4(.74,.83,.87,alpha*(1.-smoothstep(.15,1.,r)));}`,
  });
  const spray = new THREE.Points(sprayGeometry, sprayMaterial);
  spray.frustumCulled = false;
  exhaust.add(spray);
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
    if (exhaust.visible) anchors.forEach((anchor, i) => {
      nozzle.copy(anchor).applyMatrix4(rig.matrix);
      const length = Math.max(.04, nozzle.y - groundY - .025);
      const spread = (.65 + state.height * .42) * Math.max(.1, state.power);
      transform.rotation.set(0, 0, 0);
      transform.position.copy(nozzle);
      transform.scale.setScalar(1);
      transform.updateMatrix();
      nozzles.setMatrixAt(i, transform.matrix);
      transform.position.y -= length * .5;
      transform.scale.set(spread, length, spread);
      transform.updateMatrix();
      jets.setMatrixAt(i, transform.matrix);
      transform.position.y = nozzle.y - length * .36;
      transform.scale.set(spread * .33, length * .72, spread * .33);
      transform.updateMatrix();
      cores.setMatrixAt(i, transform.matrix);
      transform.position.set(nozzle.x, groundY + .018, nozzle.z);
      transform.rotation.x = -Math.PI / 2;
      transform.scale.setScalar(1.1 + state.height * .65);
      transform.updateMatrix();
      glows.setMatrixAt(i, transform.matrix);
    });
    for (const mesh of [jets, cores, nozzles, glows]) mesh.instanceMatrix.needsUpdate = true;
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
      plumeGeometry.dispose(); plumeMaterial.dispose();
      nozzleGeometry.dispose(); nozzleMaterial.dispose();
      glowGeometry.dispose(); glowMaterial.dispose();
      sprayGeometry.dispose(); sprayMaterial.dispose();
      for (const mesh of [jets, cores, nozzles, glows]) mesh.dispose();
    },
  };
}
