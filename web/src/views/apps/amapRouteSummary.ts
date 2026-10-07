import { cumulative, type AppRoute } from './amapNavigation';

/** The App supplies a total planned duration. Until per-link ETA is available,
 * estimate the remainder from measured route progress, not instantaneous speed
 * (which becomes zero at signals) or the simulation's playback multiplier. */
export function remainingRouteDuration(route: AppRoute, progress: number): number | null {
  if (typeof route.duration !== 'number' || !Number.isFinite(route.duration) || route.duration <= 0
      || !Number.isFinite(progress) || route.path.length < 2) return null;
  const lengths = cumulative(route), total = lengths[lengths.length - 1];
  if (!Number.isFinite(total) || total <= 0) return null;
  return route.duration * (1 - Math.max(0, Math.min(total, progress)) / total);
}

export function formatRemainingDuration(seconds?: number | null) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return '时间待确认';
  return seconds < 60 ? '不足 1 分钟' : formatRouteDuration(seconds);
}

export function formatRouteDuration(seconds?: number | null) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return '用时待确认';
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  const hours = Math.floor(minutes / 60), rest = minutes % 60;
  return hours ? `约 ${hours} 小时${rest ? ` ${rest} 分钟` : ''}` : `约 ${minutes} 分钟`;
}

export function formatRouteTolls(route: Pick<AppRoute, 'tolls' | 'tollCurrency'>) {
  if (route.tollCurrency !== 'CNY' || typeof route.tolls !== 'number' || !Number.isFinite(route.tolls) || route.tolls < 0) return '收费待确认';
  return route.tolls === 0 ? '不收费' : `预计收费 ¥${Number(route.tolls.toFixed(2))}`;
}
