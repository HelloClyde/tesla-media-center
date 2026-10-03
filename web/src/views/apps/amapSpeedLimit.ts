/** Road limits must come from a verified navigation source, never traffic speed. */
export interface SpeedLimitSection {
  start: number;
  end: number;
  limit: number;
}

/** APK camera event 95 is independent of the current road's section limit. */
export interface SpeedLimitCamera {
  at: number;
  type: 7 | 25 | 26 | 27;
  speed: number[];
}

/** A coordinate-backed sign from App routeguide; it does not define a road section. */
export interface SpeedSignPoint { at: number; limit: number }

export function upcomingSpeedSign(signs: SpeedSignPoint[] | undefined, progress: number, horizon = 2000) {
  if (!Number.isFinite(progress) || !Array.isArray(signs)) return;
  let nearest: { sign: SpeedSignPoint; distance: number } | undefined;
  for (const sign of signs) {
    if (!sign || !Number.isFinite(sign.at) || !Number.isInteger(sign.limit)
        || sign.limit < 5 || sign.limit > 160 || sign.at < progress || sign.at - progress > horizon) continue;
    const distance = sign.at - progress;
    if (!nearest || distance < nearest.distance) nearest = { sign, distance };
  }
  return nearest;
}

export interface SpeedLimitCameraEvent {
  type: 95;
  naviCamera: { type: SpeedLimitCamera['type']; speed: number[]; distance: number }[];
}

export function upcomingSpeedCamera(cameras: SpeedLimitCamera[] | undefined, progress: number, horizon = 2000) {
  if (!Number.isFinite(progress) || !Array.isArray(cameras)) return;
  let nearest: { camera: SpeedLimitCamera; distance: number; limit: number } | undefined;
  for (const camera of cameras) {
    if (!camera || ![7, 25, 26, 27].includes(camera.type) || !Number.isFinite(camera.at)
        || camera.at < progress || camera.at - progress > horizon || !Array.isArray(camera.speed)) continue;
    const speeds = camera.speed.filter(value => Number.isInteger(value) && value >= 5 && value <= 160 && value !== 255);
    if (!speeds.length) continue;
    const distance = camera.at - progress;
    if (!nearest || distance < nearest.distance) nearest = { camera, distance, limit: Math.max(...speeds) };
  }
  return nearest;
}

export function cameraEventAhead(cameras: SpeedLimitCamera[] | undefined, progress: number): SpeedLimitCameraEvent {
  const upcoming = upcomingSpeedCamera(cameras, progress);
  return { type: 95, naviCamera: upcoming ? [{ type: upcoming.camera.type, speed: upcoming.camera.speed, distance: upcoming.distance }] : [] };
}

/** APK NaviEventTypeSpeedLimitSection (452): zero clears an unknown section. */
export interface SpeedLimitSectionEvent {
  type: 452;
  speed: number;
  section?: SpeedLimitSection;
}

function valid(section: SpeedLimitSection): boolean {
  return Number.isFinite(section.start) && Number.isFinite(section.end)
    && Number.isInteger(section.limit) && section.limit >= 5 && section.limit <= 160
    && section.start >= 0 && section.end > section.start;
}

export function speedLimitAt(sections: SpeedLimitSection[] | undefined, progress: number): SpeedLimitSection | undefined {
  if (!Number.isFinite(progress) || !Array.isArray(sections)) return;
  return sections.find(section => valid(section) && progress >= section.start && progress < section.end);
}

export function upcomingSpeedLimit(sections: SpeedLimitSection[] | undefined, progress: number, horizon = 2000) {
  if (!Number.isFinite(progress) || !Array.isArray(sections)) return;
  const section = sections.filter(item => valid(item) && item.start > progress && item.start - progress <= horizon)
    .sort((a, b) => a.start - b.start)[0];
  return section && { section, distance: section.start - progress };
}

/** Recreate the APK's section-entry event from a verified route's distance. */
export function createSpeedLimitSectionEvents() {
  let previous: SpeedLimitSection | undefined;
  return {
    reset() { previous = undefined; },
    update(sections: SpeedLimitSection[] | undefined, progress: number): SpeedLimitSectionEvent | undefined {
      const current = speedLimitAt(sections, progress);
      if (current === previous) return;
      previous = current;
      return { type: 452, speed: current?.limit ?? 0, section: current };
    },
  };
}

/** Apply the App's default 1.1 overspeed factor only to an actual road limit. */
export function isOverSpeed(speed: number | null, limit: number | undefined): boolean {
  return speed !== null && Number.isFinite(speed) && Number.isFinite(limit)
    && limit! > 0 && speed >= limit! * 1.1;
}

export function createSpeedReminder() {
  let section: SpeedLimitSection | undefined;
  let exceededAt = 0;
  let lastSpokenAt = -Infinity;
  return {
    reset() { section = undefined; exceededAt = 0; lastSpokenAt = -Infinity; },
    update(current: SpeedLimitSection | undefined, speed: number | null, now: number): boolean {
      if (current !== section) { section = current; exceededAt = 0; lastSpokenAt = -Infinity; }
      if (!current || !isOverSpeed(speed, current.limit)) { exceededAt = 0; return false; }
      if (!exceededAt) exceededAt = now;
      if (now - exceededAt < 3000 || now - lastSpokenAt < 120000) return false;
      lastSpokenAt = now;
      return true;
    },
  };
}
