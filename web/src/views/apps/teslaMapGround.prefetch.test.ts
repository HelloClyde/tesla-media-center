import { afterEach, expect, it, vi } from 'vitest';
import type { AppRoute } from './amapNavigation';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
import { createTeslaMapGround } from './teslaMapGround';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); post.mockReset(); });

it('loads the visible 3D ground before warming decoded route roads and buildings', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  post.mockImplementation(async (url: string, batch: { level: number; tiles: number[][] }) => ({
    status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]) => url.endsWith('/prefetch')
      ? { x, y, ready: true }
      : { level: batch.level, x, y, collection: { features: [] }, buildings: [],
        surfaces: [{ minZoom: 0, maxZoom: 20, paints: { day: [{ minZoom: 0, maxZoom: 20, color: '#fff' }] },
          rings: [[[120, 30], [120.001, 30], [120, 30.001]]] }] }) } },
  }));
  const report = vi.fn();
  const ground = createTeslaMapGround(report);
  const route: AppRoute = { id: 1, path: [[120.1, 30.2], [120.2, 30.2]],
    breaks: [], steps: [], distance: 10000, labels: [] };
  ground.setRoute(route);
  ground.update([120.1, 30.2], -180, 0);
  await vi.advanceTimersByTimeAsync(500);
  const visibleCount = post.mock.calls.length;
  expect(post.mock.calls.slice(0, visibleCount).some(call => call[1].level === 15)).toBe(true);
  await vi.advanceTimersByTimeAsync(20000);
  const background = post.mock.calls.slice(visibleCount);
  expect(background.length).toBeGreaterThan(0);
  expect(background.every(call => call[1].tiles.length === 1)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map' && call[1].level === 14)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map' && call[1].level === 15)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map/prefetch')).toBe(true);
  const buildingDownloads = background.filter(call => call[0] === '/api/amap-app/map' && call[1].level === 15);
  const prefetchedBuilding = buildingDownloads[buildingDownloads.length - 1][1].tiles[0];
  const [x, y] = prefetchedBuilding;
  const target: [number, number] = [(x + .5) / 2 ** 15 * 360 - 180, 90 - (y + .5) / 2 ** 15 * 180];
  const beforeMove = post.mock.calls.length;
  const beforeReports = report.mock.calls.length;
  ground.update(target, -180, 0);
  await vi.advanceTimersByTimeAsync(500);
  expect(report.mock.calls.length).toBeGreaterThan(beforeReports);
  expect(post.mock.calls.slice(beforeMove).filter(call => call[0] === '/api/amap-app/map' && call[1].level === 15)
    .every(call => !call[1].tiles.some(([tx, ty]: number[]) => tx === x && ty === y))).toBe(true);
  ground.dispose();
});
