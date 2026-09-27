// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createFile, type MP4BoxBuffer, type Sample } from 'mp4box';
import { RangeSource, createDirectSource, concat, flvSample, parseIndex, parseRange, segmentAt, type DirectManifest } from './biliDirect';

afterEach(() => vi.unstubAllGlobals());

function fixture(kind: 'audio' | 'video') {
  const data = new Uint8Array(readFileSync(new URL(`./__fixtures__/bili-direct/${kind}.mp4`, import.meta.url)));
  const file = createFile();
  file.appendBuffer(Object.assign(data.slice().buffer, { fileStart: 0 }) as MP4BoxBuffer);
  const index = file.sidx;
  const start = index.start!;
  return { data, track: { urls: [`https://cdn.test/${kind}`], codec: file.getInfo().tracks[0].codec,
    initialization: `0-${start - 1}`, indexRange: `${start}-${start + index.size - 1}` },
    segments: parseIndex(data.slice(start, start + index.size).buffer, start) };
}

function setupSource() {
  const video = fixture('video'), audio = fixture('audio');
  const mock = vi.fn(async (url: string, options: RequestInit) => {
    const data = url.endsWith('/video') ? video.data : audio.data;
    const [start, end] = parseRange((options.headers as Record<string, string>).Range.slice(6));
    return new Response(data.slice(start, end + 1), { status: 206, headers: {
      'Content-Range': `bytes ${start}-${end}/${data.length}`,
    } });
  });
  vi.stubGlobal('fetch', mock);
  const manifest: DirectManifest = { mode: 'dash-direct', duration: 3000, video: video.track, audio: audio.track };
  return { manifest, mock, video, audio };
}

function tags(data: Uint8Array) {
  const view = new DataView(data.buffer);
  const result = [];
  const u24 = (i: number) => data[i] * 65536 + data[i + 1] * 256 + data[i + 2];
  expect(Array.from(data.slice(0, 3))).toEqual([70, 76, 86]);
  let pos = 13;
  while (pos < data.length) {
    const size = u24(pos + 1);
    expect(view.getUint32(pos + 11 + size)).toBe(size + 11);
    result.push({ type: data[pos], time: u24(pos + 4) + data[pos + 7] * 16777216, body: data.slice(pos + 11, pos + 11 + size) });
    pos += size + 15;
  }
  expect(pos).toBe(data.length);
  return result;
}

