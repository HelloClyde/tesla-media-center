import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { createVehicleLights } from './teslaLights';
import { createVehicleFlight } from './teslaFlight';

describe('official vehicle road headlights', () => {
  it('keeps lamps above the road and ahead of the body after model fitting and parent rotation', () => {
    const parent = new THREE.Group();
    parent.position.set(3, 2.6, -2);
    parent.rotation.y = .63;
    const model = new THREE.Group();
    model.position.set(.2, -2.4, .4);
    model.rotation.y = Math.PI;
    model.scale.setScalar(.85);
    const root = new THREE.Group();
    root.name = 'Y_High_Root';
    const body = new THREE.Mesh(new THREE.BoxGeometry(2, 1.6, 4.8), new THREE.MeshStandardMaterial());
    body.position.set(.1, .8, .2);
    root.add(body);
    model.add(root);
    const hidden = new THREE.Mesh(new THREE.BoxGeometry(100, 100, 100), body.material);
    hidden.visible = false;
    model.add(hidden);
    parent.add(model);
    const lights = createVehicleLights(model);
    const group = model.getObjectByName('Vehicle_display_lights')!;
    const beams = group.children.filter(node => node instanceof THREE.SpotLight) as THREE.SpotLight[];
    expect(beams).toHaveLength(2);
    lights.setEnabled(true);
    parent.updateWorldMatrix(true, true);
    const roadY = model.localToWorld(new THREE.Vector3(0, 0, 0)).y;
    for (const beam of beams) {
      const position = beam.getWorldPosition(new THREE.Vector3());
      const target = beam.target.getWorldPosition(new THREE.Vector3());
      expect(position.y - roadY).toBeCloseTo(1.6 * .35 * .85);
      expect(target.y).toBeCloseTo(roadY);
      expect(target.distanceTo(position)).toBeGreaterThan(15);
      expect(beam.position.z).toBeLessThan(.2 - 2.4);
      const ray = new THREE.Raycaster(position, target.clone().sub(position).normalize());
      expect(ray.intersectObject(body)).toHaveLength(0);
      expect(beam.intensity).toBeGreaterThan(0);
    }
    const before = beams.map(beam => beam.getWorldPosition(new THREE.Vector3()));
    const flight = createVehicleFlight(model, roadY - parent.position.y);
    flight.start();
    let lift = 0;
    for (let i = 0; i < 30; i++) lift = flight.update(.1).height;
    parent.updateWorldMatrix(true, true);
    beams.forEach((beam, i) => {
      const moved = beam.getWorldPosition(new THREE.Vector3()).sub(before[i]);
      expect(moved.x).toBeCloseTo(0);
      expect(moved.y).toBeCloseTo(lift);
      expect(moved.z).toBeCloseTo(0);
    });
    flight.reset();
    parent.updateWorldMatrix(true, true);
    beams.forEach((beam, i) => expect(beam.getWorldPosition(new THREE.Vector3()).distanceTo(before[i])).toBeLessThan(.00001));
    lights.setEnabled(false);
    expect(beams.every(beam => beam.intensity === 0)).toBe(true);
    lights.dispose();
    expect(group.parent).toBeNull();
    flight.dispose();
    body.geometry.dispose(); hidden.geometry.dispose(); body.material.dispose();
  });
});
