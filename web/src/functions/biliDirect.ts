import { createFile, BoxParser, type MP4BoxBuffer, type Sample } from 'mp4box';

export interface DirectTrack {
  urls: string[];
  codec: string;
  initialization: string;
  indexRange: string;
}
export interface DirectManifest {
  mode: 'dash-direct';
  duration: number;
  video: DirectTrack;
  audio: DirectTrack;
}
export interface Segment { start: number; end: number; time: number; duration: number }
export interface StreamChunk { data: Uint8Array; endTime: number }
export interface BrowserStreamSource {
  duration: number;
  startMs: number;
  chunks: AsyncIterable<StreamChunk>;
  signal: AbortSignal;
  cancel: () => void;
  probeTime: number;
}


const MAX_SEGMENT_BYTES = 32 * 1024 * 1024;
const FETCH_TIMEOUT = 15000;

export function parseRange(range: string): [number, number] {
  const match = /^(\d+)-(\d+)$/.exec(range);
  if (!match) throw new Error('无效的媒体分段范围');
  const start = Number(match[1]), end = Number(match[2]);
  if (!Number.isSafeInteger(end) || end < start || end - start >= MAX_SEGMENT_BYTES) {
    throw new Error('媒体分段过大或范围无效');
  }
  return [start, end];
}

/** Fail over only among URLs supplied by the playback API, never rewrite CDN hosts. */
export class RangeSource {
  private preferred = 0;
  constructor(private urls: string[], private signal: AbortSignal) {}

  async read(start: number, end: number): Promise<ArrayBuffer> {
    parseRange(`${start}-${end}`);
    let lastError: unknown;
    for (let attempt = 0; attempt < this.urls.length; attempt++) {
      this.signal.throwIfAborted();
      const index = (this.preferred + attempt) % this.urls.length;
      const controller = new AbortController();
      const abort = () => controller.abort();
      this.signal.addEventListener('abort', abort, { once: true });
      const timer = setTimeout(abort, FETCH_TIMEOUT);
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
        const response = await fetch(this.urls[index], {
          mode: 'cors', credentials: this.urls[index].startsWith('/api/bilibili/media-range/') ? 'same-origin' : 'omit', referrerPolicy: 'no-referrer',
          headers: { Range: `bytes=${start}-${end}` }, signal: controller.signal,
        });
        const contentRange = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range') || '');
        if (response.status !== 206 || !contentRange || Number(contentRange[1]) !== start
          || Number(contentRange[2]) !== end || Number(contentRange[3]) <= end || !response.body) {
          throw new Error(`源站拒绝分段读取（HTTP ${response.status}）`);
        }
        // Do not buffer an entire movie if a CDN ignores Range or sends too much data.
        const output = new Uint8Array(end - start + 1);
        reader = response.body.getReader();
        let offset = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (offset + value.length > output.length) throw new Error('源站返回了超出范围的数据');
          output.set(value, offset);
          offset += value.length;
        }
        if (offset !== output.length) throw new Error('媒体分段下载不完整');
        this.signal.throwIfAborted();
        this.preferred = index;
        return output.buffer;
      } catch (error) {
        lastError = error;
        this.signal.throwIfAborted();
      } finally {
        controller.abort();
        await reader?.cancel().catch(() => {});
        clearTimeout(timer);
        this.signal.removeEventListener('abort', abort);
      }
    }
    throw new Error(`源流直连失败，所有备用地址均不可用：${lastError instanceof Error ? lastError.message : '网络或跨域限制'}`);
  }
}

function mp4Buffer(data: ArrayBuffer, offset = 0): MP4BoxBuffer {
  return Object.assign(data, { fileStart: offset }) as MP4BoxBuffer;
}

