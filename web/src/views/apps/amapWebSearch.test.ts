// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
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
