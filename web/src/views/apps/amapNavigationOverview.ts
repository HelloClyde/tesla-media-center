import { cumulative, matchPosition, type AppRoute, type Point } from './amapNavigation';
import { remainingRouteSections } from './amapRemainingRoute';
import { remainingRouteDuration } from './amapRouteSummary';
import { routePreviewSamples } from './amapRoutePreview';
import { bearingBetween } from './amapHeading';

export interface NavigationRouteOption {
  preview: AppRoute;
  routes: AppRoute[];
  routeIndex: number;
  token: string;
  current: boolean;
}

/** A display-only remainder; its indices must never be used for native events. */
export function remainingRoutePreview(route: AppRoute, progress: number): AppRoute {
  const path: Point[] = [], breaks: number[] = [];
  for (const section of remainingRouteSections(route, progress)) {
    if (!section.length) continue;
    if (path.length) breaks.push(path.length);
    path.push(...section);
  }
  const lengths = cumulative(route), total = lengths[lengths.length - 1];
  return { ...route, path, breaks, steps: [], roadLinks: [], trafficRuns: [], trafficLights: [],
    trafficLightCount: undefined, distance: total > 0 ? route.distance * Math.max(0, 1 - progress / total) : 0,
    duration: remainingRouteDuration(route, progress), labels: ['当前路线'] };
}

/** Native route IDs are session-local. Compare the remaining corridors instead. */
export function sameRemainingRoute(a: AppRoute, b: AppRoute): boolean {
  const length = (route: AppRoute) => { const values = cumulative(route); return values[values.length - 1]; };
  const aLength = length(a), bLength = length(b);
  if (!aLength || !bLength || Math.abs(aLength - bLength) > Math.max(80, aLength * .025)) return false;
  // Sample by distance, and project onto the full geometry, including its breaks.
  // Both directions are necessary: one route may take a detour past the same trunk.
  return [[a, b], [b, a]].every(([source, target]) => {
    const points = routePreviewSamples(source);
    return points.length > 0 && points.every(point => matchPosition(target, point, 0, true).distance <= 25);
  });
}

/** Pin the running route. Refreshing choices alone never replaces its session. */
export function navigationRouteOptions(routes: AppRoute[], selected: number, token: string, progress: number,
  fresh: AppRoute[] = [], freshToken = ''): NavigationRouteOption[] {
  const active = routes[selected];
  if (!active) return [];
  const preview = remainingRoutePreview(active, progress);
  const options: NavigationRouteOption[] = [{ preview, routes, routeIndex: selected, token, current: true }];
  for (let index = 0; index < fresh.length; index++) {
    const candidate = fresh[index];
    // The car can move while the request runs. Trim its already driven prefix
    // for display/comparison, but preserve native indices in the full route.
    const matched = preview.path[0] && matchOverviewRoute(candidate, preview.path[0]);
    const candidatePreview = matched ? remainingRoutePreview(candidate, matched.progress) : candidate;
    if (sameRemainingRoute(preview, candidatePreview)) {
      // Fresh ETA/tolls for the same remaining route, without applying a replan.
      preview.duration = candidatePreview.duration ?? preview.duration;
      preview.tolls = candidate.tolls; preview.tollCurrency = candidate.tollCurrency;
      continue;
    }
    if (options.some(option => sameRemainingRoute(option.preview, candidatePreview))) continue;
    options.push({ preview: { ...candidatePreview, labels: candidate.labels }, routes: fresh, routeIndex: index, token: freshToken, current: false });
  }
  return options;
}

/** Match the vehicle at selection time, not at the earlier request's origin. */
export function matchOverviewRoute(route: AppRoute, point: Point, heading?: number, speedKmh?: number | null) {
  if (route.path.length < 2 || !point.every(Number.isFinite)) return;
  const match = matchPosition(route, point, 0, true, { heading, speed: (speedKmh ?? 0) / 3.6, accuracy: 0 });
  if (match.distance > 60 || !Number.isFinite(match.progress)) return;
  if (typeof heading === 'number' && (speedKmh ?? 0) > 7) {
    const direction = bearingBetween(route.path[match.index], route.path[match.index + 1]);
    if (Math.abs(((direction - heading + 540) % 360) - 180) > 65) return;
  }
  return match;
}
