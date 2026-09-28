import { defineStore } from 'pinia';
import { ref } from 'vue';
export class GeoLocation {
  accuracy=0; altitude: number|null=null; altitudeAccuracy: number|null=null;
  heading: number|null=null; latitude=0; longitude=0; speed: number|null=null;
  timestamp=0; source: 'gps'|'mock'='gps';
}
export const useGeoLocationStore=defineStore('geoLocation',()=>{
  const positionList=ref<GeoLocation[]>([]);
  const listeners=new Map<string,(pos:GeoLocation)=>void>();
  const errors=new Map<string,(error:GeolocationPositionError)=>void>();
  let initialized=false, requesting=false, generation=0, mode='gps';
  const mockPosList:GeoLocation[]=[];
  function publish(pos:GeoLocation) {
    if (!Number.isFinite(pos.latitude)||!Number.isFinite(pos.longitude)||Math.abs(pos.latitude)>90||Math.abs(pos.longitude)>180) return;
    // Do not discard stationary fixes: timestamps, heading and accuracy can change.
    positionList.value.unshift(pos);positionList.value=positionList.value.slice(0,100);
    listeners.forEach(callback=>callback(pos));
  }
  function refresh() {
    if(mode==='mock') { const pos=mockPosList[mockPosList.length-1];if(pos)publish({...pos,source:'mock'});return; }
    if(requesting||!navigator.geolocation)return;
    requesting=true;const id=++generation;
    const watchdog=setTimeout(()=>{if(id===generation){requesting=false;generation++;}},12000);
    const finish=()=>{clearTimeout(watchdog);requesting=false;};
    try { navigator.geolocation.getCurrentPosition(pos=>{
      if(id!==generation)return;finish();
      const c=pos.coords;
      publish({accuracy:c.accuracy,altitude:c.altitude,altitudeAccuracy:c.altitudeAccuracy,heading:c.heading,latitude:c.latitude,longitude:c.longitude,speed:c.speed,timestamp:pos.timestamp,source:'gps'});
    },error=>{if(id!==generation)return;finish();errors.forEach(callback=>callback(error));},
    {enableHighAccuracy:false,maximumAge:2000,timeout:10000}); }catch {finish();}
  }
  function init(){if(initialized)return;initialized=true;refresh();setInterval(refresh,1000);}
  return {positionList,init,refresh,getCurPosition:()=>positionList.value[0],
    addListener:(name:string,callback:(pos:GeoLocation)=>void)=>listeners.set(name,callback),
    addErrorListener:(name:string,callback:(error:GeolocationPositionError)=>void)=>errors.set(name,callback),
    removeListener:(name:string)=>{listeners.delete(name);errors.delete(name);},
    switchMode:(value:string)=>{mode=value;},addMockPos:(pos:GeoLocation)=>mockPosList.push(pos)};
});
