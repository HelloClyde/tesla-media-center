// Browser decoder for the bounded BMD sections used by the 2D map. The server
// unwraps zstd/LZ4; geometry, names and paint bindings are decoded on device.
type Grid = [number, number, number];
type Paints = Record<string, Record<string, any[]>>;
type Entry = { kind: number; offset: number; size: number };
const LIMIT = 16 * 1024 * 1024;
const utf8 = new TextDecoder('utf-8', { fatal: true });

export function base64Bytes(value: string): Uint8Array {
  if (value.length > LIMIT * 4 / 3 + 8) throw new Error('BMD base64 too large');
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

class Reader {
  offset = 0;
  bit = 0;
  constructor(readonly data: Uint8Array) {}
  integer(size: number): number {
    if (size < 1 || size > 4 || this.offset + size > this.data.length) throw new Error('truncated BMD integer');
    let value = 0;
    for (let i = 0; i < size; i++) value += this.data[this.offset++] * 2 ** (i * 8);
    return value;
  }
  variable(): number {
    let value = 0;
    for (let i = 0; i < 8; i++) {
      const byte = this.integer(1);
      value += (byte & 127) * 2 ** (7 * i);
      if (byte < 128 && Number.isSafeInteger(value)) return value;
    }
    throw new Error('invalid BMD varint');
  }
  beginBits() { this.bit = this.offset * 8; }
  bits(width: number, signed = false): number {
    if (width < 0 || width > 31 || this.bit + width > this.data.length * 8) throw new Error('invalid BMD bits');
    let value = 0;
    for (let i = 0; i < width; i++) {
      value = value * 2 + ((this.data[this.bit >> 3] >> (7 - (this.bit & 7))) & 1);
      this.bit++;
    }
    if (signed && width && value >= 2 ** (width - 1)) value -= 2 ** width;
    return value;
  }
  endBits() { this.offset = Math.ceil(this.bit / 8); }
  done() { if (this.offset !== this.data.length) throw new Error('unconsumed BMD bytes'); }
}

function crc32(data: Uint8Array): number {
  let crc = -1;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ -1) >>> 0;
}

function sections(data: Uint8Array): Map<number, Uint8Array> {
  if (data.length < 11 || data.length > LIMIT) throw new Error('invalid BMD size');
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  if (view.getUint32(0, true) !== crc32(data.subarray(4)) || data[4] >= 16 || view.getUint32(5, true) !== 8000)
    throw new Error('invalid BMD header');
  const count = view.getUint16(9, true);
  if (!count || count > 256) throw new Error('invalid BMD section count');
  const reader = new Reader(data); reader.offset = 11;
  const entries: Entry[] = [], kinds = new Set<number>();
  for (let i = 0; i < count; i++) {
    const kind = reader.integer(2), offset = reader.variable(), size = reader.variable();
    reader.variable();
    if (kinds.has(kind)) throw new Error('duplicate BMD section');
    kinds.add(kind); entries.push({ kind, offset, size });
  }
  const base = reader.offset, result = new Map<number, Uint8Array>();
  let end = 0;
  for (const entry of entries.sort((a, b) => a.offset - b.offset)) {
    if (entry.offset < end || entry.offset + entry.size > data.length - base) throw new Error('invalid BMD section range');
    result.set(entry.kind, data.subarray(base + entry.offset, base + entry.offset + entry.size));
    end = entry.offset + entry.size;
  }
  return result;
}

