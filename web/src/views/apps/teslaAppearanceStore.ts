import { normalizeAppearance, type VehicleAppearance } from './teslaAppearance';
import type { VehicleSkinVariant } from './teslaVehicleSkin';

export type VehicleAppearanceRecord = { appearance: VehicleAppearance; manualModel: VehicleSkinVariant | null };
export type TeslaSceneSettings = { weatherMode: 'auto' | 'clear' | 'cloudy' | 'rain' | 'fog' | 'snow'; sceneNight: boolean };
const url = (vin: string) => `/api/tesla/appearance/${encodeURIComponent(vin || 'default')}`;

async function checked(response: Response): Promise<any> {
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status !== 'ok') throw new Error(body?.message || '车辆外观设置请求失败');
  return body.data;
}

export async function readAppearance(vin: string): Promise<VehicleAppearanceRecord | null> {
  const response = await fetch(url(vin), { credentials: 'same-origin', cache: 'no-store' });
  if (response.status === 204) return null;
  const data = await checked(response);
  return { appearance: normalizeAppearance(data.appearance), manualModel: data.manualModel || null };
}

export async function saveAppearance(vin: string, record: VehicleAppearanceRecord, onlyIfMissing = false): Promise<boolean> {
  const response = await fetch(url(vin), {
    method: 'PUT', credentials: 'same-origin', headers: {
      'Content-Type': 'application/json', ...(onlyIfMissing ? { 'If-None-Match': '*' } : {}),
    }, body: JSON.stringify(record),
  });
  if (onlyIfMissing && response.status === 412) return false;
  await checked(response);
  return true;
}

export async function readSelectedVehicle(): Promise<string> {
  const response = await fetch('/api/tesla/appearance/selection', { credentials: 'same-origin', cache: 'no-store' });
  return (await checked(response)).selectedVin || '';
}

export async function saveSelectedVehicle(vin: string, onlyIfMissing = false): Promise<boolean> {
  const response = await fetch('/api/tesla/appearance/selection', {
    method: 'PUT', credentials: 'same-origin', headers: {
      'Content-Type': 'application/json', ...(onlyIfMissing ? { 'If-None-Match': '*' } : {}),
    }, body: JSON.stringify({ selectedVin: vin }),
  });
  if (onlyIfMissing && response.status === 412) return false;
  await checked(response);
  return true;
}

export async function readSceneSettings(): Promise<TeslaSceneSettings | null> {
  const response = await fetch('/api/tesla/appearance/scene', { credentials: 'same-origin', cache: 'no-store' });
  return response.status === 204 ? null : checked(response);
}

export async function saveSceneSettings(settings: TeslaSceneSettings, onlyIfMissing = false): Promise<boolean> {
  const response = await fetch('/api/tesla/appearance/scene', {
    method: 'PUT', credentials: 'same-origin', headers: {
      'Content-Type': 'application/json', ...(onlyIfMissing ? { 'If-None-Match': '*' } : {}),
    }, body: JSON.stringify(settings),
  });
  if (onlyIfMissing && response.status === 412) return false;
  await checked(response);
  return true;
}
