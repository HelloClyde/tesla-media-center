import { afterEach, describe, expect, it, vi } from 'vitest';
import { wgs84togcj02 } from 'coordtransform';
import getAMap from '@/functions/amapConfig';
import { fetchVehicleWeather, weatherFromDescription } from './teslaWeatherData';

vi.mock('@/functions/amapConfig', () => ({ default: vi.fn() }));
afterEach(() => vi.clearAllMocks());

describe('Tesla vehicle weather from AMap', () => {
  it('maps live weather descriptions without guessing unknown conditions', () => {
    expect(weatherFromDescription('晴')).toBe('clear');
    expect(weatherFromDescription('晴转多云')).toBe('cloudy');
    expect(weatherFromDescription('阴')).toBe('cloudy');
    expect(weatherFromDescription('雷阵雨伴有冰雹')).toBe('rain');
    expect(weatherFromDescription('雨夹雪')).toBe('snow');
    expect(weatherFromDescription('轻雾')).toBe('fog');
    expect(() => weatherFromDescription('未知')).toThrow('无法识别');
  });

  it('reverse geocodes the vehicle position and queries AMap live weather by adcode', async () => {
    const getAddress = vi.fn((_point, callback) => callback('complete', { regeocode: { addressComponent: { adcode: '330106' } } }));
    const getLive = vi.fn((_adcode, callback) => callback(null, { weather: '多云' }));
    vi.mocked(getAMap).mockResolvedValue({
      Geocoder: class { getAddress = getAddress; },
      Weather: class { getLive = getLive; },
    });
    const signal = new AbortController().signal;
    expect(await fetchVehicleWeather(30.27, 120.15, signal)).toBe('cloudy');
    expect(getAddress.mock.calls[0][0]).toEqual(wgs84togcj02(120.15, 30.27));
    expect(getLive.mock.calls[0][0]).toBe('330106');
    expect(await fetchVehicleWeather(30.27, 120.15, signal, 'gcj02')).toBe('cloudy');
    expect(getAddress.mock.calls[1][0]).toEqual([120.15, 30.27]);
  });

  it('rejects invalid coordinates, missing district codes and failed weather lookups', async () => {
    const getAddress = vi.fn((_point, callback) => callback('complete', { regeocode: { addressComponent: {} } }));
    const getLive = vi.fn((_adcode, callback) => callback({ info: 'ERROR' }, null));
    vi.mocked(getAMap).mockResolvedValue({
      Geocoder: class { getAddress = getAddress; },
      Weather: class { getLive = getLive; },
    });
    const signal = new AbortController().signal;
    await expect(fetchVehicleWeather(100, 120, signal)).rejects.toThrow('车辆位置无效');
    await expect(fetchVehicleWeather(30, 120, signal)).rejects.toThrow('无法识别车辆所在地区');
    getAddress.mockImplementation((_point, callback) => callback('complete', { regeocode: { addressComponent: { adcode: '330106' } } }));
    await expect(fetchVehicleWeather(30, 120, signal)).rejects.toThrow('实时天气暂不可用');
    const cancelled = new AbortController();
    cancelled.abort();
    await expect(fetchVehicleWeather(30, 120, cancelled.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('stops waiting if the AMap SDK is still loading when the request is cancelled', async () => {
    vi.mocked(getAMap).mockImplementation(() => new Promise(() => undefined));
    const controller = new AbortController();
    const pending = fetchVehicleWeather(30, 120, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
