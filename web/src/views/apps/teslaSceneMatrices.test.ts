import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createSceneMatrixCache } from './teslaSceneMatrices';

describe('parked scene matrix cache', () => {
  function fixture() {
    const scene = new THREE.Scene();
    const pivot = new THREE.Group();
    const street = new THREE.Group();
    const building = new THREE.Object3D();
    const car = new THREE.Group();
    const door = new THREE.Object3D();
    scene.add(pivot); pivot.add(street, car); street.add(building); car.add(door);
    building.position.set(12, 0, 25);
    const cache = createSceneMatrixCache(scene);
    cache.update([car]);
    return { scene, pivot, street, building, car, door, cache };
  }

  it('updates the rising vehicle and its doors without traversing the static street', () => {
    const { scene, building, car, door, cache } = fixture();
    const streetUpdate = vi.spyOn(building, 'updateMatrixWorld');
    car.position.y = 1.35;
    door.position.x = .5;
    cache.update([car]);
    expect(streetUpdate).not.toHaveBeenCalled();
    expect(new THREE.Vector3().setFromMatrixPosition(door.matrixWorld).toArray()).toEqual([.5, 1.35, 0]);
    expect(new THREE.Vector3().setFromMatrixPosition(building.matrixWorld).toArray()).toEqual([12, 0, 25]);
    expect(scene.matrixWorldAutoUpdate).toBe(false);
    cache.dispose();
    expect(scene.matrixWorldAutoUpdate).toBe(true);
  });

  it('refreshes driving displacement and gear direction after invalidation', () => {
    const { pivot, street, building, car, cache } = fixture();
    pivot.rotation.y = Math.PI / 2;
    street.position.z = -5;
    cache.invalidate();
    cache.update([car]);
    const actual = new THREE.Vector3().setFromMatrixPosition(building.matrixWorld);
    expect(actual.x).toBeCloseTo(20);
    expect(actual.z).toBeCloseTo(-12);
    cache.dispose();
  });

  it('includes newly loaded street assets and preserves an already manual scene', () => {
    const { scene, street, cache } = fixture();
    const tree = new THREE.Object3D(); tree.position.y = 4; street.add(tree);
    scene.position.x = 2;
    cache.invalidate(); cache.update();
    expect(new THREE.Vector3().setFromMatrixPosition(tree.matrixWorld).toArray()).toEqual([2, 4, 0]);
    cache.dispose();
    scene.matrixWorldAutoUpdate = false;
    const manual = createSceneMatrixCache(scene);
    manual.update(); manual.dispose();
    expect(scene.matrixWorldAutoUpdate).toBe(false);
  });
});
