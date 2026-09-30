// @vitest-environment node
/** Opt-in cross-process check; started by verify_vdr_live_http.py. */
import { expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';
import { createBrowserInertialStream } from './browserInertialStream';
import { initialMotionState } from './motionCapture';
import type { InertialResult } from './inertialSession';

it.skipIf(!process.env.TMC_VDR_TEST_URL)('streams DOM motion through real HTTP and the translated engine', async () => {
  let clock = 0, receiveGps!: (fix: any) => void;
  const results: InertialResult[] = [], errors: string[] = [];
  const unsubscribe = vi.fn();
  // Keep Node fetch and AbortController in the same realm. Only DOM surfaces
  // come from jsdom; the transport still uses real HTTP with cancellation.
  const dom = new JSDOM('', { url: process.env.TMC_VDR_TEST_URL });
  vi.stubGlobal('window', dom.window); vi.stubGlobal('document', dom.window.document);
  Object.defineProperty(window, 'isSecureContext', { value: true });
  Object.defineProperty(window, 'DeviceMotionEvent', { value: class {} });
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
  let cookie = process.env.TMC_VDR_TEST_COOKIE!;
  const request: typeof fetch = async (url, options) => {
    try {
      const response = await fetch(`${process.env.TMC_VDR_TEST_URL}${url}`, {
        ...options, headers: { ...options?.headers, Cookie: cookie },
      });
      // Native Node fetch has no browser cookie jar. Retain Flask's updated
      // signed session containing the inertial session owner.
      const updated = response.headers.get('set-cookie');
      if (updated) cookie = updated.split(';', 1)[0];
      return response;
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };
  const stream = createBrowserInertialStream(initialMotionState(), receive => {
    receiveGps = receive; return unsubscribe;
  }, result => results.push(result), message => errors.push(message), request);
  try {
    const health = await request('/api/amap-app/inertial/status');
    expect(health.ok).toBe(true);
    const started = await stream.start();
    expect(errors).toEqual([]);
    expect(started).toBe(true);
    for (let start = 0; start < 1600; start += 25) {
      for (let step = start; step < start + 25; step++) {
        clock = 1000 + step * 40;
        if (step % 25 === 0 && !(step >= 1100 && step < 1400)) receiveGps({
          longitude: 120 + step * .000003, latitude: 30, altitude: 0,
          accuracy: 1, speed: 7.2, heading: 90, timestamp: 1700000000000 + clock,
          altitudeAccuracy: null, source: 'gps',
        });
        const factor = 1 + .12 * Math.sin(2 * Math.PI * 2 * step * .04) / 9.80665;
        window.dispatchEvent(Object.assign(new dom.window.Event('devicemotion'), {
          accelerationIncludingGravity: { x: .2 * factor, y: .3 * factor,
            z: Math.sqrt(9.80665 ** 2 - .13) * factor },
          rotationRate: { alpha: 0, beta: 0, gamma: 0 }, interval: 40,
        }));
      }
      await vi.waitFor(() => {
        expect(errors).toEqual([]);
        expect(results[results.length - 1]?.timestamp).toBe(clock + 1);
      }, { timeout: 4000, interval: 25 });
    }
    const before = results.find(result => result.timestamp === 1000 + 1099 * 40 + 1)!.output!;
    const after = results.find(result => result.timestamp === 1000 + 1399 * 40 + 1)!.output!;
    const distance = (after.longitude - before.longitude) * Math.cos(Math.PI / 6) * 111319.49079327358;
    expect(distance).toBeGreaterThan(60); expect(distance).toBeLessThan(110);
    expect(after.missing_fix).toBe(true);
    expect(results[results.length - 1]?.output?.missing_fix).toBe(false);
    expect(results[results.length - 1]?.output?.estimated_accuracy).toBeGreaterThanOrEqual(0);
    stream.stop(); expect(unsubscribe).toHaveBeenCalledOnce();
  } finally {
    stream.stop(); vi.restoreAllMocks(); vi.unstubAllGlobals(); dom.window.close();
  }
}, 60000);
