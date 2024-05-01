import axios from 'axios';
import AMapLoader from '@amap/amap-jsapi-loader';
import { get } from '@/functions/requests'

export default function getAMap(): Promise<any> {
    return get(`/api/config`)
        .then(data => {
          const amap_config = {
            "key": data['amap_key'],              // 申请好的Web端开发者Key，首次调用 load 时必填
            "version": "2.1Beta", 
            "plugins": ['AMap.Scale', 'AMap.ToolBar', 'AMap.ControlBar', 'AMap.MoveAnimation', 'AMap.Driving', 'AMap.AutoComplete'],           // 需要使用的的插件列表，如比例尺'AMap.Scale'等
            "Loca": {                // 是否加载 Loca， 缺省不加载
              "version": '2.0.0'
            }
          };

          return AMapLoader.load(amap_config);
        });
}