export function parseIndex(data: ArrayBuffer, rangeStart: number): Segment[] {
  const file = createFile();
  file.appendBuffer(mp4Buffer(data));
  const index = file.sidx;
  if (!index || !index.timescale || !index.references.length) throw new Error('源流没有可用的 SIDX 索引');
  let start = rangeStart + (index.start || 0) + index.size + index.first_offset;
  let time = index.earliest_presentation_time / index.timescale;
  return index.references.map(ref => {
    if (ref.reference_type || !ref.referenced_size || !ref.subsegment_duration
      || ref.referenced_size > MAX_SEGMENT_BYTES || !Number.isSafeInteger(start)) {
      throw new Error('不支持该媒体分段索引');
    }
    const segment = { start, end: start + ref.referenced_size - 1, time, duration: ref.subsegment_duration / index.timescale };
    start += ref.referenced_size;
    time += segment.duration;
    return segment;
  });
}

export function segmentAt(segments: Segment[], seconds: number): number {
  let index = segments.findIndex(s => s.time > seconds);
  if (index < 0) index = segments.length;
  return Math.max(0, index - 1);
}

function parseInit(init: ArrayBuffer, kind: 'video' | 'audio') {
  const file = createFile();
  file.appendBuffer(mp4Buffer(init.slice(0)));
  const tracks = file.getInfo().tracks;
  const track = tracks.find(t => t.type === kind);
  if (!track) throw new Error(`源流缺少 ${kind} 轨道`);
  const entry = file.getTrackById(track.id).mdia.minf.stbl.stsd.entries[0];
  let config: Uint8Array;
  if (kind === 'video' && 'avcC' in entry && entry.avcC instanceof BoxParser.box.avcC) {
    const box = entry.avcC;
    config = new Uint8Array(init.slice(box.start! + (box.hdr_size || 8), box.start! + box.size));
  } else if (kind === 'audio' && 'esds' in entry && entry.esds instanceof BoxParser.box.esds) {
    const bytes = entry.esds.esd.findDescriptor(4)?.findDescriptor(5)?.data;
    if (!bytes?.length) throw new Error('源流缺少 AAC 解码配置');
    config = new Uint8Array(bytes);
  } else {
    throw new Error('直连播放仅支持 H264/AAC');
  }
  return { id: track.id, config };
}

/** A fresh parser for each fragment bounds memory even for multi-hour videos. */
export function extractSamples(init: ArrayBuffer, fragment: ArrayBuffer, trackId: number): Sample[] {
  const file = createFile();
  const samples: Sample[] = [];
  file.onError = () => { throw new Error('无法解析 DASH 媒体分段'); };
  file.onReady = () => {
    file.setExtractionOptions(trackId, null, { nbSamples: 10000 });
    file.start();
  };
  file.onSamples = (_id, _user, batch) => samples.push(...batch);
  file.appendBuffer(mp4Buffer(init.slice(0)));
  // DASH fragments use offsets relative to moof and may be relocated after init.
  file.appendBuffer(mp4Buffer(fragment, init.byteLength));
  file.flush();
  if (file.moofs.some(m => m.trafs.some(t => Boolean(t.tfhd.flags & 1)))) {
    throw new Error('不支持使用绝对偏移的 DASH 分段');
  }
  if (!samples.length || samples.some(s => !s.data || !s.timescale)) throw new Error('媒体分段没有可解码数据');
  return samples;
}

export function concat(parts: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.length; }
  return output;
}

function uint24(data: Uint8Array, offset: number, value: number) {
  data[offset] = value >>> 16; data[offset + 1] = value >>> 8; data[offset + 2] = value;
}

export function flvTag(type: number, timestamp: number, body: Uint8Array): Uint8Array {
  if (body.length > 0xffffff) throw new Error('媒体帧过大');
  const data = new Uint8Array(15 + body.length);
  data[0] = type;
  uint24(data, 1, body.length);
  const ms = Math.max(0, Math.round(timestamp));
  uint24(data, 4, ms); data[7] = ms >>> 24;
  data.set(body, 11);
  new DataView(data.buffer).setUint32(data.length - 4, body.length + 11);
  return data;
}

export function flvSample(sample: Sample, kind: 'video' | 'audio', baseMs: number): Uint8Array {
  const prefix = kind === 'video' ? new Uint8Array([sample.is_sync ? 0x17 : 0x27, 1, 0, 0, 0]) : new Uint8Array([0xaf, 1]);
  if (kind === 'video') uint24(prefix, 2, Math.round((sample.cts - sample.dts) * 1000 / sample.timescale));
  return flvTag(kind === 'video' ? 9 : 8, sample.dts * 1000 / sample.timescale - baseMs, concat([prefix, sample.data!]));
}

