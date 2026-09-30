import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

await build({
  entryPoints: [fileURLToPath(new URL('./core-entry.ts', import.meta.url))],
  outfile: fileURLToPath(new URL('../../public/tts/amap-1.0/amap-core.js', import.meta.url)),
  bundle: true,
  minify: true,
  format: 'iife',
  globalName: 'AmapCore',
  platform: 'browser',
  target: 'es2020',
});
