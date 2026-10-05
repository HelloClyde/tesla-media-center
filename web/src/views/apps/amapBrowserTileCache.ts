/** Per-device cache for decoded App tiles. The server remains authoritative. */
export type CachedMapTile = { level: number; x: number; y: number; error?: string; missingLayers?: string[]; [key: string]: unknown };
export type CacheKind = 'rendered' | 'full' | 'lanes';

const NAME = 'tmc-amap-tiles-v1';
const STORE = 'tiles';
const SETTINGS = 'tmc-amap-browser-cache-settings-v1';
const DEFAULT_TTL_HOURS = 168;
const DEFAULT_MAX_MB = 96;
const MAX_TILE_BYTES = 12 * 1024 * 1024;
type Row = { key: string; fetchedAt: number; touchedAt: number; bytes: number; payload: string | Uint8Array; encoding: 'json' | 'gzip' | 'glb' };
const MAX_MODEL_BYTES = 16 * 1024 * 1024;
const modelKey = (name: string) => /^[0-9]{1,19}-[0-9a-f]{12}\.glb$/.test(name) ? `model/${name}` : undefined;
let opening: Promise<IDBDatabase | undefined> | undefined;
function limits() {
  try {
    const stored=JSON.parse(localStorage.getItem(SETTINGS) || '{}');
    const ttlHours=Number.isInteger(stored.ttlHours) && stored.ttlHours>=1 && stored.ttlHours<=2160
      ? stored.ttlHours : DEFAULT_TTL_HOURS;
    const maxMB=Number.isInteger(stored.maxMB) && stored.maxMB>=16 && stored.maxMB<=512
      ? stored.maxMB : DEFAULT_MAX_MB;
    return {ttlHours,maxMB};
  } catch {return {ttlHours:DEFAULT_TTL_HOURS,maxMB:DEFAULT_MAX_MB};}
}
export function browserMapTileTtlMs() {return limits().ttlHours*3600000;}

function key(kind: CacheKind, level: number, x: number, y: number) {
  return `${kind === 'full' && level === 15 ? 'full-buildings-v8' : kind === 'lanes' ? 'lanes-v2' : kind}/${level}/${x}/${y}`;
}
function open() {
  if (opening) return opening;
  opening = new Promise(resolve => {
    if (typeof indexedDB === 'undefined') { resolve(undefined); return; }
    try {
      const request = indexedDB.open(NAME, 1);
      let settled = false;
      const finish = (db?: IDBDatabase) => {
        if (settled) { db?.close(); return; }
        settled = true;
        clearTimeout(timer);
        if (!db) opening = undefined;
        resolve(db);
      };
      // An unavailable or blocked store must never stall navigation startup.
      const timer = setTimeout(() => finish(), 1000);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'key' });
      request.onsuccess = () => finish(request.result);
      request.onerror = () => finish();
      request.onblocked = () => finish();
    } catch { opening = undefined; resolve(undefined); }
  });
  return opening;
}
function complete(tx: IDBTransaction) {
  return new Promise<void>((resolve,reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = tx.onerror = () => reject(tx.error || new Error('map cache transaction failed'));
  });
}
async function encode(tile: CachedMapTile) {
  const json = JSON.stringify(tile);
  if (typeof CompressionStream === 'undefined') return { payload: json, encoding: 'json' as const, bytes: new TextEncoder().encode(json).length };
  try {
    const stream = new Blob([json]).stream().pipeThrough(new CompressionStream('gzip'));
    const payload = new Uint8Array(await new Response(stream).arrayBuffer());
    return { payload, encoding: 'gzip' as const, bytes: payload.byteLength };
  } catch { return { payload: json, encoding: 'json' as const, bytes: new TextEncoder().encode(json).length }; }
}
async function decode(row: Row): Promise<CachedMapTile> {
  if (row.encoding === 'glb') throw new Error('binary model is not a map tile');
  const text = row.encoding === 'gzip'
    ? await new Response(new Blob([new Uint8Array(row.payload as Uint8Array)]).stream()
      .pipeThrough(new DecompressionStream('gzip'))).text()
    : row.payload as string;
  return JSON.parse(text) as CachedMapTile;
}

/** Landmark GLBs share the tile budget and clear-cache control. */
export async function readMapModel(name: string): Promise<ArrayBuffer | undefined> {
  const id = modelKey(name), db = await open();
  if (!id || !db) return undefined;
  try {
    const tx = db.transaction(STORE, 'readwrite'), store = tx.objectStore(STORE), done = complete(tx);
    const request = store.get(id);
    let data: ArrayBuffer | undefined;
    request.onsuccess = () => {
      const row = request.result as Row | undefined;
      if (!row) return;
      if (Date.now() - row.fetchedAt > browserMapTileTtlMs() || row.encoding !== 'glb' ||
          !(row.payload instanceof Uint8Array) || row.bytes !== row.payload.byteLength ||
          row.bytes < 20 || row.bytes > MAX_MODEL_BYTES) {
        store.delete(id); return;
      }
      row.touchedAt = Date.now(); store.put(row);
      data = row.payload.slice().buffer as ArrayBuffer;
    };
    await done;
    return data;
  } catch { return undefined; }
}

export async function storeMapModel(name: string, buffer: ArrayBuffer) {
  const id = modelKey(name), db = await open();
  if (!id || !db || !(buffer instanceof ArrayBuffer) || buffer.byteLength < 20 ||
      buffer.byteLength > MAX_MODEL_BYTES) return;
  const now = Date.now(), payload = new Uint8Array(buffer).slice();
  try {
    const tx = db.transaction(STORE, 'readwrite'), done = complete(tx);
    tx.objectStore(STORE).put({key:id, fetchedAt:now, touchedAt:now,
                              bytes:payload.byteLength, payload, encoding:'glb'} satisfies Row);
    await done;
    await prune(db);
  } catch { /* Model rendering remains available without persistent storage. */ }
}