/**
 * The bundled decoder calls av_seek_frame after probing even on a non-seekable
 * FIFO. That discards the probed packets, including the opening keyframe. Give it
 * a disposable preroll first; decoder.js suppresses and subtracts that interval.
 * The real stream follows from its original keyframe without another download.
 */
export function probePrefix(firstChunk: Uint8Array): { data: Uint8Array; duration: number } {
  const tags: { data: Uint8Array; time: number }[] = [];
  const view = new DataView(firstChunk.buffer, firstChunk.byteOffset, firstChunk.byteLength);
  let pos = 13, lastTime = 0;
  while (pos < firstChunk.length) {
    const size = view.getUint32(pos) & 0xffffff;
    const time = (view.getUint32(pos + 4) >>> 8) + firstChunk[pos + 7] * 16777216;
    tags.push({ data: firstChunk.slice(pos, pos + size + 15), time });
    let presentationTime = time;
    if (firstChunk[pos] === 9 && firstChunk[pos + 12] === 1) {
      // Include B-frame composition offsets so no probe frame leaks into playback.
      const composition = (view.getInt32(pos + 13) >> 8);
      presentationTime += composition;
    }
    lastTime = Math.max(lastTime, time, presentationTime);
    pos += size + 15;
  }
  const parts = [firstChunk.slice(0, 13)];
  // At least six seconds of probe packets, even for a very short final segment.
  const span = Math.max(100, lastTime + 100);
  const repeats = Math.max(3, Math.ceil(6000 / span));
  if (13 + tags.reduce((n, t) => n + t.data.length, 0) * repeats > 4 * 1024 * 1024) {
    throw new Error('源流启动数据过大，请降低清晰度或使用兼容播放');
  }
  for (let i = 0; i < repeats; i++) {
    for (const tag of tags) {
      const data = tag.data.slice();
      const time = i * span + tag.time;
      uint24(data, 4, time); data[7] = time >>> 24;
      parts.push(data);
    }
  }
  return { data: concat(parts), duration: span * repeats / 1000 };
}

function shiftTimestamps(tags: Uint8Array, milliseconds: number): Uint8Array {
  const data = tags.slice();
  const view = new DataView(data.buffer);
  for (let pos = 0; pos < data.length;) {
    const size = view.getUint32(pos) & 0xffffff;
    const time = (view.getUint32(pos + 4) >>> 8) + data[pos + 7] * 16777216 + milliseconds;
    uint24(data, pos + 4, time); data[pos + 7] = time >>> 24;
    pos += size + 15;
  }
  return data;
}

async function loadTrack(track: DirectTrack, kind: 'video' | 'audio', signal: AbortSignal) {
  const source = new RangeSource(track.urls, signal);
  const init = await source.read(...parseRange(track.initialization));
  const [indexStart, indexEnd] = parseRange(track.indexRange);
  const index = await source.read(indexStart, indexEnd);
  return { source, init, ...parseInit(init, kind), segments: parseIndex(index, indexStart) };
}

async function* trackSamples(track: Awaited<ReturnType<typeof loadTrack>>, index: number, signal: AbortSignal) {
  // One segment of bounded lookahead per track hides network latency while
  // current samples are consumed. Settle errors immediately to avoid an
  // unhandled rejection when playback is paused or cancelled.
  const fetchSegment = (i: number) => {
    const segment = track.segments[i];
    return track.source.read(segment.start, segment.end).then(
      data => ({ data, error: undefined }), error => ({ data: undefined, error }));
  };
  let pending = fetchSegment(index);
  for (let i = index; i < track.segments.length; i++) {
    signal.throwIfAborted();
    const { data, error } = await pending;
    signal.throwIfAborted();
    if (!data) throw error;
    if (i + 1 < track.segments.length) pending = fetchSegment(i + 1);
    const samples = extractSamples(track.init, data, track.id);
    for (const sample of samples) { signal.throwIfAborted(); yield sample; }
  }
}

