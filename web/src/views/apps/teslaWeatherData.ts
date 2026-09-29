export type SceneWeather = 'clear' | 'cloudy' | 'rain' | 'fog' | 'snow';
export const weatherLabels: Record<SceneWeather,string> = {clear:'晴天',cloudy:'阴天',rain:'下雨',fog:'雾天',snow:'下雪'};
export function weatherFromCode(code:number):SceneWeather {
  if ([71,73,75,77,85,86].includes(code)) return 'snow';
  if ([45,48].includes(code)) return 'fog';
  if ([51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99].includes(code)) return 'rain';
  if ([1,2,3].includes(code)) return 'cloudy';
  return 'clear';
}
export async function fetchVehicleWeather(latitude:number,longitude:number,signal:AbortSignal):Promise<SceneWeather> {
  if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180)throw Error('车辆位置无效');
  const query=new URLSearchParams({latitude:latitude.toFixed(2),longitude:longitude.toFixed(2),current:'weather_code',forecast_days:'1'});
  const response=await fetch(`https://api.open-meteo.com/v1/forecast?${query}`,{signal});
  if(!response.ok)throw Error('天气服务暂不可用');
  const data=await response.json();
  if(typeof data.current?.weather_code!=='number')throw Error('天气数据无效');
  return weatherFromCode(data.current.weather_code);
}
