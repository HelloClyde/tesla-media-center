import { describe,it,expect,vi,afterEach } from 'vitest';
import { weatherFromCode,fetchVehicleWeather } from './teslaWeatherData';
afterEach(()=>vi.unstubAllGlobals());
describe('vehicle weather',()=>{
 it('maps freezing precipitation, snow showers, fog and thunderstorms',()=>{
  for(const code of [56,57,66,67,95,96,99])expect(weatherFromCode(code)).toBe('rain');
  for(const code of [71,73,75,77,85,86])expect(weatherFromCode(code)).toBe('snow');
  expect(weatherFromCode(48)).toBe('fog');expect(weatherFromCode(3)).toBe('cloudy');expect(weatherFromCode(0)).toBe('clear');
 });
 it('rejects missing weather and failed service instead of reporting sunshine',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({current:{}})}));
  await expect(fetchVehicleWeather(30,120,new AbortController().signal)).rejects.toThrow('天气数据无效');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false}));
  await expect(fetchVehicleWeather(30,120,new AbortController().signal)).rejects.toThrow('天气服务');
 });
 it('uses a rounded position and passes cancellation',async()=>{
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({current:{weather_code:75}})});vi.stubGlobal('fetch',fetch);
  const signal=new AbortController().signal;
  expect(await fetchVehicleWeather(30.26789,120.15123,signal)).toBe('snow');
  expect(fetch.mock.calls[0][0]).toContain('latitude=30.27&longitude=120.15');expect(fetch.mock.calls[0][1].signal).toBe(signal);
 });
});