export async function createDirectSource(manifest: DirectManifest, startMs: number, controller: AbortController): Promise<BrowserStreamSource> {
  const { signal } = controller;
  try {
    if (!(manifest.duration > 0 && manifest.duration < 864000000)) throw new Error('不支持该视频时长');
    const [video, audio] = await Promise.all([
      loadTrack(manifest.video, 'video', signal), loadTrack(manifest.audio, 'audio', signal),
    ]);
    const videoIndex = segmentAt(video.segments, startMs / 1000);
    const videos = trackSamples(video, videoIndex, signal);
    const audios = trackSamples(audio, segmentAt(audio.segments, video.segments[videoIndex].time), signal);
    let [v, a] = await Promise.all([videos.next(), audios.next()]);
    if (v.done || a.done || !v.value.is_sync) throw new Error('分段起点没有音视频或关键帧');
    const baseMs = v.value.dts * 1000 / v.value.timescale;
    // Trim audio before the selected video keyframe, retaining the original A/V timestamps.
    while (!a.done && a.value.dts * 1000 / a.value.timescale < baseMs) a = await audios.next();
    if (a.done) throw new Error('目标位置没有音频');

    async function* chunks(): AsyncGenerator<StreamChunk> {
      let parts = [new Uint8Array([0x46, 0x4c, 0x56, 1, 5, 0, 0, 0, 9, 0, 0, 0, 0]),
        flvTag(9, 0, concat([new Uint8Array([0x17, 0, 0, 0, 0]), video.config])),
        flvTag(8, 0, concat([new Uint8Array([0xaf, 0]), audio.config]))];
      let boundary = baseMs + 2000, endTime = baseMs / 1000, bytes = 0;
      try {
        while (!v.done || !a.done) {
          signal.throwIfAborted();
          const useVideo = !v.done && (a.done || v.value.dts / v.value.timescale <= a.value.dts / a.value.timescale);
          const sample = (useVideo ? v.value : a.value)!;
          const timestamp = sample.dts * 1000 / sample.timescale;
          const tag = flvSample(sample, useVideo ? 'video' : 'audio', baseMs);
          parts.push(tag); bytes += tag.length;
          endTime = Math.max(endTime, (sample.cts + sample.duration) / sample.timescale);
          if (timestamp >= boundary || bytes >= 512 * 1024) {
            yield { data: concat(parts), endTime };
            parts = []; bytes = 0; boundary = timestamp + 2000;
          }
          if (useVideo) v = await videos.next(); else a = await audios.next();
        }
        if (parts.length) yield { data: concat(parts), endTime };
        // The legacy WASM reader checks its FIFO before draining AVIO's read-ahead
        // buffer. Repeating the unchanged AAC sequence header produces no frames
        // and lets the demuxer drain media without seeking or malformed padding.
        const padding = flvTag(8, endTime * 1000 - baseMs, concat([new Uint8Array([0xaf, 0]), audio.config]));
        yield { data: concat(Array.from({ length: 8192 }, () => padding)), endTime };
      } finally {
        await Promise.all([videos.return(), audios.return()]);
      }
    }
    const encoded = chunks();
    const first = await encoded.next();
    if (first.done) throw new Error('源流没有媒体数据');
    const probe = probePrefix(first.value.data);
    async function* primedChunks(): AsyncGenerator<StreamChunk> {
      try {
        yield { data: probe.data, endTime: baseMs / 1000 };
        signal.throwIfAborted();
        yield { ...first.value, data: shiftTimestamps(first.value.data.slice(13), probe.duration * 1000) };
        for await (const chunk of encoded) {
          signal.throwIfAborted();
          yield { ...chunk, data: shiftTimestamps(chunk.data, probe.duration * 1000) };
        }
      } finally {
        await encoded.return(undefined);
      }
    }
    return { duration: manifest.duration, startMs: baseMs, chunks: primedChunks(), signal,
      probeTime: probe.duration, cancel: () => controller.abort() };
  } catch (error) {
    controller.abort();
    throw error;
  }
}
