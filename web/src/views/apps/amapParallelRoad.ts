import { matchPosition, meters, type AppRoute, type Point, type RoadLink } from './amapNavigation';
import { bearingBetween } from './amapHeading';

export type RoadKind = 'main' | 'side' | 'elevated' | 'ground' | 'tunnel';
export const roadKindLabels: Record<RoadKind, string> = { main: '主路', side: '辅路', elevated: '高架', ground: '地面', tunnel: '隧道' };

export function matchRoadLink(route: AppRoute, point: Point, progress?: number) {
  const match = matchPosition(route, point, progress ?? 0, progress === undefined);
  // Shared step endpoints belong to the outgoing road once the vehicle reaches
  // them. An inclusive end would keep reporting the previous road's level.
  const index = match.point && route.path[match.index + 1] && meters(match.point, route.path[match.index + 1]) < .1
    ? match.index + 1 : match.index;
  const step = route.steps.find(step => step.start <= index && step.end > index)
    ?? (index === route.path.length - 1 ? route.steps[route.steps.length - 1] : undefined);
  const link = route.roadLinks?.find(link => link.start <= index && link.end > index)
    ?? (index === route.path.length - 1 ? route.roadLinks?.slice(-1)[0] : undefined);
  return { ...match, index: Math.min(index, route.path.length - 2), name: link ? link.road : step?.road || '', link };
}

/** libamaploc AutoBL getParallelLinkType's property branch, after eligibility.
 * This classifies a link; it does not reproduce the native candidate/MM gate.
 */
export function parallelRoadProperty(property: number | undefined): 'main' | 'side' | undefined {
  if (property === 1 || property === 3 || property === 6 || property === 8) return 'main';
  if (property === 5 || property === 7) return 'side';
}

function roadKind(name: string, axis: 'parallel' | 'level', link?: RoadLink): RoadKind | undefined {
  if (axis === 'parallel') {
    const nativeKind = parallelRoadProperty(link?.roadProperty);
    if (nativeKind) return nativeKind;
    if (/辅路|辅道/.test(name)) return 'side';
    if (/主路|主道/.test(name)) return 'main';
  } else {
    // APK ELinkType: COMMON=0, FERRY=1, TUNNEL=2, BRIDGE=3, ELEVATED_RD=4.
    // RouteLink.getLinkType reads this per-link attribute. It is independent
    // of LocParallelRoadInfo.hwFlag and does not identify the vehicle's floor.
    if (link?.linkType !== undefined) {
      if (link.linkType === 0) return 'ground';
      if (link.linkType === 2) return 'tunnel';
      if (link.linkType === 3 || link.linkType === 4) return 'elevated';
      return undefined;
    }
    if (/桥下|高架下|地面|隧道上方/.test(name)) return 'ground';
    if (/隧道|地道|地下道路|地下通道|下穿通道/.test(name)) return 'tunnel';
    if (/高架|桥上/.test(name)) return 'elevated';
  }
}

/** Direct, target-labelled shortcuts, following the APK's separate axes.
 * Route classification is not the APK's MM availability event. Unknown axes
 * are offered only when an existing nearby candidate confirms a target.
 */
export function directRoadSwitchTargets(route: AppRoute, point: Point, candidates: AppRoute[], progress?: number): RoadKind[] {
  if (route.path.length < 2 || !point.every(Number.isFinite)) return [];
  const current = matchRoadLink(route, point, progress);
  const parallel = roadKind(current.name, 'parallel', current.link);
  const level = roadKind(current.name, 'level', current.link);
  const targets: RoadKind[] = [];
  if (parallel === 'main') targets.push('side');
  else if (parallel === 'side') targets.push('main');
  else for (const target of ['main', 'side'] as const) {
    if (findParallelRoute(candidates, route, point, target, progress) >= 0) targets.push(target);
  }
  if (level === 'elevated' || level === 'tunnel') targets.push('ground');
  else {
    const confirmed = (['elevated', 'tunnel'] as const)
      .filter(target => findParallelRoute(candidates, route, point, target, progress) >= 0);
    targets.push(...(confirmed.length || level !== 'ground' ? confirmed : ['elevated', 'tunnel'] as const));
  }
  return targets;
}

/** Only select a nearby, distinguishable alternative; GPS alone cannot identify stacked roads. */
export function findParallelRoute(routes: AppRoute[], previous: AppRoute, point: Point, target: RoadKind, progress?: number): number {
  if (previous.path.length < 2 || !point.every(Number.isFinite)) return -1;
  const axis = target === 'main' || target === 'side' ? 'parallel' : 'level';
  const before = matchRoadLink(previous, point, progress);
  const beforeKind = roadKind(before.name, axis, before.link);
  if (beforeKind === target) return -1;
  let best = -1, bestScore = Infinity;
  for (let index = 0; index < routes.length; index++) {
    if (routes[index].path.length < 2) continue;
    const candidate = matchRoadLink(routes[index], point);
    if (candidate.distance > 40) continue;
    // A new route/session can still be on the very same native link. Names,
    // geometry jitter and the route index must never turn that into a switch.
    if (candidate.link?.id && candidate.link.id === before.link?.id) continue;
    const currentHeading = bearingBetween(previous.path[before.index], previous.path[before.index + 1]);
    const candidateHeading = bearingBetween(routes[index].path[candidate.index], routes[index].path[candidate.index + 1]);
    if (Math.abs(((candidateHeading - currentHeading + 540) % 360) - 180) > 65) continue;
    const kind = roadKind(candidate.name, axis, candidate.link);
    const named = candidate.name.trim() && !/^(道路|无名道路)$/.test(candidate.name.trim());
    if (!named && !kind) continue;
    // A named ordinary road is a surface alternative beside a labelled tunnel
    // or elevated road. Missing road names do not provide this evidence.
    const inferred = named && (axis === 'parallel'
      ? !candidate.link && beforeKind === 'side' && target === 'main' && !kind
      : candidate.link?.linkType === undefined && (beforeKind === 'elevated' || beforeKind === 'tunnel') && target === 'ground' && !kind);
    if (kind !== target && !inferred) continue;
    const distinctLink = candidate.link?.id && before.link?.id && candidate.link.id !== before.link.id;
    const distinctProperty = axis === 'parallel' && kind && beforeKind && kind !== beforeKind;
    const distinctType = axis === 'level' && candidate.link?.linkType !== undefined && before.link?.linkType !== undefined
      && kind && beforeKind && kind !== beforeKind;
    if (!distinctLink && !distinctProperty && !distinctType && candidate.name === before.name && meters(candidate.point, before.point) < 3) continue;
    if (candidate.distance < bestScore) { bestScore = candidate.distance; best = index; }
  }
  return best;
}
