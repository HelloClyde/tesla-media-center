import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { createFlightTimeline, createVehicleFlight } from './teslaFlight';

describe('vehicle flight lifecycle', () => {
  it('ignites, lifts, hovers and lands automatically, then can be replayed', () => {
    const flight = createFlightTimeline();
    expect(flight.start()).toBe(true);
    expect(flight.start()).toBe(false);
    const phases = new Set<string>();
    let maximumHeight = 0;
    for (let i = 0; i < 650; i++) {
      const frame = flight.update(1 / 60);
      phases.add(frame.phase);
      maximumHeight = Math.max(maximumHeight, frame.height);
      expect(frame.height).toBeGreaterThanOrEqual(0);
      expect(frame.power).toBeGreaterThanOrEqual(0);
      expect(frame.power).toBeLessThanOrEqual(1);
    }
    expect([...phases]).toEqual(['ignition', 'ascent', 'hover', 'landing', 'idle']);
    expect(maximumHeight).toBeGreaterThan(1.3);
    expect(maximumHeight).toBeLessThan(1.4);
    expect(flight.update(0)).toMatchObject({ height: 0, power: 0, phase: 'idle' });
    expect(flight.start()).toBe(true);
  });

  it.each([.2, 1.4, 3.5])('can land early after %s seconds without snapping or lifting further', seconds => {
    const flight = createFlightTimeline();
    flight.start();
    for (let i = 0; i < Math.round(seconds * 60); i++) flight.update(1 / 60);
    let previous = flight.update(0).height;
    flight.land();
    for (let i = 0; i < 180; i++) {
      const frame = flight.update(1 / 60);
      expect(frame.height).toBeLessThanOrEqual(previous);
      expect(Math.abs(frame.height - previous)).toBeLessThan(.05);
      previous = frame.height;
    }
    expect(flight.active).toBe(false);
  });

  it('resets the animation without moving the road or altering the model transforms', () => {
    const parent = new THREE.Group();
    parent.position.y = .85;
    const model = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.6, 4.8), new THREE.MeshStandardMaterial());
    model.add(body);
    model.rotation.y = Math.PI;
    model.position.set(.1, -.2, -.1);
    model.scale.setScalar(.9);
    parent.add(model);
    const original = model.position.clone();
    const flight = createVehicleFlight(model, -.9);
    const exhaust = parent.getObjectByName('Vehicle_flight_exhaust')!;
    const rig = parent.getObjectByName('Vehicle_flight_rig')!;
    expect(exhaust.visible).toBe(false);
    flight.start();
    for (let i = 0; i < 200; i++) flight.update(1 / 60);
    expect(rig.position.y).toBeGreaterThan(1.3);
    expect(exhaust.position.y).toBe(0);
    expect(model.position.equals(original)).toBe(true);
    flight.reset();
    expect(rig.position.y).toBe(0);
    expect(rig.rotation.x).toBe(0);
    expect(rig.rotation.z).toBe(0);
    expect(exhaust.visible).toBe(false);
    flight.dispose();
    expect(model.parent).toBe(parent);
    expect(model.position.equals(original)).toBe(true);
    expect(model.scale.x).toBe(.9);
    expect(model.rotation.y).toBe(Math.PI);
    expect(parent.children).toEqual([model]);
    body.geometry.dispose();
    body.material.dispose();
  });
});
