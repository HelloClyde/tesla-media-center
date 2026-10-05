import laneAssets from './amapLaneAssets.json';

export interface LaneGuideVariant {
  startHour: number;
  endHour: number;
  back: number[];
  front: number[];
}

export interface LaneGuide {
  at: number;
  variants: LaneGuideVariant[];
}

export interface UpcomingLaneGuide {
  at: number;
  distance: number;
  variant: LaneGuideVariant;
}

/** The NCP lane event is anchored to a route distance, not a map tile. */
export function upcomingLaneGuide(guides: LaneGuide[] | undefined, progress: number,
  hour = new Date().getHours(), horizon = 450): UpcomingLaneGuide | undefined {
  if (!Array.isArray(guides) || !Number.isFinite(progress)) return;
  let upcoming: UpcomingLaneGuide | undefined;
  for (const guide of guides) {
    if (!Number.isFinite(guide.at)) continue;
    const distance = guide.at - progress;
    if (distance < -20 || distance > horizon) continue;
    const variant = guide.variants?.find(value => value.startHour <= hour && hour < value.endHour
      && value.back.length === value.front.length && value.back.length > 0);
    if (variant && (!upcoming || distance < upcoming.distance))
      upcoming = { at: guide.at, distance: Math.max(0, distance), variant };
  }
  return upcoming;
}

export function laneArrowAsset(back: number, front: number): string | undefined {
  return (laneAssets.front as Record<string, string>)[`${back}_${front}`]
    ?? (laneAssets.back as Record<string, string>)[String(back)];
}
