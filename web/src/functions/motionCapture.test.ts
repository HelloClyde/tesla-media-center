import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { createMotionCapture, initialMotionState, readMotionSample } from './motionCapture';
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('DeviceMotionEvent', class {});
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function event(values = {}) {
  return Object.assign(new Event('devicemotion'), {
    accelerationIncludingGravity: { x: 0, y: 0, z: 9.8 },
    rotationRate: { alpha: 180, beta: 90, gamma: -90 }, interval: 20, ...values,
  }) as DeviceMotionEvent;
}
it('records GPS with the same receipt clock while preserving missing fields and original timestamps', async () => {
  let clock = 100;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
  const capture = createMotionCapture(initialMotionState());
  const fix = { timestamp: 1700000000000, latitude: 30, longitude: 120, accuracy: 2,
    altitude: null, altitudeAccuracy: null, speed: null, heading: null };
  expect(capture.recordGps(fix)).toBeUndefined();
  await capture.start();
  clock = 140;
  window.dispatchEvent(event());
  expect(capture.recordGps(fix)).toBe(1);
  const recording = capture.recording();
  expect(recording.gps.fixes[0]).toEqual({ ...fix, elapsed: 40 });
  expect(recording.samples[0].elapsed).toBe(40);
  recording.gps.fixes[0].longitude = 0;
  expect(capture.recording().gps.fixes[0].longitude).toBe(120);
  capture.recordGps({ ...fix, latitude: NaN });
  expect(capture.recording().gps.fixes).toHaveLength(1);
  capture.stop();
  capture.recordGps(fix);
  expect(capture.recording().gps.fixes).toHaveLength(1);
  await capture.start();
  expect(capture.recording().gps.fixes).toHaveLength(0);
  capture.stop();
});
it('maps physical axes and units without converting absent sensor fields to zero', () => {
  const sample = readMotionSample(event(), 20, 1000)!;
  expect(sample.angularVelocity).toEqual([Math.PI / 2, -Math.PI / 2, Math.PI]);
  expect(sample.timestamp).toBe(1020);
  expect(readMotionSample(event({ rotationRate: { alpha: null, beta: 0, gamma: 0 } }), 20, 0)).toBeNull();
});
it('reports missing samples and releases the listener on stop', async () => {
  const state = initialMotionState(), sink = vi.fn(), capture = createMotionCapture(state, sink);
  await capture.start();
  window.dispatchEvent(event({ rotationRate: null }));
  expect(state.incomplete).toBe(1);
  vi.advanceTimersByTime(5000); expect(state.status).toBe('unavailable');
  vi.spyOn(performance, 'now').mockReturnValue(10000);
  window.dispatchEvent(event()); expect(sink).toHaveBeenCalledTimes(1);
  expect(state.status).toBe('receiving');
  capture.stop(); window.dispatchEvent(event()); expect(sink).toHaveBeenCalledTimes(1);
});
it('does not start after an outstanding permission request is cancelled', async () => {
  let resolve!: (s: string) => void;
  vi.stubGlobal('DeviceMotionEvent', { requestPermission: () => new Promise<string>(r => { resolve = r; }) });
  const state = initialMotionState(), capture = createMotionCapture(state);
  const pending = capture.start(); capture.stop(); resolve('granted'); await pending;
  window.dispatchEvent(event()); expect(state.count).toBe(0); expect(state.status).toBe('stopped');
});
it('bounds exports and stops when the document becomes hidden', async () => {
  let clock = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
  const state = initialMotionState(), capture = createMotionCapture(state);
  await capture.start();
  for (let n = 0; n < 3010; n++) { clock += 20; window.dispatchEvent(event()); }
  expect(capture.recording().samples).toHaveLength(3000);
  expect(state.hz).toBe(50);
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  document.dispatchEvent(new Event('visibilitychange'));
  expect(state.status).toBe('stopped');
  window.dispatchEvent(event()); expect(state.count).toBe(3010);
});
