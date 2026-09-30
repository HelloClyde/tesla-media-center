import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { createVehicleWeather } from './teslaWeather';

describe('vehicle rain impacts', () => {
  it('shows pooled splashes on the car only while it rains', () => {
    const vehicle = new THREE.Mesh(
      new THREE.BoxGeometry(2, 1, 4),
      new THREE.MeshStandardMaterial({ name: 'Pearl_White_Clearcoat' }),
    );
    vehicle.position.y = 1;
    const weather = createVehicleWeather();
    const scene = new THREE.Group();
    scene.add(vehicle, weather.group);
    weather.setImpactSurface(vehicle);
    const splashes = weather.group.getObjectByName('Vehicle_rain_splashes') as THREE.LineSegments;
    expect(splashes).toBeDefined();
    expect(splashes.geometry.getAttribute('position').count).toBe(24 * 3 * 2);
    weather.set('rain', false);
    expect(splashes.visible).toBe(true);
    for (let i = 0; i < 60; i++) weather.update(1 / 60);
    expect(Array.from(splashes.geometry.getAttribute('position').array).some(value => value > 0)).toBe(true);
    weather.set('clear', false);
    expect(splashes.visible).toBe(false);
    weather.dispose();
    vehicle.geometry.dispose();
    (vehicle.material as THREE.Material).dispose();
  });
});