export async function forgetMapModel(name: string) {
  const id = modelKey(name), db = await open();
  if (!id || !db) return;
  try {
    const tx = db.transaction(STORE, 'readwrite'), done = complete(tx);
    tx.objectStore(STORE).delete(id);
    await done;
  } catch { /* A bad row will still expire under the normal TTL. */ }
}

export async function readMapTiles(kind: CacheKind, tiles: number[][]) {
  const result = new Map<string,{ tile: CachedMapTile; at: number }>();
  const db = await open();
  if (!db || !tiles.length) return result;
  const rows: Row[] = [];
  try {
    const tx = db.transaction(STORE,'readwrite'), store = tx.objectStore(STORE), done = complete(tx);
    const now = Date.now(), ttl=limits().ttlHours*3600000;
    for (const [level,x,y] of tiles) {
      const request = store.get(key(kind,level,x,y));
      request.onsuccess = () => {
        const row = request.result as Row | undefined;
        if (!row) return;
        if (now - row.fetchedAt > ttl) { store.delete(row.key); return; }
        row.touchedAt = now; store.put(row); rows.push(row);
      };
    }
    await done;
    for (const row of rows) {
      try {
        const tile = await decode(row);
        if (tile.error || tile.missingLayers?.length || row.key !== key(kind,tile.level,tile.x,tile.y)) continue;
        result.set(`${tile.level}/${tile.x}/${tile.y}`,{tile,at:row.fetchedAt});
      } catch { /* A damaged entry is a miss; the next request replaces it. */ }
    }
  } catch { /* Private mode or full storage: use the existing in-memory map. */ }
  return result;
}

async function prune(db: IDBDatabase) {
  const {ttlHours,maxMB}=limits(), ttl=ttlHours*3600000, maxBytes=maxMB*1048576;
  const metadata: {key:string;bytes:number;fetchedAt:number;touchedAt:number}[] = [];
  const tx=db.transaction(STORE,'readonly'), request=tx.objectStore(STORE).openCursor(), done=complete(tx);
  request.onsuccess=()=>{
    const cursor=request.result;
    if(!cursor) return;
    const row=cursor.value as Row;
    metadata.push({key:row.key,bytes:row.bytes,fetchedAt:row.fetchedAt,touchedAt:row.touchedAt});
    cursor.continue();
  };
  await done;
  const now=Date.now(), expired=metadata.filter(row=>now-row.fetchedAt>ttl);
  const live=metadata.filter(row=>now-row.fetchedAt<=ttl).sort((a,b)=>a.touchedAt-b.touchedAt);
  let bytes=live.reduce((sum,row)=>sum+row.bytes,0);
  const remove=expired.map(row=>row.key);
  for(const row of live) if(bytes>maxBytes) {remove.push(row.key);bytes-=row.bytes;}
  if(!remove.length) return;
  const deletion=db.transaction(STORE,'readwrite'), store=deletion.objectStore(STORE), finished=complete(deletion);
  remove.forEach(value=>store.delete(value));
  await finished;
}

export async function storeMapTiles(kind: CacheKind, tiles: CachedMapTile[]) {
  const db=await open();
  if(!db || !tiles.length) return;
  const now=Date.now(), rows:Row[]=[];
  for(const tile of tiles) {
    if(tile.error || tile.missingLayers?.length || !Number.isInteger(tile.level) || !Number.isInteger(tile.x) || !Number.isInteger(tile.y)) continue;
    const encoded=await encode(tile);
    if(encoded.bytes>MAX_TILE_BYTES) continue;
    rows.push({key:key(kind,tile.level,tile.x,tile.y),fetchedAt:now,touchedAt:now,...encoded});
  }
  if(!rows.length) return;
  try {
    const tx=db.transaction(STORE,'readwrite'), store=tx.objectStore(STORE), done=complete(tx);
    rows.forEach(row=>store.put(row));
    await done;
    await prune(db);
  } catch { /* Failed persistence must not interrupt live navigation. */ }
}

export async function browserMapCacheStats() {
  const {ttlHours,maxMB}=limits();
  const db=await open();
  if(!db) return {available:false,count:0,usedBytes:0,ttlHours,maxMB};
  let count=0,usedBytes=0;
  try {
    const tx=db.transaction(STORE,'readonly'), request=tx.objectStore(STORE).openCursor(), done=complete(tx);
    request.onsuccess=()=>{const cursor=request.result;if(!cursor)return;const row=cursor.value as Row;count++;usedBytes+=row.bytes;cursor.continue();};
    await done;
    return {available:true,count,usedBytes,ttlHours,maxMB};
  } catch {return {available:false,count:0,usedBytes:0,ttlHours,maxMB};}
}

export async function updateBrowserMapCacheConfig(ttlHours:number,maxMB:number) {
  if(!Number.isInteger(ttlHours) || ttlHours<1 || ttlHours>2160 ||
      !Number.isInteger(maxMB) || maxMB<16 || maxMB>512) return false;
  try {localStorage.setItem(SETTINGS,JSON.stringify({ttlHours,maxMB}));}
  catch {return false;}
  const db=await open();
  if(db) try {await prune(db);} catch { /* A new limit still applies to future reads/writes. */ }
  return true;
}

export async function clearBrowserMapCache() {
  const db=await open();
  if(!db) return false;
  try {const tx=db.transaction(STORE,'readwrite'), done=complete(tx);tx.objectStore(STORE).clear();await done;return true;}
  catch {return false;}
}
