import { promises as fs } from 'node:fs';
import path from 'node:path';
import { brotliCompress, constants, gzip } from 'node:zlib';
import { promisify } from 'node:util';

const gzipAsync = promisify(gzip);
const brotliAsync = promisify(brotliCompress);

const rootDir = path.resolve(process.cwd(), 'dist');
const compressibleExtensions = new Set([
  '.js',
  '.mjs',
  '.css',
  '.html',
  '.svg',
  '.json',
  '.wasm',
  '.glb',
  '.gltf',
  '.bin',
]);
const brotliPreferredExtensions = new Set([
  '.js',
  '.mjs',
  '.css',
  '.html',
  '.svg',
  '.json',
  '.wasm',
  '.glb',
  '.gltf',
  '.bin',
]);
const maxBrotliSourceBytes = 32 * 1024 * 1024;

async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return walk(fullPath);
    }
    return [fullPath];
  }));
  return files.flat();
}

async function writeIfSmaller(targetPath, content) {
  try {
    const current = await fs.stat(targetPath);
    if (current.size <= content.length) {
      return false;
    }
  } catch {
    // Missing output is expected on first build.
  }
  await fs.writeFile(targetPath, content);
  return true;
}

async function main() {
  const files = await walk(rootDir);
  let compressedCount = 0;

  for (const filePath of files) {
    const ext = path.extname(filePath).toLowerCase();
    if (!compressibleExtensions.has(ext)) {
      continue;
    }
    if (filePath.endsWith('.gz') || filePath.endsWith('.br')) {
      continue;
    }

    const source = await fs.readFile(filePath);
    if (source.length < 1024) {
      continue;
    }

    const gzipped = await gzipAsync(source, { level: 9 });
    let brotlied = null;
    if (brotliPreferredExtensions.has(ext) || source.length <= maxBrotliSourceBytes) {
      brotlied = await brotliAsync(source, {
        params: {
          [constants.BROTLI_PARAM_QUALITY]: 5,
        },
      });
    }

    const wroteGzip = await writeIfSmaller(`${filePath}.gz`, gzipped);
    const wroteBrotli = brotlied ? await writeIfSmaller(`${filePath}.br`, brotlied) : false;
    if (wroteGzip || wroteBrotli) {
      compressedCount += 1;
    }
  }

  console.log(`precompress-dist: wrote compressed variants for ${compressedCount} files`);
}

main().catch((error) => {
  console.error('precompress-dist failed');
  console.error(error);
  process.exit(1);
});
