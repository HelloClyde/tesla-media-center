import { defineStore } from 'pinia'
import { ref } from 'vue'

export class GeoLocation {
  accuracy: number = 0;
  altitude: number | null = null;
  altitudeAccuracy: number | null = null;
  heading: number | null = null;
  latitude: number = 0;
  longitude: number = 0;
  speed: number | null = null;
  timestamp: number = 0;
}

export const useGeoLocationStore = defineStore('geoLocation', () => {
  const initState = ref(false);
  const positionList = ref<Array<GeoLocation>>([]);
  const listeners = {} as any;
  let mode = 'gps';
  const mockPosList = [] as Array<GeoLocation>;
  const myWindow = window as any;

  function getCurPosition(): GeoLocation {
    return positionList.value[0];
  }

  function positionConverter(src: GeolocationPosition): GeoLocation {
    const ret = new GeoLocation();
    ret.accuracy = src.coords.accuracy;
    ret.altitude = src.coords.altitude;
    ret.altitudeAccuracy = src.coords.altitudeAccuracy;
    ret.heading = src.coords.heading;
    ret.latitude = src.coords.latitude;
    ret.longitude = src.coords.longitude;
    ret.speed = src.coords.speed;
    ret.timestamp = new Date().getTime();

    return ret;
  }

  function addListener(name: string, callback: (pos: GeoLocation) => void) {
    listeners[name] = callback;
  }

  function removeListener(name: string) {
    listeners[name] = null;
  }

  function switchMode(runMode: string) {
    mode = runMode;
  }

  function addMockPos(pos: GeoLocation) {
    mockPosList.push(pos);
  }

  function posUpdateCallBack(geo: GeoLocation) {
    // const geo = positionConverter(position)

    // 计算精度
    let needPush = true;
    if (myWindow.AMap) {
      const lastGeo = positionList.value.length == 0 ? null : positionList.value[0];
      if (lastGeo != null) {
        const dist = myWindow.AMap.GeometryUtil.distance([geo.longitude, geo.latitude], [lastGeo.longitude, lastGeo.latitude]);
        if (geo.accuracy > dist) {
          needPush = false;
        }
      }
    }

    if (needPush) {
      positionList.value.unshift(geo);
      positionList.value = positionList.value.slice(0, 100);
      console.debug('updated position', geo);

      console.debug('listeners', listeners);
      for (const name in listeners) {
        const callback = listeners[name];
        if (callback) {
          callback(geo);
        }
      }
    }
  }


  function init() {
    // 初始化 
    if (!initState.value) {
      console.info('start fix rate to get position');
      setInterval(() => {
        console.debug('position start to refresh.');
        if (mode === 'gps') {
          navigator.geolocation.getCurrentPosition((position) => {
            posUpdateCallBack(positionConverter(position))
          });
        } else if (mode === 'mock') {
          if (mockPosList.length != 0) {
            posUpdateCallBack(mockPosList[mockPosList.length - 1])
          }
        }

      }, 1000);
      initState.value = true;
    } else {
      console.info('is inited, ignore');
    }
  };


  // 通过返回值暴露所管理的状态
  return {
    positionList,
    getCurPosition,
    init,
    addListener,
    removeListener,
    switchMode,
    addMockPos
  }
})