function names(raw?: Uint8Array): Record<string, string>[] {
  if (!raw) return [];
  const r = new Reader(raw), languageCount = r.variable();
  if (languageCount < 1 || languageCount > 64) throw new Error('invalid BMD languages');
  r.beginBits(); const width = r.bits(5), languages: string[] = [];
  for (let i = 0; i < languageCount; i++) {
    const length = r.bits(width);
    if (length < 1 || length > 64) throw new Error('invalid BMD language length');
    languages.push(utf8.decode(Uint8Array.from({ length }, () => r.bits(8))));
  }
  r.endBits();
  const count = r.variable();
  if (count > 100000) throw new Error('too many BMD names');
  const result: Record<string, string>[] = [];
  for (let i = 0; i < count; i++) {
    const variants = r.integer(1);
    if (variants > languages.length) throw new Error('invalid BMD variants');
    r.beginBits(); const textWidth = r.bits(5); r.endBits();
    const entry: Record<string, string> = {};
    for (let j = 0; j < variants; j++) {
      const language = r.variable();
      if (language >= languages.length || languages[language] in entry) throw new Error('invalid BMD name language');
      r.beginBits(); const length = r.bits(textWidth); r.endBits();
      if (length > 4096 || r.offset + length > raw.length) throw new Error('invalid BMD name length');
      const value = utf8.decode(raw.subarray(r.offset, r.offset + length)); r.offset += length;
      r.beginBits(); const alternate = r.bits(1), phonetic = r.bits(1); r.endBits();
      for (const present of [alternate, phonetic]) if (present) {
        const count = r.variable(); if (count > 4096) throw new Error('invalid BMD name annotation');
        r.beginBits(); const indexWidth = r.bits(5);
        for (let k = 0; k < count; k++) r.bits(indexWidth);
        r.endBits();
      }
      entry[languages[language]] = value;
    }
    result.push(entry);
  }
  r.done(); return result;
}

function label(table: Record<string, string>[], index: number | null): string {
  if (index === null) return '';
  if (index >= table.length) throw new Error('invalid BMD name index');
  return table[index]['zh-Hans'] ?? Object.values(table[index])[0] ?? '';
}

function geographic(point: number[], [level, x, y]: Grid, width = 13): number[] {
  if (![3, 6, 8, 10, 12, 14].includes(level) || ![11, 12, 13].includes(width)) throw new Error('invalid BMD grid');
  const extent = 2 ** (width - 1);
  if (point[0] < 0 || point[0] > extent || point[1] < 0 || point[1] > extent / 2) throw new Error('BMD point outside tile');
  const unit = 360 / 2 ** (level + width - 1);
  return [(x * extent + point[0]) * unit - 180, 90 - (y + 1) * 180 / 2 ** level + point[1] * unit];
}

function bindings(raw: Uint8Array | undefined, featureCount: number): Map<number, string> {
  const result = new Map<number, string>();
  if (!raw) return result;
  const directory = new Reader(raw), count = directory.variable();
  if (count < 1 || count > 32) throw new Error('invalid BMD attribute count');
  const entries: [number, number][] = [];
  for (let i = 0; i < count; i++) entries.push([directory.variable(), directory.variable()]);
  const start = directory.offset, offsets = entries.map(e => e[1]);
  if (new Set(entries.map(e => e[0])).size !== count || new Set(offsets).size !== count ||
      offsets.some(o => o >= raw.length - start)) throw new Error('invalid BMD attribute directory');
  const selected = entries.find(e => e[0] === 1);
  if (!selected) return result;
  const end = Math.min(...offsets.filter(o => o > selected[1]), raw.length - start);
  const r = new Reader(raw.subarray(start + selected[1], start + end));
  const mode = r.integer(1), rows = r.variable();
  if (![1, 2].includes(mode) || rows > featureCount) throw new Error('invalid BMD bindings');
  for (let i = 0; i < rows; i++) {
    const size = mode === 2 ? r.variable() : 1;
    if (size > featureCount || result.size + size > featureCount) throw new Error('too many BMD bindings');
    const indexes = Array.from({ length: size }, () => r.variable());
    const subtype = r.integer(4), category = r.integer(4);
    for (const index of indexes) {
      if (index >= featureCount || result.has(index)) throw new Error('invalid BMD binding index');
      result.set(index, `${category}/${subtype}`);
    }
  }
  r.done(); return result;
}

