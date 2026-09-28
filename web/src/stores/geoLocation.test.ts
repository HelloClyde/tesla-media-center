import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {createPinia,setActivePinia} from 'pinia';
import {useGeoLocationStore} from './geoLocation';
let request:ReturnType<typeof vi.fn>;
beforeEach(()=>{vi.useFakeTimers();setActivePinia(createPinia());request=vi.fn();vi.stubGlobal('navigator',{geolocation:{getCurrentPosition:request}});});
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals();});
const fix=(timestamp:number)=>({timestamp,coords:{latitude:30,longitude:120,accuracy:1,altitude:null,altitudeAccuracy:null,heading:0,speed:0}});
it('shares real timestamps and stationary fixes without overlapping requests',()=>{
 const s=useGeoLocationStore(), listener=vi.fn();s.addListener('map',listener);s.init();vi.advanceTimersByTime(3000);expect(request).toHaveBeenCalledTimes(1);
 expect(request.mock.calls[0][2]).toEqual({ maximumAge: 0, timeout: 10000 });request.mock.calls[0][0](fix(100));expect(s.getCurPosition().timestamp).toBe(100);
 vi.advanceTimersByTime(1000);request.mock.calls[1][0](fix(200));expect(listener).toHaveBeenCalledTimes(2);expect(s.getCurPosition().timestamp).toBe(200);
 s.removeListener('map');s.refresh();request.mock.calls[2][0](fix(300));expect(listener).toHaveBeenCalledTimes(2);
});
it('accepts a delayed fix but rejects older requests after a newer success',()=>{
 const s=useGeoLocationStore();s.init();vi.advanceTimersByTime(13000);expect(request).toHaveBeenCalledTimes(2);
 request.mock.calls[0][0](fix(100));expect(s.getCurPosition().timestamp).toBe(100);request.mock.calls[1][0](fix(200));request.mock.calls[0][0](fix(150));expect(s.getCurPosition().timestamp).toBe(200);
});
it('keeps mock fixes distinguishable from real GPS',()=>{const s=useGeoLocationStore();s.switchMode('mock');s.addMockPos({...fix(100).coords,timestamp:100,source:'gps'});s.refresh();expect(s.getCurPosition().source).toBe('mock');});

it('retries after transient browser errors and a silent request timeout',()=>{
 const s=useGeoLocationStore(), listener=vi.fn(), errors=vi.fn();
 s.addListener('map',listener);s.addErrorListener('map',errors);s.init();
 request.mock.calls[0][1]({code:3});vi.advanceTimersByTime(1000);
 expect(request).toHaveBeenCalledTimes(2);
 vi.advanceTimersByTime(13000);
 expect(request).toHaveBeenCalledTimes(3);
 request.mock.calls[2][0](fix(Date.now()));
 expect(listener).toHaveBeenCalledTimes(1);expect(errors).toHaveBeenCalledTimes(1);
});
