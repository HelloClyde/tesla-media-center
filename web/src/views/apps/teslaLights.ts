import * as T from 'three';

/** Lamp anchors use the authored 2022 Model Y coordinates (+Z is forward). */
export function createVehicleLights(model: T.Object3D) {
  model.updateWorldMatrix(true, true);
  const body: T.Object3D[] = []; model.traverse(o => { if (o instanceof T.Mesh) body.push(o); });
  const group = new T.Group(); group.name = 'Vehicle_display_lights'; model.add(group);
  const front = new T.MeshStandardMaterial({ color: '#dcecff', emissive: '#dcecff', emissiveIntensity: 0, roughness: .2 });
  const rear = new T.MeshStandardMaterial({ color: '#9c0810', emissive: '#ff1824', emissiveIntensity: 0, roughness: .3 });
  const beams: T.SpotLight[] = [];
  const markers: T.PointLight[] = [];
  function strip(points: number[][], material: T.Material, radius: number) {
    // Project LED points onto the actual lens/body surface to avoid floating strips.
    const fitted = points.map(p => {
      const sign = Math.sign(p[2]);
      const origin = model.localToWorld(new T.Vector3(p[0],p[1],sign*5));
      const direction = new T.Vector3(0,0,-sign).transformDirection(model.matrixWorld);
      const hit = new T.Raycaster(origin,direction).intersectObjects(body,false)[0];
      return hit ? model.worldToLocal(hit.point.clone()).add(new T.Vector3(0,0,sign*.008)) : null;
    }).filter((p): p is T.Vector3 => p !== null);
    if (fitted.length < 2) return;
    const curve = new T.CatmullRomCurve3(fitted);
    const mesh = new T.Mesh(new T.TubeGeometry(curve, 16, radius, 6, false), material);
    group.add(mesh);
  }
  for (const side of [-1, 1]) {
    // Slim LED signatures follow the swept front lens and rear corner.
    strip([[side*.53,.78,2.23],[side*.67,.8,2.18],[side*.79,.85,2.04],[side*.84,.86,1.95]], front, .012);
    strip([[side*.43,1.03,-2.32],[side*.65,1.05,-2.26],[side*.82,1.06,-2.12],[side*.86,1.06,-1.99]], rear, .014);
    const beam = new T.SpotLight('#e5efff', 0, 42, .3, .65, 2);
    beam.position.set(side*.68,.76,2.2);
    beam.target.position.set(side*1.6, -.2, 22);
    // A shared shadow caster prevents the beam from shining through roadside objects.
    beam.castShadow = side === -1;
    beam.shadow.mapSize.set(1024,1024);beam.shadow.bias=-.00015;beam.shadow.normalBias=.025;
    beam.shadow.camera.near=.15;
    group.add(beam,beam.target);beams.push(beam);
    const glow = new T.PointLight('#ff1525',0,2,2);
    glow.position.set(side*.7,1,-2.4);group.add(glow);markers.push(glow);
  }
  return { setEnabled(enabled: boolean) {
    front.emissiveIntensity=enabled ? 6 : 0;
    rear.emissiveIntensity=enabled ? 3 : 0;
    beams.forEach(light=>light.intensity=enabled ? 220 : 0);
    markers.forEach(light=>light.intensity=enabled ? 1.2 : 0);
    group.visible=enabled;
  }, dispose() {
    beams.forEach(light=>light.shadow.dispose());
    group.traverse(o=>{if(o instanceof T.Mesh)o.geometry.dispose();});
    front.dispose();rear.dispose();group.removeFromParent();
  }};
}
