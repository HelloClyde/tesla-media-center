import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  // Public image URLs stay browser URLs; unit tests must not import them as
  // native file:// modules, especially on Windows.
  plugins: [vue({ template: { transformAssetUrls: false } })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
});
