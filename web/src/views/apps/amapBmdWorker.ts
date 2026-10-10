import { decodeMapTile, type RawMapTile } from './amapBmdDecode';
import {encodeMapTile, decodeCachedMapTile} from './amapTileCodec';
import {prepareMapGeometryBounds} from './amapGeometryBounds';
const scope = self as unknown as {
  postMessage: (message: unknown, transfer?: Transferable[]) => void;
  onmessage: (event: MessageEvent<any>) => void;
};

// Let the caller keep the raw response until this module has actually loaded.
// A blocked module Worker can then fall back locally without a second download.
scope.postMessage({ ready: true });

let paused = false, chain = Promise.resolve();
const replies: {id: number; value?: any; error?: string}[] = [];
const granted = new Set<number>();
let sourceId = 0;
const sources = new Map<string, unknown>();
function decodeTiles(payload: {tiles: RawMapTile[]; paints: any; epoch: number}) {
  const tiles = payload.tiles.map(tile => tile.error ? tile : prepareMapGeometryBounds(decodeMapTile(tile, payload.paints)));
  const ids = tiles.map(tile => {
    const id = `${payload.epoch}/${++sourceId}`; sources.set(id, tile);
    while (sources.size > 8) sources.delete(sources.keys().next().value!);
    return id;
  });
  return {tiles, sources: ids};
}
async function encode(payload: {source?: string; tile?: unknown}) {
  if (payload.source !== undefined) {
    if (!sources.has(payload.source)) return {missingSource: true};
    try {return await encodeMapTile(sources.get(payload.source));}
    finally {sources.delete(payload.source);}
  }
  return encodeMapTile(payload.tile);
}
function flush() {
  if (paused) return;
  for (let i = replies.length - 1; i >= 0; i--) {
    const reply = replies[i];
    if (!granted.delete(reply.id)) continue;
    replies.splice(i, 1);
    const transfers = reply.value?.payload instanceof Uint8Array ? [reply.value.payload.buffer] : [];
    scope.postMessage(reply, transfers);
  }
}
scope.onmessage = event => {
  if (typeof event.data.paused === 'boolean') { paused = event.data.paused; flush(); return; }
  if (typeof event.data.deliver === 'number') { granted.add(event.data.deliver); flush(); return; }
  const {id, operation, payload} = event.data;
  chain = chain.then(async () => {
    try {
      const value = operation === 'bmd'
        ? decodeTiles(payload)
        : operation === 'encode' ? await encode(payload)
        : operation === 'decode' ? prepareMapGeometryBounds(await decodeCachedMapTile(payload)) : undefined;
      if (value === undefined) throw new Error('unknown map worker operation');
      replies.push({id, value});
    } catch (error) { replies.push({id, error: error instanceof Error ? error.message : 'map data failed'}); }
    // Decoding can occupy this thread before a pause message is processed.
    // Require a fresh main-thread grant after completion rather than posting
    // a large structured clone while that pause is still queued.
    scope.postMessage({id, complete: true});
  });
};