function roads(parts: Map<number, Uint8Array>, grid: Grid) {
  const raw = parts.get(30);
  if (!raw) return { type: 'FeatureCollection', features: [] };
  const r = new Reader(raw), styleCount = r.variable();
  if (styleCount > 4096) throw new Error('too many BMD road styles');
  const styles = Array.from({ length: styleCount }, () => r.integer(2));
  const groups = r.variable(); if (groups > 10000) throw new Error('too many BMD road groups');
  const table = names(parts.get(10)), features: any[] = [];
  let pointTotal = 0;
  for (let group = 0; group < groups; group++) {
    r.integer(4); r.integer(2); const width = r.integer(1), count = r.variable();
    if (width < 1 || width > 24 || count + features.length > 100000) throw new Error('invalid BMD road group');
    for (let i = 0; i < count; i++) {
      const styleIndex = r.variable(); if (styleIndex >= styles.length) throw new Error('invalid BMD road style');
      const flags = r.integer(1), name = flags & 1 ? r.variable() : null;
      if (flags & 2) { r.variable(); r.variable(); }
      if (flags & 32 && !(flags & 16)) r.variable();
      r.integer(1); r.integer(1);
      // Feature IDs are 64-bit and do not affect this renderer.
      r.integer(4); r.integer(4);
      const pointCount = r.variable(); pointTotal += pointCount;
      if (pointCount < 1 || pointCount > 100000 || pointTotal > 500000) throw new Error('invalid BMD road points');
      r.beginBits(); let x = r.bits(width), y = r.bits(width);
      const deltaWidth = pointCount > 1 ? r.bits(5) : 0; r.endBits();
      const coordinates = [geographic([x, y], grid, width)];
      r.beginBits();
      for (let j = 1; j < pointCount; j++) {
        x += r.bits(deltaWidth, true); y += r.bits(deltaWidth, true);
        if (flags & 4) r.bits(1);
        coordinates.push(geographic([x, y], grid, width));
      }
      r.endBits();
      if (r.variable() !== 0) throw new Error('unsupported BMD geometry suffix');
      features.push({ type: 'Feature', properties: { name: label(table, name), style: styles[styleIndex] },
        geometry: { type: 'LineString', coordinates } });
    }
  }
  r.done(); return { type: 'FeatureCollection', features };
}

function surfaces(parts: Map<number, Uint8Array>, grid: Grid, paints: Paints): any[] {
  const raw = parts.get(40); if (!raw) return [];
  const r = new Reader(raw), styleCount = r.variable();
  if (styleCount > 4096) throw new Error('too many BMD surface styles');
  const styles = Array.from({ length: styleCount }, () => r.integer(2));
  const groups = r.variable(); if (groups > 10000) throw new Error('too many BMD surface groups');
  const features: { style: number; rings: number[][][] }[] = [];
  let ringTotal = 0, pointTotal = 0;
  for (let group = 0; group < groups; group++) {
    r.integer(4); r.integer(2); const width = r.integer(1), count = r.variable();
    if (width < 1 || width > 24 || count + features.length > 100000) throw new Error('invalid BMD surface group');
    for (let i = 0; i < count; i++) {
      const styleIndex = r.variable(); if (styleIndex >= styles.length) throw new Error('invalid BMD surface style');
      const ringCount = r.variable(); ringTotal += ringCount;
      if (ringCount > 10000 || ringTotal > 100000) throw new Error('too many BMD rings');
      const rings: number[][][] = [];
      for (let j = 0; j < ringCount; j++) {
        const pointCount = r.variable(); pointTotal += pointCount;
        if (pointCount < 1 || pointCount > 100000 || pointTotal > 500000) throw new Error('invalid BMD ring');
        r.beginBits(); let x = r.bits(width), y = r.bits(width);
        r.bits(1); r.bits(1); const deltaWidth = pointCount > 1 ? r.bits(5) : 0; r.endBits();
        const ring = [[x, y]];
        r.beginBits();
        for (let k = 1; k < pointCount; k++) {
          x += r.bits(deltaWidth, true); y += r.bits(deltaWidth, true); r.bits(1);
          ring.push([x, y]);
        }
        r.endBits(); rings.push(ring);
      }
      features.push({ style: styles[styleIndex], rings: width === 12 || width === 13
        ? rings.filter(ring => ring.length >= 3).map(ring => ring.map(([x, y]) => geographic([x * 2 ** (13 - width), y * 2 ** (13 - width)], grid))) : [] });
    }
  }
  r.done();
  const keys = bindings(parts.get(41), features.length), result: any[] = [];
  features.forEach((feature, index) => {
    const key = keys.get(index); if (!key || !feature.rings.length) return;
    const colors: Record<string, any[]> = {};
    for (const [theme, lookup] of Object.entries(paints)) if (lookup[key]) colors[theme] = lookup[key];
    if (Object.keys(colors).length) result.push({ rings: feature.rings, paints: colors,
      minZoom: feature.style & 31, maxZoom: (feature.style >> 5) & 31 });
  });
  return result;
}

