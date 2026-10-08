import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createVehicleSkin, readVehicleSkin, removeVehicleSkin, saveVehicleSkin } from './teslaVehicleSkin';

function car(rootName: string) {
  const root = new THREE.Group(); root.name = rootName;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1], 2));
  geometry.setAttribute('uv1', new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1], 2));
  const body = new THREE.MeshStandardMaterial({ name: 'PaintSkybox', color: '#aabbcc' });
  const trim = new THREE.MeshStandardMaterial({ name: 'PaintRough', color: '#222222' });
  const mesh = new THREE.Mesh(geometry, [body, trim]);
  root.add(mesh);
  return { root, body, trim, mesh };
}

describe('Model Y vehicle skin', () => {
  it('identifies each official model and ignores an unsupported model', async () => {
    const matching = car('Y_High_Root');
    const skin = createVehicleSkin(matching.root);
    expect(skin.supported).toBe(true);
    expect(skin.variant).toBe('modely-high');
    await skin.set(null);
    expect(matching.body.color.getHexString()).toBe('aabbcc');
    expect(matching.trim.color.getHexString()).toBe('222222');
    skin.dispose();

    const other = car('Bayberry_Root');
    expect(createVehicleSkin(other.root).variant).toBe('modely-juniper');
    expect(createVehicleSkin(other.root).supported).toBe(true);
    expect(createVehicleSkin(car('unrecognized').root).supported).toBe(false);
  });

  it('maps only the body paint and restores the original material when cleared', async () => {
    const { root, body, trim, mesh } = car('Y_High_Root');
    const loaded = new THREE.Texture<HTMLImageElement>();
    const load = vi.spyOn(THREE.TextureLoader.prototype, 'loadAsync').mockResolvedValue(loaded);
    const objectUrl = vi.fn(() => 'blob:test-skin');
    const revokeObjectUrl = vi.fn();
    const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
    const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: objectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl });
    const skin = createVehicleSkin(root);
    try {
      await skin.set(new Blob(['image'], { type: 'image/png' }));
      const painted = (mesh.material as THREE.Material[])[0] as THREE.MeshStandardMaterial;
      expect(painted.map).toBe(loaded);
      expect(painted.color.getHexString()).toBe('ffffff');
      expect((mesh.material as THREE.Material[])[1]).toBe(trim);
      expect(trim.color.getHexString()).toBe('222222');
      expect(loaded.flipY).toBe(false);
      expect(loaded.channel).toBe(1);
      await skin.set(null);
      expect(painted.map).toBeNull();
      expect(painted.color.getHexString()).toBe('aabbcc');
    } finally {
      skin.dispose(); load.mockRestore();
      if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate);
      else Reflect.deleteProperty(URL, 'createObjectURL');
      if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke);
      else Reflect.deleteProperty(URL, 'revokeObjectURL');
    }
    expect(objectUrl).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:test-skin');
    expect((mesh.material as THREE.Material[])[0]).toBe(body);
  });
});

describe('server vehicle skin storage', () => {
  it('uploads before reporting success and reads the shared server image', async () => {
    const image = new Blob(['uploaded-skin'], { type: 'image/png' });
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
      if (options?.method === 'PUT' || options?.method === 'DELETE') {
        return new Response(JSON.stringify({ status: 'ok' }), { headers: { 'content-type': 'application/json' } });
      }
      return { ok: true, headers: new Headers({ 'content-type': 'image/png' }), blob: async () => image } as Response;
    });
    try {
      await saveVehicleSkin('modely-high', image);
      expect(fetch).toHaveBeenCalledWith('/api/tesla/skins/modely-high', expect.objectContaining({ method: 'PUT', body: image }));
      expect(await readVehicleSkin('modely-high')).toBe(image);
      await removeVehicleSkin('modely-high');
      expect(fetch).toHaveBeenCalledWith('/api/tesla/skins/modely-high', expect.objectContaining({ method: 'DELETE' }));
    } finally { fetch.mockRestore(); }
  });

  it('rejects a failed upload', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ status: 'fail', message: '磁盘空间不足' }),
      { status: 500, headers: { 'content-type': 'application/json' } },
    ));
    try {
      await expect(saveVehicleSkin('modely-high', new Blob(['image']))).rejects.toThrow('磁盘空间不足');
    } finally { fetch.mockRestore(); }
  });

  it('does not overwrite a server skin during legacy migration', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ status: 'already_exists' }), { status: 412 },
    ));
    try {
      expect(await saveVehicleSkin('modely-high', new Blob(['old']), true)).toBe(false);
      expect(fetch).toHaveBeenCalledWith('/api/tesla/skins/modely-high', expect.objectContaining({
        headers: expect.objectContaining({ 'If-None-Match': '*' }),
      }));
    } finally { fetch.mockRestore(); }
  });
});