describe('direct DASH remux', () => {
  it('produces H264/AAC FLV with complete tags, interleaved timestamps and EOF padding', async () => {
    const { manifest, mock } = setupSource();
    const source = await createDirectSource(manifest, 0, new AbortController());
    const chunks = [];
    for await (const chunk of source.chunks) chunks.push(chunk.data);
    const result = tags(concat(chunks));
    expect(result[0].type).toBe(9);
    expect(Array.from(result[0].body.slice(0, 2))).toEqual([0x17, 0]);
    expect(Array.from(result[1].body.slice(0, 2))).toEqual([0xaf, 0]);
    const media = result.filter(t => t.type !== 18 && t.body[1] === 1 && t.time >= source.probeTime * 1000);
    expect(media.filter(t => t.type === 9)).toHaveLength(30);
    expect(media.some(t => t.type === 8)).toBe(true);
    expect(media.map(t => t.time)).toEqual(media.map(t => t.time).sort((a, b) => a - b));
    expect(Array.from(result[result.length - 1].body.slice(0, 2))).toEqual([0xaf, 0]);
    for (const [url, options] of mock.mock.calls) {
      expect(url).toMatch(/^https:\/\/cdn.test\//);
      expect(options.credentials).toBe('omit');
      expect(options.referrerPolicy).toBe('no-referrer');
    }
  });

  it('seeks by segment index without fetching earlier media and starts on a keyframe', async () => {
    const { manifest, mock, video } = setupSource();
    const source = await createDirectSource(manifest, 2200, new AbortController());
    expect(source.startMs).toBeGreaterThanOrEqual(1000);
    expect(source.startMs).toBeLessThanOrEqual(2200);
    const chunks = [];
    for await (const chunk of source.chunks) chunks.push(chunk.data);
    const frames = tags(concat(chunks)).filter(t => t.type === 9 && t.body[1] === 1 && t.time >= source.probeTime * 1000);
    expect(frames[0].body[0]).toBe(0x17);
    expect(frames[0].time - source.probeTime * 1000).toBe(0);
    const first = video.segments[0];
    expect(mock.mock.calls.some(([u, o]) => u.endsWith('/video') &&
      (o.headers as Record<string, string>).Range === `bytes=${first.start}-${first.end}`)).toBe(false);
  });

  it('stops fetching after cancellation, including cancellation between yielded chunks', async () => {
    const { manifest, mock } = setupSource();
    const controller = new AbortController();
    const source = await createDirectSource(manifest, 0, controller);
    const iterator = source.chunks[Symbol.asyncIterator]();
    await iterator.next();
    const count = mock.mock.calls.length;
    source.cancel();
    await expect(iterator.next()).rejects.toThrow();
    expect(mock).toHaveBeenCalledTimes(count);
  });

  it('keeps signed composition offsets for B frames and extended FLV timestamps', () => {
    const sample = { is_sync: false, dts: 17000000, cts: 16999960, timescale: 1000,
      data: new Uint8Array([1, 2, 3]) } as Sample;
    const tag = flvSample(sample, 'video', 0);
    expect(Array.from(tag.slice(13, 16))).toEqual([255, 255, 216]);
    expect(tag[7]).toBe(1);
  });

  it('preserves the opening keyframe and drains the tail through the actual bundled WASM decoder', async () => {
    const { manifest } = setupSource();
    const source = await createDirectSource(manifest, 0, new AbortController());
    const chunks = [];
    for await (const chunk of source.chunks) chunks.push(chunk.data);
    const bytes = concat(chunks);
    const require = createRequire(import.meta.url);
    const wasm = require('../../public/libffmpeg.js');
    await new Promise<void>(resolve => { wasm.onRuntimeInitialized = resolve; });
    const videos: number[] = [], audios: number[] = [];
    const record = (list: number[]) => (_ptr: number, _size: number, time: number) => {
      if (time >= source.probeTime) list.push(time - source.probeTime);
    };
    const videoCallback = wasm.addFunction(record(videos), 'viid');
    const audioCallback = wasm.addFunction(record(audios), 'viid');
    const statusCallback = wasm.addFunction(() => {}, 'vi');
    const requestCallback = wasm.addFunction(() => {}, 'vii');
    const buffer = wasm._malloc(bytes.length), params = wasm._malloc(28);
    try {
      expect(wasm._initDecoder(-1, 0)).toBe(0);
      wasm.HEAPU8.set(bytes, buffer);
      wasm._sendData(buffer, bytes.length);
      expect(wasm._openDecoder(params, 7, videoCallback, audioCallback, statusCallback, requestCallback)).toBe(0);
      for (let i = 0; i < 2000; i++) wasm._decodeOnePacket();
      expect(audios[0]).toBeCloseTo(0, 2);
      expect(videos[0]).toBeCloseTo(0.2, 2);
      expect(videos.length).toBeGreaterThanOrEqual(28);
      expect(audios[audios.length - 1]).toBeGreaterThan(2.9);
      expect(videos.every(t => t >= 0 && t < 3.3)).toBe(true);
    } finally {
      wasm._closeDecoder(); wasm._uninitDecoder();
      wasm._free(buffer); wasm._free(params);
    }
  });
});

describe('CDN range transport', () => {
  it('fails over on HTTP rejection and remembers the working backup', async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response('', { status: 403 }))
      .mockImplementation(async () => new Response(new Uint8Array([1, 2]), { status: 206,
        headers: { 'Content-Range': 'bytes 0-1/10' } }));
    vi.stubGlobal('fetch', mock);
    const source = new RangeSource(['https://bad.test', 'https://good.test'], new AbortController().signal);
    expect(new Uint8Array(await source.read(0, 1))).toEqual(new Uint8Array([1, 2]));
    await source.read(0, 1);
    expect(mock.mock.calls.map(c => c[0])).toEqual(['https://bad.test', 'https://good.test', 'https://good.test']);
  });

  it.each([
    [200, 'bytes 0-1/10', [1, 2]], [206, '', [1, 2]],
    [206, 'bytes 1-2/10', [1, 2]], [206, 'bytes 0-1/10', [1]],
    [206, 'bytes 0-1/10', [1, 2, 3]],
  ])('rejects ignored, inaccessible, mismatched or incomplete ranges (%s / %s)', async (status, range, bytes) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Uint8Array(bytes as number[]), {
      status: status as number, headers: { 'Content-Range': range as string },
    })));
    await expect(new RangeSource(['https://cdn.test'], new AbortController().signal).read(0, 1)).rejects.toThrow('直连失败');
  });

  it('rejects invalid ranges and chooses preceding segments at boundaries', () => {
    expect(() => parseRange('4-1')).toThrow();
    expect(() => parseRange('0-999999999999')).toThrow();
    expect(() => parseIndex(new ArrayBuffer(8), 0)).toThrow();
    const segments = fixture('video').segments;
    expect(segmentAt(segments, 0)).toBe(0);
    expect(segmentAt(segments, segments[1].time)).toBe(1);
    expect(segmentAt(segments, Infinity)).toBe(segments.length - 1);
  });
});
