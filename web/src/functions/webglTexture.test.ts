// @vitest-environment node
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';

it('updates live video textures without reallocating them each frame', () => {
  const context = vm.createContext({});
  vm.runInContext(readFileSync(new URL('../../public/webgl.js', import.meta.url), 'utf8'), context);
  const gl = {
    TEXTURE_2D: 1, TEXTURE_MAG_FILTER: 2, TEXTURE_MIN_FILTER: 3,
    TEXTURE_WRAP_S: 4, TEXTURE_WRAP_T: 5, LINEAR: 6,
    CLAMP_TO_EDGE: 7, LUMINANCE: 8, UNSIGNED_BYTE: 9,
    createTexture: vi.fn(() => ({})), bindTexture: vi.fn(), texParameteri: vi.fn(),
    texImage2D: vi.fn(), texSubImage2D: vi.fn(),
  };
  const texture = vm.runInContext('Texture', context);
  const instance = new texture(gl);
  instance.fill(1280, 720, new Uint8Array(1280 * 720));
  instance.fill(1280, 720, new Uint8Array(1280 * 720));
  instance.fill(640, 360, new Uint8Array(640 * 360));
  expect(gl.texImage2D).toHaveBeenCalledTimes(2);
  expect(gl.texSubImage2D).toHaveBeenCalledTimes(1);
});
