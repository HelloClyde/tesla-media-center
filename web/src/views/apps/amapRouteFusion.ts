import { cumulative, matchPosition, meters, pointAt, type AppRoute, type Point } from './amapNavigation';
import { bearingBetween } from './amapHeading';

export interface FusionFix { point: Point; accuracy: number; speed?: number | null; heading?: number | null; timestamp: number }
export interface FusionPosition { point: Point; progress?: number; heading?: number; speed: number; estimated: boolean; estimationSeconds?: number; state: 'tracking' | 'estimating' | 'recovering' | 'waiting' | 'off-route' }
/** Route-constrained positioning, not an IMU engine. All elapsed times are monotonic milliseconds. */
export function createRouteFusion(route: AppRoute) {
  const speedGraceMs = 12000;
  const speedFadeMs = 5000;
  const staleDistanceLimit = 120;
  const lengths = cumulative(route), total = lengths[lengths.length - 1];
  let progress: number | undefined, target: number | undefined;
  let clock = 0, trustedAt = -Infinity, speedAt = -Infinity, speed = 0, travelled = 0;
  let staleTravelled = 0, speedStreamEstablished = false;
  let lastFix: FusionFix | undefined, lastTimestamp = -Infinity;
  let trustedStream = false, odometer = 0;
  type Evidence = { since: number; last: number; count: number; distance: number; progress: number; point: Point };
  let recovery: Evidence | undefined, departure: Evidence | undefined;
  function corroborate(previous: Evidence | undefined, fix: FusionFix, matchedProgress: number, now: number, offRoute = false): Evidence {
    const distance = previous ? odometer - previous.distance : 0;
    const observed = previous ? offRoute ? meters(previous.point, fix.point) : matchedProgress - previous.progress : 0;
    // Compare the whole confirmation window, not just adjacent fixes: a slowly
    // moving or frozen "accurate" fix must not drag a moving vehicle backwards.
    const consistent = previous && now - previous.last <= 2500
      && Math.abs(observed - distance) <= 12 + distance * .2;
    return consistent ? { ...previous, last: now, count: previous.count + 1 }
      : { since: now, last: now, count: 1, distance: odometer, progress: matchedProgress, point: fix.point };
  }
  const confirmed = (value: Evidence, now: number) => value.count >= 3 && now - value.since >= 5000;
  let speedSamples = 0, unchangedSince = 0, lastSample: FusionFix | undefined;
  let state: FusionPosition['state'] = 'waiting';
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  function output(): FusionPosition | undefined {
    if (progress === undefined) return;
    const point = pointAt(route, progress);
    const staleFor = clock - speedAt;
    const estimatedSpeed = state === 'waiting' ? 0 : speed * clamp((speedGraceMs - staleFor) / (speedGraceMs - speedFadeMs), 0, 1);
    return { point, progress, speed: staleFor <= speedFadeMs ? speed : estimatedSpeed, heading: bearingBetween(point, pointAt(route, Math.min(total, progress + 8))),
      estimated: state !== 'tracking', estimationSeconds: Math.max(0, Math.floor((clock - trustedAt) / 1000)), state };
  }
  function tick(now: number) {
    const dt = clamp((now - clock) / 1000, 0, 1); clock = now;
    if (progress === undefined) return;
    if (state === 'off-route') return;
    if (now - trustedAt > 2500) { trustedStream = false; if (state === 'tracking') state = 'estimating'; }
    const continuousSpeed = speedSamples >= 3 && now - speedAt <= 2500;
    const staleFor = now - speedAt;
    if ((!speedStreamEstablished && !continuousSpeed && (now - trustedAt > 30000 || travelled >= 500))
      || staleFor > speedGraceMs || (speedStreamEstablished && staleTravelled >= staleDistanceLimit)) {
      state = 'waiting'; speed = 0; return output();
    }
    if (state === 'waiting') {
      if (!continuousSpeed) return output();
      state = 'estimating';
    }
    const fade = staleFor <= speedFadeMs ? 1 : clamp((speedGraceMs - staleFor) / (speedGraceMs - speedFadeMs), 0, 1);
    const step = continuousSpeed ? speed * dt
      : Math.min(speed * fade * dt, Math.max(0, speedStreamEstablished ? staleDistanceLimit - staleTravelled : 500 - travelled));
    let next = progress + step;
    if (target !== undefined) {
      target += step;
      next += clamp(target - next, -5 * dt, 5 * dt);
      if (Math.abs(target - next) < 1) { target = undefined; if (now - trustedAt < 2000) state = 'tracking'; }
    }
    // Never extrapolate across a missing section of route geometry.
    const boundary = route.breaks.map(i => lengths[i]).find(v => v >= progress! - .01);
    if (boundary !== undefined && next >= boundary) { next = boundary; state = 'waiting'; speed = 0; }
    progress = clamp(next, 0, total); travelled += step; odometer += step;
    // Count the first 2.5 seconds as part of an outage too; otherwise sparse
    // speed callbacks could repeatedly get that distance for free.
    if (speedStreamEstablished) staleTravelled += step;
    return output();
  }
  function accept(fix: FusionFix, now: number): FusionPosition | undefined {
    if (!Number.isFinite(fix.timestamp) || fix.timestamp <= lastTimestamp || !Number.isFinite(fix.accuracy) || fix.accuracy < 0
      || !fix.point.every(Number.isFinite)) return;
    tick(now); lastTimestamp = fix.timestamp;
    const match = matchPosition(route, fix.point, progress ?? 0, progress === undefined);
    const elapsed = lastFix ? Math.max(.1, (now - lastFixNow) / 1000) : 1;
    const plausible = !lastFix || meters(lastFix.point, fix.point) <= 60 * elapsed + lastFix.accuracy + fix.accuracy;
    const routeHeading = bearingBetween(route.path[match.index], route.path[Math.min(match.index + 1, route.path.length - 1)]);
    const headingOK = fix.heading == null || !Number.isFinite(fix.heading) || (fix.speed ?? 0) < 2
      || Math.abs(((fix.heading - routeHeading + 540) % 360) - 180) < 65;
    const precise = fix.accuracy <= 25 && plausible;
    // Repeated accurate off-route fixes must escape the route constraint and permit replanning.
    departure = precise && (match.distance > 40 || !headingOK) ? corroborate(departure, fix, match.progress, now, true) : undefined;
    if (departure && confirmed(departure, now)) { state = 'off-route'; return { point: fix.point, speed: fix.speed ?? 0, heading: fix.heading ?? undefined, estimated: false, state }; }
    const continuous = progress === undefined || state === 'waiting' || Math.abs(match.progress - (target ?? progress)) < Math.max(80, speed * elapsed + 40);
    const good = precise && match.distance <= 30 && headingOK && continuous;
    if (trustedStream && progress !== undefined && Math.abs(match.progress - (target ?? progress)) > 20) trustedStream = false;
    recovery = good ? corroborate(recovery, fix, match.progress, now) : undefined;
    if (good) {
      if (progress === undefined) { progress = match.progress; state = 'tracking'; trustedStream = true; }
      if (trustedStream || (recovery && confirmed(recovery, now))) {
        trustedStream = true;
        lastFix = fix; lastFixNow = now;
        trustedAt = now; travelled = 0;
        if (Math.abs(match.progress - progress) > 1) { target = match.progress; state = 'recovering'; }
        else { target = undefined; state = 'tracking'; }
      }
      else { if (state !== 'waiting') state = 'estimating'; target = undefined; }
    } else if (progress !== undefined) { trustedStream = false; if (state !== 'waiting') state = 'estimating'; target = undefined; }
    // Speed is assessed independently of drifting coordinates. A fresh timestamp
    // alone is insufficient: reject frozen full samples and implausible acceleration.
    const changed = !lastSample || fix.point[0] !== lastSample.point[0] || fix.point[1] !== lastSample.point[1]
      || fix.speed !== lastSample.speed || fix.heading !== lastSample.heading;
    if (changed) unchangedSince = now;
    const frozen = (fix.speed ?? 0) > 1 && now - unchangedSince > 8000;
    const speedElapsed = Math.max(.1, (now - speedAt) / 1000);
    const predictedHeading = progress === undefined ? routeHeading
      : bearingBetween(pointAt(route, progress), pointAt(route, Math.min(total, progress + 10)));
    const speedHeadingOK = fix.heading == null || !Number.isFinite(fix.heading) || (fix.speed ?? 0) < 2
      || Math.abs(((fix.heading - predictedHeading + 540) % 360) - 180) < 75;
    const validSpeed = !frozen && speedHeadingOK && typeof fix.speed === 'number' && Number.isFinite(fix.speed)
      && fix.speed >= 0 && fix.speed <= 60
      && (now - speedAt > 5000 || Math.abs(fix.speed - speed) <= 8 * speedElapsed + 2);
    if (validSpeed) {
      speedSamples = now - speedAt <= 2500 ? speedSamples + 1 : 1;
      speed = fix.speed!; speedAt = now;
      if (speedSamples >= 3) { speedStreamEstablished = true; staleTravelled = 0; }
    } else { speedSamples = 0; }
    lastSample = fix;
    return output();
  }
  let lastFixNow = 0;
  return { accept, tick };
}
