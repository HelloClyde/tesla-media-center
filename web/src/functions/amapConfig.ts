import AMapLoader from '@amap/amap-jsapi-loader';
import { get } from '@/functions/requests'

export default function getAMap(): Promise<any> {
    return get(`/api/config`)
        .then(data => {
          const key = String(data?.amap_key || '').trim();
          if (!key) throw new Error('请先在调试页设置高德 JS API Key');
          const securityCode = String(data?.amap_security_js_code || '').trim();
          if (securityCode) (window as any)._AMapSecurityConfig = { securityJsCode: securityCode };
          const amap_config = {
            "key": key,              // 申请好的Web端开发者Key，首次调用 load 时必填
            "version": "2.1Beta",
            "plugins": ['AMap.Scale', 'AMap.ToolBar', 'AMap.ControlBar', 'AMap.MoveAnimation', 'AMap.Driving', 'AMap.AutoComplete', 'AMap.Geocoder', 'AMap.Weather'],
            "Loca": {                // 是否加载 Loca， 缺省不加载
              "version": '2.0.0'
            }
          };

          return AMapLoader.load(amap_config);
        });
}
