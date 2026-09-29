// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { ref } from 'vue';
import { searchWebPlaces } from './amapWebSearch';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
const configured = () => vi.mocked(axios.get).mockResolvedValue({ data: { status: 'ok', data: { amap_key: 'test-only' } } });
const frame = () => document.querySelector('iframe')!;
function reply(data: unknown, source = frame().contentWindow, origin = location.origin) {
  window.dispatchEvent(new MessageEvent('message', { data, source, origin }));
}
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ''; });

describe('isolated legacy Web SDK search', () => {
  it('reports a missing key before creating a frame', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { status: 'ok', data: {} } });
    await expect(searchWebPlaces('北京大学', new AbortController().signal)).rejects.toThrow('Key');
    expect(frame()).toBeNull();
  });
  it('accepts results only from its own same-origin frame and cleans up', async () => {
    configured();
    const pending = searchWebPlaces('北京大学', new AbortController().signal);
    await vi.waitFor(() => expect(frame()).not.toBeNull());
    const data = { type: 'tmc-search-result', status: 'ok', data: { coordinateSystem: 'GCJ-02', places: [] } };
    reply(data, window);
    reply(data, frame().contentWindow, 'https://other.example');
    expect(frame()).not.toBeNull();
    reply(data);
    await expect(pending).resolves.toEqual([]);
    expect(frame()).toBeNull();
  });
  it('removes the frame when a query is cancelled', async () => {
    configured();
    const controller = new AbortController();
    const pending = searchWebPlaces('北京大学', controller.signal);
    const rejection = expect(pending).rejects.toThrow('取消');
    await vi.waitFor(() => expect(frame()).not.toBeNull());
    controller.abort();
    await rejection;
    expect(frame()).toBeNull();
  });
  it('preserves SDK failure messages instead of presenting empty results', async () => {
    configured();
    const pending = searchWebPlaces('北京大学', new AbortController().signal);
    const rejection = expect(pending).rejects.toThrow('INVALID_USER_KEY');
    await vi.waitFor(() => expect(frame()).not.toBeNull());
    reply({ type: 'tmc-search-result', status: 'error', message: 'INVALID_USER_KEY' });
    await rejection;
    expect(frame()).toBeNull();
  });
});


it('gives SDK loading its own deadline and resets the timer when the query starts', async () => {
  vi.useFakeTimers();
  try {
    configured();
    const pending = searchWebPlaces('测试', new AbortController().signal);
    const rejection = expect(pending).rejects.toThrow('地点查询超时');
    await Promise.resolve(); await Promise.resolve();
    reply({ type: 'tmc-search-stage', stage: 'sdk-loading' });
    await vi.advanceTimersByTimeAsync(25000);
    expect(frame()).not.toBeNull();
    reply({ type: 'tmc-search-stage', stage: 'query' });
    await vi.advanceTimersByTimeAsync(12000);
    await rejection;
    expect(frame()).toBeNull();
  } finally { vi.useRealTimers(); }
});
it('reports SDK network timeout separately from search failure', async () => {
  vi.useFakeTimers();
  try {
    configured();
    const pending = searchWebPlaces('测试', new AbortController().signal);
    const rejection = expect(pending).rejects.toThrow('SDK 加载超时');
    await Promise.resolve(); await Promise.resolve();
    reply({ type: 'tmc-search-stage', stage: 'sdk-loading' });
    await vi.advanceTimersByTimeAsync(30000); await rejection;
    expect(frame()).toBeNull();
  } finally { vi.useRealTimers(); }
});

it('sends a cloneable coordinate snapshot from a Vue location ref', async () => {
  configured();
  const location = ref<[number, number]>([120.28447, 30.199608]);
  expect(() => structuredClone(location.value)).toThrow();
  const pending = searchWebPlaces('江南名府', new AbortController().signal, location.value);
  await vi.waitFor(() => expect(frame()).not.toBeNull());
  let sent: any;
  const post = vi.spyOn(frame().contentWindow!, 'postMessage').mockImplementation(value => { sent = structuredClone(value); });
  reply({ type: 'tmc-search-ready' });
  expect(post).toHaveBeenCalledOnce();
  expect(sent.center).toEqual([120.28447, 30.199608]);
  location.value[0] = 121;
  expect(sent.center[0]).toBe(120.28447);
  reply({ type: 'tmc-search-result', status: 'ok', data: { coordinateSystem: 'GCJ-02', places: [] } });
  await expect(pending).resolves.toEqual([]);
});
it('reports a message-send failure immediately and removes the frame', async () => {
  configured();
  const pending = searchWebPlaces('测试', new AbortController().signal);
  const rejection = expect(pending).rejects.toThrow('搜索请求发送失败');
  await vi.waitFor(() => expect(frame()).not.toBeNull());
  vi.spyOn(frame().contentWindow!, 'postMessage').mockImplementation(() => { throw new DOMException('not cloneable', 'DataCloneError'); });
  reply({ type: 'tmc-search-ready' });
  await rejection;
  expect(frame()).toBeNull();
});
