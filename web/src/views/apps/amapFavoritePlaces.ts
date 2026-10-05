import type { Place } from './amapSearch';

const storageKey = 'tmc.amap.favorite-places.v1';
const maxFavorites = 100;

type FavoriteStorage = Pick<Storage, 'getItem' | 'removeItem'>;

function browserStorage(): FavoriteStorage | undefined {
  try { return typeof window === 'undefined' ? undefined : window.localStorage; }
  catch { return undefined; }
}

function point(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2
    && value.every((coordinate: unknown) => typeof coordinate === 'number' && Number.isFinite(coordinate))
    && Math.abs(value[0]) <= 180 && Math.abs(value[1]) <= 85;
}

function place(value: unknown): Place | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.id !== 'string' || !candidate.id.trim()
      || typeof candidate.name !== 'string' || !candidate.name.trim()
      || !point(candidate.location)) return;
  return {
    id: candidate.id.trim(), name: candidate.name.trim(),
    address: typeof candidate.address === 'string' ? candidate.address.trim() : '',
    location: [candidate.location[0], candidate.location[1]],
    ...(point(candidate.entrance) ? { entrance: [candidate.entrance[0], candidate.entrance[1]] as [number, number] } : {}),
  };
}

/** Read favorites saved by the earlier browser-only build for one-time import. */
export function loadBrowserFavoritePlaces(storage: FavoriteStorage | undefined = browserStorage()): Place[] {
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(storageKey) || '[]');
    if (!Array.isArray(parsed)) return [];
    const ids = new Set<string>();
    const favorites: Place[] = [];
    for (const value of parsed) {
      const favorite = place(value);
      if (!favorite || ids.has(favorite.id)) continue;
      ids.add(favorite.id);
      favorites.push(favorite);
      if (favorites.length === maxFavorites) break;
    }
    return favorites;
  } catch { return []; }
}

export function clearBrowserFavoritePlaces(storage: FavoriteStorage | undefined = browserStorage()): boolean {
  try {
    if (!storage) return false;
    storage.removeItem(storageKey);
    return true;
  } catch { return false; }
}
