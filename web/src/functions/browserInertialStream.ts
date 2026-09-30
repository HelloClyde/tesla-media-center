import { createMotionCapture, type MotionGpsFix, type MotionState } from './motionCapture';
import { createInertialSession, type BrowserInertialSample, type InertialResult } from './inertialSession';

/** One stream per user start; stop also cancels pending permission/session work. */
export function createBrowserInertialStream(state: MotionState,
  subscribe: (receive: (fix: MotionGpsFix & { source?: string }) => void) => () => void,
  onResult: (result: InertialResult) => void, onError: (message: string) => void,
  request: typeof fetch = fetch) {
  let stopped = false, started = false, ready = false, lastGps = -1;
  let unsubscribe: (() => void) | undefined, monitor: ReturnType<typeof setInterval> | undefined;
  let pendingGps: BrowserInertialSample['gps'];
  const transport = createInertialSession(onResult, fail, request, 'browser');
  const capture = createMotionCapture(state, sample => {
    if (!ready || stopped) return;
    const reading: BrowserInertialSample = { elapsed: sample.elapsed,
      acceleration: sample.acceleration, angularVelocity: sample.angularVelocity };
    if (pendingGps && pendingGps.elapsed <= sample.elapsed) {
      reading.gps = pendingGps; pendingGps = undefined;
    }
    transport.push(reading);
  });
  function stop() {
    stopped = true; ready = false; clearInterval(monitor);
    unsubscribe?.(); unsubscribe = undefined; pendingGps = undefined;
    document.removeEventListener('visibilitychange', visibility);
    capture.stop(); transport.stop();
  }
  function fail(message: string) {
    if (stopped) return;
    stop(); onError(message);
  }
  function visibility() { if (document.hidden) fail('页面已隐藏，惯性联调已停止'); }
  function gps(fix: MotionGpsFix & { source?: string }) {
    const elapsed = capture.elapsedNow();
    if (!ready || stopped || elapsed === null || fix.source === 'mock') return;
    // Do not invent altitude/speed or replace unavailable sensors with GPS.
    if (![fix.longitude, fix.latitude, fix.altitude, fix.speed, fix.accuracy].every(
      value => typeof value === 'number' && Number.isFinite(value))) return;
    if (Math.abs(fix.longitude) > 180 || Math.abs(fix.latitude) > 90
      || fix.accuracy < 0 || fix.speed! < 0 || (fix.heading !== null
        && (!Number.isFinite(fix.heading) || fix.heading < 0 || fix.heading >= 360))) return;
    const tick = Math.floor(elapsed);
    if (tick <= lastGps) return;
    lastGps = tick;
    pendingGps = { elapsed, longitude: fix.longitude, latitude: fix.latitude,
      altitude: fix.altitude!, speed: fix.speed!, heading: fix.heading, accuracy: fix.accuracy };
  }
  async function start() {
    if (started || stopped) return false;
    started = true;
    // Invoke directly on the click stack, before awaiting any HTTP request.
    await capture.start();
    if (stopped) return false;
    if (!['waiting', 'receiving'].includes(state.status)) { fail(state.message); return false; }
    document.addEventListener('visibilitychange', visibility);
    monitor = setInterval(() => {
      if (['unavailable', 'denied', 'stopped'].includes(state.status)) fail(state.message);
    }, 250);
    if (!await transport.start() || stopped) return false;
    ready = true;
    try { unsubscribe = subscribe(gps); }
    catch { fail('无法订阅车辆定位'); return false; }
    return true;
  }
  return { start, stop, elapsedNow: capture.elapsedNow };
}
