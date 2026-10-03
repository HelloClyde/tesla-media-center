import { matchPosition, meters, type AppRoute, type Point } from './amapNavigation';
import { bearingBetween } from './amapHeading';

export type RoadKind = 'main' | 'side' | 'elevated' | 'ground';

function roadAt(route: AppRoute, point: Point) {
  const match = matchPosition(route, point, 0, true);
  const step = route.steps.find(step => step.start <= match.index && step.end >= match.index);
  return { ...match, name: step?.road || '' };
}

function roadKind(name: string, axis: 'parallel' | 'level'): RoadKind | undefined {
  if (axis === 'parallel') {
    if (/辅路|辅道/.test(name)) return 'side';
    if (/主路|主道/.test(name)) return 'main';
  } else {
    if (/桥下|高架下|地面/.test(name)) return 'ground';
    if (/高架|桥上/.test(name)) return 'elevated';
  }
}

/** Only select a nearby, distinguishable alternative; GPS alone cannot identify stacked roads. */
export function findParallelRoute(routes: AppRoute[], previous: AppRoute, point: Point, target: RoadKind): number {
  const axis = target === 'main' || target === 'side' ? 'parallel' : 'level';
  const before = roadAt(previous, point);
  const beforeKind = roadKind(before.name, axis);
  if (beforeKind === target) return -1;
  let best = -1, bestScore = Infinity;
  for (let index = 0; index < routes.length; index++) {
    const candidate = roadAt(routes[index], point);
    if (candidate.distance > 40) continue;
    const currentHeading = bearingBetween(previous.path[before.index], previous.path[before.index + 1]);
    const candidateHeading = bearingBetween(routes[index].path[candidate.index], routes[index].path[candidate.index + 1]);
    if (Math.abs(((candidateHeading - currentHeading + 540) % 360) - 180) > 65) continue;
    const kind = roadKind(candidate.name, axis);
    // An unlabelled main/ground road is only meaningful beside a labelled
    // side/elevated road. Never infer a road layer from coordinates alone.
    const inferred = axis === 'parallel' ? beforeKind === 'side' && target === 'main' && !kind
      : beforeKind === 'elevated' && target === 'ground' && !kind;
    if (kind !== target && !inferred) continue;
    if (candidate.name === before.name && meters(candidate.point, before.point) < 3) continue;
    if (candidate.distance < bestScore) { bestScore = candidate.distance; best = index; }
  }
  return best;
}