function points(parts: Map<number, Uint8Array>, grid: Grid, places: boolean): any[] {
  const raw = parts.get(20); if (!raw) return [];
  const r = new Reader(raw), styleCount = r.variable();
  if (styleCount > 4096) throw new Error('too many BMD point styles');
  const styles = Array.from({ length: styleCount }, () => r.integer(2));
  const groups = r.variable(); if (groups > 10000) throw new Error('too many BMD point groups');
  const found: { point: number[]; name: number | null; style: number; width: number }[] = [];
  for (let group = 0; group < groups; group++) {
    r.integer(4); r.integer(2); const width = r.integer(1), count = r.variable();
    if (![11, 12, 13].includes(width) || count + found.length > 100000) throw new Error('invalid BMD point group');
    for (let i = 0; i < count; i++) {
      const styleIndex = r.variable(); if (styleIndex >= styles.length) throw new Error('invalid BMD point style');
      r.integer(4); r.integer(4); const flags = r.integer(1);
      r.integer(4); r.integer(4); const name = flags & 1 ? r.variable() : null;
      r.beginBits(); const point = [r.bits(width), r.bits(width)]; r.endBits();
      found.push({ point, name, style: styles[styleIndex], width });
    }
  }
  r.done();
  const table = names(parts.get(10)), keys = places ? bindings(parts.get(21), found.length) : new Map<number, string>();
  const result: any[] = [];
  found.forEach((feature, index) => {
    const key = keys.get(index), subtype = Number(key?.split('/')[1]);
    if (places && (!key?.startsWith('10002/') || ![5, 6, 22, 30, 31, 32].includes(subtype))) return;
    if (feature.name === null) return;
    const name = label(table, feature.name); if (!name) return;
    result.push({ point: geographic(feature.point, grid, feature.width), name,
      minZoom: feature.style & 31, maxZoom: (feature.style >> 5) & 31,
      ...(places ? { kind: subtype === 22 ? 'province' : 'city',
        priority: subtype === 30 ? 0 : subtype === 22 ? 1 : subtype === 31 || subtype === 32 ? 2 : 3 } : {}) });
  });
  return result;
}

export type RawMapTile = { level: number; x: number; y: number; collectionBmd?: string; surfacesBmd?: string;
  transitBmd?: string; placeLabelsBmd?: string; missingLayers?: string[]; error?: string };

export function decodeMapTile(tile: RawMapTile, paints: Paints) {
  const grid: Grid = [tile.level, tile.x, tile.y];
  const part = (value?: string) => value ? sections(base64Bytes(value)) : new Map<number, Uint8Array>();
  return { level: tile.level, x: tile.x, y: tile.y,
    collection: roads(part(tile.collectionBmd), grid),
    surfaces: surfaces(part(tile.surfacesBmd), grid, paints),
    transit: points(part(tile.transitBmd), grid, false),
    placeLabels: points(part(tile.placeLabelsBmd), grid, true),
    missingLayers: tile.missingLayers, error: tile.error };
}
