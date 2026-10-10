export type EncodedMapTile = {payload: string | Uint8Array; encoding: 'json' | 'gzip'; bytes: number};
export async function encodeMapTile(tile: unknown): Promise<EncodedMapTile> {
  const json = JSON.stringify(tile);
  if (typeof CompressionStream !== 'undefined') try {
    const stream = new Blob([json]).stream().pipeThrough(new CompressionStream('gzip'));
    const payload = new Uint8Array(await new Response(stream).arrayBuffer());
    return {payload, encoding: 'gzip', bytes: payload.byteLength};
  } catch { /* Older browsers retain the JSON cache representation. */ }
  return {payload: json, encoding: 'json', bytes: new TextEncoder().encode(json).length};
}
export async function decodeCachedMapTile(row: {payload: string | Uint8Array; encoding: string}) {
  if (row.encoding !== 'json' && row.encoding !== 'gzip') throw new Error('invalid tile cache encoding');
  const text = row.encoding === 'gzip'
    ? await new Response(new Blob([new Uint8Array(row.payload as Uint8Array)]).stream()
      .pipeThrough(new DecompressionStream('gzip'))).text() : row.payload as string;
  return JSON.parse(text);
}
