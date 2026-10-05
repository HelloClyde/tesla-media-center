import axios, { type AxiosRequestConfig } from 'axios';
import { decodeMapTile, type RawMapTile } from './amapBmdDecode';

const MIME = 'application/vnd.tmc.amap-bmd';
const FIELDS = ['collectionBmd', 'surfacesBmd', 'transitBmd', 'placeLabelsBmd', 'buildingsBmd'] as const;
const MAGIC = 'TMCBMD1!';
const MAX_BYTES = 26 * 1024 * 1024;

export class InvalidBmdResponseError extends Error {}
export class TransientBmdDecodeError extends Error {}

/** A transient upstream/network failure must not disable compact BMD for the page. */
export function rawBmdUnsupported(error: unknown): boolean {
  if (error instanceof InvalidBmdResponseError) return true;
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status === 404 || status === 405 || status === 406 || status === 415 || status === 501;
}

export function rawBmdDecodeUnsupported(error: unknown): boolean {
  return !(error instanceof TransientBmdDecodeError);
}

/** Parsed tile sections share the response buffer. Transfer it to the decode
 * worker once instead of copying the full batch for every tile. */
export function transferableBmdBuffers(tiles: RawMapTile[]): ArrayBuffer[] {
  const buffers = new Set<ArrayBuffer>();
  for (const tile of tiles) for (const name of FIELDS) {
    const value = tile[name];
    if (value instanceof Uint8Array && value.buffer instanceof ArrayBuffer)
      buffers.add(value.buffer);
  }
  return [...buffers];
}

/** Older car browsers may lack module Workers. Keep compact BMD delivery and
 * decode in place instead of forcing a much larger JSON map response. */
export function decodeBmdOnMainThread(tiles: RawMapTile[], paints: Record<string, Record<string, any[]>>) {
  return tiles.map(tile => {
    if (tile.error) return tile;
    const alreadyDecoded = !FIELDS.some(name => tile[name]) &&
      ('collection' in tile || 'surfaces' in tile || 'buildings' in tile);
    return alreadyDecoded ? tile : decodeMapTile(tile, paints);
  });
}

export function parseBmdBatch(source: ArrayBuffer | Uint8Array): {tiles: RawMapTile[]; paints: Record<string, Record<string, any[]>>} {
  const bytes = ArrayBuffer.isView(source)
    ? new Uint8Array(source.buffer,source.byteOffset,source.byteLength) : new Uint8Array(source);
  if (bytes.byteLength < 12 || bytes.byteLength > MAX_BYTES ||
      String.fromCharCode(...bytes.subarray(0, 8)) !== MAGIC) throw new Error('invalid BMD batch');
  const length = new DataView(bytes.buffer, bytes.byteOffset + 8, 4).getUint32(0, true);
  if (length > 2 * 1024 * 1024 || 12 + length > bytes.byteLength) throw new Error('invalid BMD manifest size');
  const manifest = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes.subarray(12,12+length)));
  if (manifest.version !== 1 || !Array.isArray(manifest.tiles) || manifest.tiles.length > 24 ||
      !manifest.paints || typeof manifest.paints !== 'object') throw new Error('invalid BMD manifest');
  const body = bytes.subarray(12+length), tiles: RawMapTile[] = [];
  let cursor = 0;
  for (const row of manifest.tiles) {
    if (!Number.isInteger(row.level) || !Number.isInteger(row.x) || !Number.isInteger(row.y) ||
        !row.bmd || typeof row.bmd !== 'object') throw new Error('invalid BMD tile');
    const {bmd,...metadata} = row;
    const tile = metadata as RawMapTile;
    for (const name of FIELDS) {
      if (!(name in bmd)) continue;
      const span = bmd[name];
      if (!Array.isArray(span) || span.length !== 2 || !Number.isInteger(span[0]) ||
          !Number.isInteger(span[1]) || span[0] !== cursor || span[1] < 1 || span[1] > 16*1024*1024 ||
          cursor + span[1] > body.byteLength) throw new Error('invalid BMD span');
      tile[name] = body.subarray(cursor,cursor+span[1]);
      cursor += span[1];
    }
    if (Object.keys(bmd).some(name => !(FIELDS as readonly string[]).includes(name))) throw new Error('unknown BMD layer');
    tiles.push(tile);
  }
  if (cursor !== body.byteLength) throw new Error('unconsumed BMD data');
  return {tiles,paints:manifest.paints};
}

export async function postMapTiles(path: string, payload: unknown, options: AxiosRequestConfig = {}) {
  if (path !== '/api/amap-app/map/bmd' && path !== '/api/amap-app/map/bmd/prefetch')
    return axios.post(path,payload,options);
  const response = await axios.post(path,payload,{
    ...options,responseType:'arraybuffer',headers:{...options.headers,Accept:MIME},
  });
  if (ArrayBuffer.isView(response.data) || Object.prototype.toString.call(response.data) === '[object ArrayBuffer]') {
    const bytes = ArrayBuffer.isView(response.data)
      ? new Uint8Array(response.data.buffer,response.data.byteOffset,response.data.byteLength)
      : new Uint8Array(response.data);
    if (bytes.byteLength === 0 && (response.status === 202 || response.status === 204)) {
      response.data = undefined;
      return response;
    }
    const binary = bytes.byteLength >= 8 && String.fromCharCode(...bytes.subarray(0,8)) === MAGIC;
    try {
      response.data = binary ? {status:'ok',data:parseBmdBatch(bytes)}
        : JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes));
    } catch {
      throw new InvalidBmdResponseError('invalid BMD endpoint response');
    }
  }
  return response;
}
