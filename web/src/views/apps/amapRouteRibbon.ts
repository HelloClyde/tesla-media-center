import * as THREE from 'three';
import { cumulative, matchPosition, type AppRoute } from './amapNavigation';
import { groundOffset, groundPoint, type MapPoint } from './teslaMapCoordinates';

export type RibbonSpan = { start: number; end: number };
export type RouteRibbonPoint = { point: MapPoint; distance: number; section: number };

/** Keep the ribbon under the displayed car while its position catches up with the latest fix. */
export function routeRibbonCutProgress(route: AppRoute, progress: number, displayedPosition?: MapPoint) {
  const routeProgress = Math.max(0, Number.isFinite(progress) ? progress : 0);
  const match = displayedPosition && route.path.length > 1
    ? matchPosition(route, displayedPosition, 0, true) : undefined;
  const visibleProgress = match && match.distance <= 30
    ? Math.min(routeProgress, match.progress) : routeProgress;
  return Math.max(0, visibleProgress - 8);
}

/** Round genuine route corners without connecting discontinuities between steps. */
export function roundedRoutePoints(route: AppRoute, origin: MapPoint): RouteRibbonPoint[] {
  const lengths = cumulative(route), breaks = new Set(route.breaks);
  const local = route.path.map(point => groundOffset(point, origin));
  const result: RouteRibbonPoint[] = [];
  let section = 0;
  for (let i = 0; i < route.path.length; i++) {
    if (breaks.has(i) && i > 0) {
      const start = local[i - 1], end = local[i], gap = Math.hypot(end[0] - start[0], end[1] - start[1]);
      if (gap > .01 && gap <= 40) {
        const before = local[i - 2], after = local[i + 1];
        let control: MapPoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
        if (before && after) {
          const incoming: MapPoint = [start[0] - before[0], start[1] - before[1]];
          const outgoing: MapPoint = [after[0] - end[0], after[1] - end[1]];
          const a = Math.hypot(...incoming), b = Math.hypot(...outgoing);
          if (a > 1 && b > 1) {
            const first: MapPoint = [incoming[0] / a, incoming[1] / a];
            const second: MapPoint = [outgoing[0] / b, outgoing[1] / b];
            const cross = first[0] * second[1] - first[1] * second[0];
            if (Math.abs(cross) > .15) {
              const dx = end[0] - start[0], dz = end[1] - start[1];
              const approach = (dx * second[1] - dz * second[0]) / cross;
              const depart = (first[0] * dz - first[1] * dx) / cross;
              if (approach >= 0 && depart >= 0 && approach <= gap * 2 && depart <= gap * 2)
                control = [start[0] + first[0] * approach, start[1] + first[1] * approach];
            }
          }
        }
        const steps = Math.max(3, Math.ceil(gap / 4));
        for (let step = 1; step <= steps; step++) {
          const t = step / steps, u = 1 - t;
          result.push({ point: groundPoint(origin,
            u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
            u * u * start[1] + 2 * u * t * control[1] + t * t * end[1]),
            distance: lengths[i], section });
        }
        continue;
      }
      section++;
    }
    const previous = local[i - 1], center = local[i], next = local[i + 1];
    if (previous && next && !breaks.has(i) && !breaks.has(i + 1)) {
      const incoming: MapPoint = [center[0] - previous[0], center[1] - previous[1]];
      const outgoing: MapPoint = [next[0] - center[0], next[1] - center[1]];
      const before = Math.hypot(...incoming), after = Math.hypot(...outgoing);
      if (before > 1 && after > 1) {
        const dot = Math.max(-1, Math.min(1, (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / (before * after)));
        if (dot < .92 && dot > -.85) {
          const setback = Math.min(12, before * .3, after * .3);
          const start: MapPoint = [center[0] - incoming[0] / before * setback, center[1] - incoming[1] / before * setback];
          const end: MapPoint = [center[0] + outgoing[0] / after * setback, center[1] + outgoing[1] / after * setback];
          const steps = Math.max(3, Math.ceil(setback * Math.acos(dot) / 3));
          for (let step = 0; step <= steps; step++) {
            const t = step / steps, u = 1 - t;
            const x = u * u * start[0] + 2 * u * t * center[0] + t * t * end[0];
            const z = u * u * start[1] + 2 * u * t * center[1] + t * t * end[1];
            result.push({ point: groundPoint(origin, x, z), distance: lengths[i] + (2 * t - 1) * setback, section });
          }
          continue;
        }
      }
    }
    result.push({ point: route.path[i], distance: lengths[i], section });
  }
  return result;
}

/** Shared miter at adjacent ribbon quads; a bounded length prevents spikes. */
export function ribbonJoinNormal(current: MapPoint, adjacent?: MapPoint): MapPoint {
  if (!adjacent) return current;
  const sum: MapPoint = [current[0] + adjacent[0], current[1] + adjacent[1]];
  const length = Math.hypot(...sum);
  if (length < .2) return current;
  const direction: MapPoint = [sum[0] / length, sum[1] / length];
  const scale = Math.min(2, 1 / Math.max(.5, direction[0] * current[0] + direction[1] * current[1]));
  return [direction[0] * scale, direction[1] * scale];
}

const trimmedQuad = new WeakMap<THREE.BufferGeometry, number>();
/** Clip the first visible six-vertex route quad at the current route metre. */
export function trimRouteRibbon(geometry: THREE.BufferGeometry, spans: RibbonSpan[],
  original: Float32Array, progress: number) {
  if (original.length !== spans.length * 18 || !Number.isFinite(progress)) return;
  let low = 0, high = spans.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (spans[middle].end <= progress) low = middle + 1;
    else high = middle;
  }
  const position = geometry.getAttribute('position') as THREE.BufferAttribute;
  const previous = trimmedQuad.get(geometry);
  if (previous !== undefined && previous !== low) {
    const previousOffset = previous * 18;
    for (let i = 0; i < 18; i++) position.array[previousOffset + i] = original[previousOffset + i];
  }
  if (low === spans.length) {
    trimmedQuad.delete(geometry);
    position.needsUpdate = true;
    geometry.setDrawRange(0, 0);
    return;
  }
  const offset = low * 18;
  // Restore the first quad before each trim so backward GPS corrections can
  // reveal its original beginning again.
  for (let i = 0; i < 18; i++) position.array[offset + i] = original[offset + i];
  const span = spans[low];
  const fraction = Math.max(0, Math.min(1, (progress - span.start) / (span.end - span.start || 1)));
  if (fraction > 0) {
    for (const [from, to] of [[0, 3], [6, 15], [9, 15]] as const) {
      for (let axis = 0; axis < 3; axis++) {
        position.array[offset + from + axis] = original[offset + from + axis]
          + (original[offset + to + axis] - original[offset + from + axis]) * fraction;
      }
    }
    trimmedQuad.set(geometry, low);
  } else {
    trimmedQuad.delete(geometry);
  }
  position.needsUpdate = true;
  geometry.setDrawRange(low * 6, (spans.length - low) * 6);
}
