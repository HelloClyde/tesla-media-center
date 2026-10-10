import {beforeEach, describe, expect, it, vi} from 'vitest';
import * as THREE from 'three';
import {flushPromises} from '@vue/test-utils';
import {groundPoint} from './teslaMapCoordinates';
const network = vi.hoisted(() => vi.fn());
vi.mock('axios', () => ({default: {get: network}}));
import {createAmapLandmarks, disposeGltfScenes} from './amapLandmarks';
beforeEach(() => {network.mockReset();});

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
  it('defers area queries during camera interaction, including a pending query continuation', async () => {
    let finish!: (response: unknown) => void;
    network.mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const landmarks = createAmapLandmarks({extensions: {has: () => false}} as any, vi.fn());
    const center: [number, number] = [120.2, 30.2], panned = groundPoint(center, 250, 0);
    landmarks.update(center, 'day', false);
    expect(network).not.toHaveBeenCalled();
    landmarks.update(center, 'day');
    expect(network).toHaveBeenCalledTimes(1);
    landmarks.update(panned, 'day', false);
    finish({data: {status: 'ok', data: {models: []}}});
    await flushPromises();
    expect(network).toHaveBeenCalledTimes(1);
    landmarks.update(panned, 'day');
    expect(network).toHaveBeenCalledTimes(2);
    landmarks.dispose();
  });
});
