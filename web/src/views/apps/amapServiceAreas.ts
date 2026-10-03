import { cumulative, type AppRoute } from './amapNavigation';

export interface UpcomingServiceArea {
  name: string;
  key: string;
  from: number;
  to: number;
  distance: number;
}

/** The App route identifies a service-area road segment, not its entrance. */
export function upcomingServiceAreas(route: AppRoute | undefined, progress: number, limit = 2): UpcomingServiceArea[] {
  if (!route || !Number.isFinite(progress)) return [];
  const lengths = cumulative(route), areas: UpcomingServiceArea[] = [];
  for (const step of route.steps) {
    if (!step.serviceArea || !step.serviceArea.endsWith('服务区') && !step.serviceArea.endsWith('停车区')) continue;
    const from = lengths[step.start], to = lengths[step.end];
    if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) continue;
    const previous = areas[areas.length - 1];
    if (previous?.name === step.serviceArea && from <= previous.to + 100) {
      previous.to = Math.max(previous.to, to);
      previous.distance = Math.max(0, (previous.from + previous.to) / 2 - progress);
      continue;
    }
    areas.push({ name: step.serviceArea, key: `${step.start}/${step.serviceArea}`,
      from, to, distance: Math.max(0, (from + to) / 2 - progress) });
  }
  return areas.filter(area => area.to > progress).slice(0, Math.max(0, limit));
}

export function shouldAnnounceServiceArea(area: UpcomingServiceArea, progress: number, turnDistance: number): boolean {
  // The exact entrance is unknown. Warn before the annotated segment, without
  // claiming an exact arrival distance or interrupting an imminent turn.
  return area.from - progress <= 5000 && area.from - progress >= -300 &&
    area.to > progress && turnDistance > 800;
}
