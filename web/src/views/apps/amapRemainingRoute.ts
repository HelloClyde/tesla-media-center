import { cumulative, type AppRoute, type Point } from './amapNavigation';

/** One result per continuous path section; route breaks are never joined. */
export function remainingRouteSections(route: AppRoute, progress: number): Point[][] {
  const lengths = cumulative(route);
  const ends = [0, ...route.breaks, route.path.length];
  const sections: Point[][] = [];
  for (let section = 1; section < ends.length; section++) {
    const from = ends[section - 1], to = ends[section];
    if (to - from < 2) continue;
    if (progress <= lengths[from]) { sections.push(route.path.slice(from, to)); continue; }
    if (progress >= lengths[to - 1]) { sections.push([]); continue; }
    let index = from + 1;
    while (index < to && lengths[index] <= progress) index++;
    const start = route.path[index - 1], end = route.path[index];
    const fraction = (progress - lengths[index - 1]) / (lengths[index] - lengths[index - 1]);
    sections.push([[start[0] + (end[0] - start[0]) * fraction,
      start[1] + (end[1] - start[1]) * fraction], ...route.path.slice(index, to)]);
  }
  return sections;
}
