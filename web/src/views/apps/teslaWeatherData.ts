import { wgs84togcj02 } from 'coordtransform';
import getAMap from '@/functions/amapConfig';

export type SceneWeather = 'clear' | 'cloudy' | 'rain' | 'fog' | 'snow';
export const weatherLabels: Record<SceneWeather, string> = {
  clear: '晴天', cloudy: '阴天', rain: '下雨', fog: '雾天', snow: '下雪',
};

export function weatherFromDescription(description: string): SceneWeather {
  const value = description.trim();
  if (/雪|冰粒/.test(value)) return 'snow';
  if (/雨|雷|冰雹/.test(value)) return 'rain';
  if (/雾|霾|沙尘|浮尘|扬沙/.test(value)) return 'fog';
  if (/多云|阴/.test(value)) return 'cloudy';
  if (/晴/.test(value)) return 'clear';
  throw new Error('高德天气数据无法识别');
}

function awaitAmapCallback<T>(signal: AbortSignal, start: (finish: (error: Error | null, value?: T) => void) => void): Promise<T> {
  if (signal.aborted) return Promise.reject(new DOMException('天气查询已取消', 'AbortError'));
  return new Promise((resolve, reject) => {
    const abort = () => finish(new DOMException('天气查询已取消', 'AbortError'));
    const finish = (error: Error | null, value?: T) => {
      signal.removeEventListener('abort', abort);
      if (error) reject(error);
      else resolve(value as T);
    };
    signal.addEventListener('abort', abort, { once: true });
    try { start(finish); }
    catch (error) { finish(error instanceof Error ? error : new Error('高德天气服务不可用')); }
  });
}

export async function fetchVehicleWeather(latitude: number, longitude: number, signal: AbortSignal, coordType = ''): Promise<SceneWeather> {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
    throw new Error('车辆位置无效');
  }
  const AMap = await awaitAmapCallback<any>(signal, finish => {
    void getAMap().then(map => finish(null, map), error => {
      finish(error instanceof Error ? error : new Error('高德天气服务不可用'));
    });
  });
  const isGcj = ['gcj', 'gcj02', 'gcj-02'].includes(coordType.toLowerCase());
  const point = isGcj ? [longitude, latitude] : wgs84togcj02(longitude, latitude);
  const adcode = await awaitAmapCallback<string>(signal, finish => {
    new AMap.Geocoder({ extensions: 'base' }).getAddress(point, (status: string, result: any) => {
      const code = result?.regeocode?.addressComponent?.adcode;
      if (status !== 'complete' || !/^\d{6}$/.test(String(code || ''))) {
        finish(new Error('高德无法识别车辆所在地区'));
      } else finish(null, String(code));
    });
  });
  const description = await awaitAmapCallback<string>(signal, finish => {
    new AMap.Weather().getLive(adcode, (error: unknown, data: any) => {
      if (error || typeof data?.weather !== 'string' || !data.weather.trim()) {
        finish(new Error('高德实时天气暂不可用'));
      } else finish(null, data.weather);
    });
  });
  return weatherFromDescription(description);
}
