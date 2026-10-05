import { decodeMapTile, type RawMapTile } from './amapBmdDecode';

// Let the caller keep the raw response until this module has actually loaded.
// A blocked module Worker can then fall back locally without a second download.
self.postMessage({ ready: true });

self.onmessage = (event: MessageEvent<{ tiles: RawMapTile[]; paints: Record<string, Record<string, any[]>> }>) => {
  try {
    const tiles = event.data.tiles.map(tile => tile.error ? tile : decodeMapTile(tile, event.data.paints));
    self.postMessage({ tiles });
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : 'BMD decode failed' });
  }
};
