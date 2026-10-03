import { afterEach, expect, it, vi } from 'vitest';
const { post, cancelDraw } = vi.hoisted(() => ({ post: vi.fn(), cancelDraw: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
vi.mock('leaflet', () => ({ default: {
  canvas: () => ({ remove() {} }),
  layerGroup: () => ({ addTo() { return this; }, remove() {} }),
} }));
vi.mock('./mapRenderQueue', () => ({ createMapRenderQueue: () => ({ start() {}, cancel: cancelDraw }) }));
import { attachAppMap } from './amapVectorMap';
afterEach(() => { vi.useRealTimers(); post.mockReset(); cancelDraw.mockReset(); });

function fakeMap() {
  const events: Record<string, () => void> = {};
  const map = {
    getPane() {}, createPane: () => ({ style: {} }), getZoom: () => 14,
    getBounds: () => ({ getWest: () => 120, getEast: () => 120.001, getNorth: () => 30.001, getSouth: () => 30 }),
    on(names: string, fn: () => void) { names.split(' ').forEach(name => events[name] = fn); }, off() {},
  };
  return { map: map as any, events };
}
it('keeps in-flight tiles during movement and aborts on disposal', async () => {
  vi.useFakeTimers();
  let resolve!: (value: unknown) => void;
  post.mockImplementationOnce(() => new Promise(r => resolve = r));
  const { map, events } = fakeMap();
  const layer = attachAppMap(map, vi.fn());
  const signal = post.mock.calls[0][2].signal;
  events.movestart(); events.moveend();
  await vi.advanceTimersByTimeAsync(150);
  expect(signal.aborted).toBe(false);
  expect(post).toHaveBeenCalledTimes(1);
  const batch = post.mock.calls[0][1];
  resolve({ status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]: number[]) => ({ level: batch.level, x, y })) } } });
  post.mockImplementation(() => new Promise(() => {}));
  await vi.advanceTimersByTimeAsync(150);
  expect(post).toHaveBeenCalledTimes(2);
  layer.dispose();
  expect(post.mock.calls[1][2].signal.aborted).toBe(true);
});
it('backs off failed tiles instead of looping on the same request', async () => {
  vi.useFakeTimers(); post.mockRejectedValue(new Error('offline'));
  const { map } = fakeMap(); const layer = attachAppMap(map, vi.fn());
  await vi.advanceTimersByTimeAsync(1000);
  const firstLevel = post.mock.calls[0][1].level;
  expect(post.mock.calls.filter(c => c[1].level === firstLevel)).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1500);
  expect(post.mock.calls.filter(c => c[1].level === firstLevel)).toHaveLength(2);
  layer.dispose();
});
it('does not repeatedly cancel drawing while following successive GPS pans', () => {
  post.mockImplementation(() => new Promise(() => {}));
  const { map, events } = fakeMap();
  const layer = attachAppMap(map, vi.fn());
  layer.setFollowing(true);
  for (let i = 0; i < 10; i++) { events.movestart(); events.moveend(); }
  expect(cancelDraw).not.toHaveBeenCalled();
  layer.dispose();
});
