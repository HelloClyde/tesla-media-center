import type { AppRoute } from './amapNavigation';

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
