import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { disposeGltfScenes } from './amapLandmarks';

describe('App landmark resource lifecycle', () => {
  it('releases a day/night GLB texture, material and geometry once even when shared', () => {
    const geometry = new THREE.BoxGeometry();
    const texture = new THREE.Texture();
    const material = new THREE.MeshBasicMaterial({ map: texture });
    const day = new THREE.Group(), night = new THREE.Group();
    day.add(new THREE.Mesh(geometry, material));
    night.add(new THREE.Mesh(geometry, material));
    const disposed = { geometry: 0, material: 0, texture: 0 };
    geometry.addEventListener('dispose', () => disposed.geometry++);
    material.addEventListener('dispose', () => disposed.material++);
    texture.addEventListener('dispose', () => disposed.texture++);

    disposeGltfScenes([day, night]);

    expect(disposed).toEqual({ geometry: 1, material: 1, texture: 1 });
  });
});
