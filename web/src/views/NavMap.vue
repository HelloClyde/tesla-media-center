

<script setup lang="ts">
import { reactive } from 'vue'
import { onMounted, onUnmounted, computed } from 'vue'
import { GeoLocation, useGeoLocationStore } from '@/stores/geoLocation';
import carImg from '@/assets/car.png';
import AMapLoader from '@amap/amap-jsapi-loader';
// import { AMapConfig } from '@/config/AMapConfig';
import { Calendar, Search } from '@element-plus/icons-vue'
import { ref, shallowRef } from '@vue/reactivity';
import axios from 'axios';

const postionState = useGeoLocationStore();

let gAMap = shallowRef<any>(null);
let myMap = shallowRef<any>(null);

// 地址搜索
let geoSearch = shallowRef<any>(null);
let driving = shallowRef<any>(null);
let trafficLayer = shallowRef<any>(null);

const state = reactive({
    lastPos: null as (GeoLocation | null),
    search: {
        query: '',
        suggestList: [] as any[],
        focus: false,
    },
    enableFollow: true,
    lowSignal: false,
    showTrafficLayer: true,
})

function searchSuggest(text: string) {
    geoSearch.search(text, (status: any, result: { tips: any[]; }) => {
        console.info(status, result);
        state.search.suggestList = result.tips;
    });
}

function navToSuggestResult(suggestItem: any) {
    console.log('nav to', suggestItem);

    const curGeo = postionState.getCurPosition();

    console.log('path:', [new gAMap.LngLat(curGeo.longitude, curGeo.latitude), suggestItem.location]);

    // 搜索完成后，将自动绘制路线到地图上
    driving.search(new gAMap.LngLat(curGeo.longitude, curGeo.latitude), suggestItem.location, function (status: any, result: any) {
        // 未出错时，result即是对应的路线规划方案
        console.log(status, result);
        state.enableFollow = false;

        console.log('zoom', myMap);
    });

    state.search.focus = false;
}

function changeFollowState() {
    state.enableFollow = !state.enableFollow;
    // console.log('zoom', myMap.getZoom());
    // console.log('enableFollow', state.enableFollow);
    if (state.enableFollow) {
        console.log('zoom', myMap.getZoom());
        myMap.setZoom(17, true);
    }
}

function switchTrafficLayer() {
    if (state.showTrafficLayer) {
        myMap.remove(trafficLayer);
    } else {
        myMap.add(trafficLayer);
    }
    state.showTrafficLayer = !state.showTrafficLayer;
}


onMounted(() => {
    postionState.init();
    let curGeo = postionState.getCurPosition();
    if (!curGeo) {
        curGeo = {
            accuracy: 0,
            altitude: null,
            altitudeAccuracy: null,
            heading: null,
            latitude: 30.2783,
            longitude: 120.2169,
            speed: null,
            timestamp: 11
        }
    }

    axios.get(`/api/config`)
        .then(response => {
            const amap_config = {
                "key": response.data['amap_key'],              // 申请好的Web端开发者Key，首次调用 load 时必填
                "version": "2.1Beta",   // 指定要加载的 JSAPI 的版本，缺省时默认为 1.4.15
                "plugins": ['AMap.Scale', 'AMap.ToolBar', 'AMap.ControlBar', 'AMap.MoveAnimation', 'AMap.Driving', 'AMap.AutoComplete'],           // 需要使用的的插件列表，如比例尺'AMap.Scale'等
                "Loca": {                // 是否加载 Loca， 缺省不加载
                    "version": '2.0.0'  // Loca 版本，缺省 1.3.2
                }
            };

            const AMap = (window as any).AMap;
            gAMap = AMap;
            const map = new AMap.Map('container', {
                rotateEnable: true,
                pitchEnable: true,
                zoom: 17,
                pitch: 25,
                rotation: 0,
                viewMode: '3D', //开启3D视图,默认为关闭
                terrain: false,
                zooms: [2, 20],
                center: [curGeo.longitude, curGeo.latitude],
                mapStyle: "amap://styles/whitesmoke",
                showBuildingBlock: true,
                features: ['bg', 'point', 'road', 'building'],
                skyColor: '#ffffff',
            });
            myMap = map;

            var loca = new Loca.Container({
                map: map
            });

            map.on('click', (e: any) => {
                console.log('map click', e);
                state.search.focus = false;

                // postionState.switchMode('mock');
                const mockGeo = {
                    longitude: e.lnglat.lng,
                    latitude: e.lnglat.lat,
                    timestamp: new Date().getTime(),
                    accuracy: 1
                } as GeoLocation;
                postionState.addMockPos(mockGeo);
            });
            map.on('touchstart', (e: any) => {
                console.log('touchstart', e);
                state.enableFollow = false;
            });

            //实时路况图层
            trafficLayer = new AMap.TileLayer.Traffic({
                zIndex: 10,
                zooms: [2, 20],
                map: map,
            });

            const controlBar = new AMap.ControlBar({
                visible: true,
                position: {
                    top: '10px',
                    right: '10px'
                },
            });
            map.addControl(controlBar);


            // 车辆位置
            const carMarker = new AMap.Marker({
                position: new AMap.LngLat(curGeo.longitude, curGeo.latitude),
                icon: carImg,
                offset: new AMap.Pixel(-64, -64),
                map: map,
            });

            carMarker.on('moving', (e: any) => {
                if (state.enableFollow) {
                    console.log(e.target.getOrientation())
                    map.setCenter(e.target.getPosition());
                    map.setRotation(-e.target.getOrientation());
                }
            })

            // 监听位置变更
            postionState.addListener('nav', pos => {
                console.debug('pos changed', pos);

                // 信号强度
                if (pos.accuracy == null || pos.accuracy > 10) {
                    state.lowSignal = true;
                } else {
                    state.lowSignal = false;
                }

                if (state.lastPos !== null) {
                    const posList = [];
                    let ts = pos.timestamp - state.lastPos.timestamp;
                    ts = ts < 200 ? 200 : ts;
                    console.log(ts)

                    posList.push({
                        position: [state.lastPos.longitude, state.lastPos.latitude],
                        duration: 0,
                    });
                    posList.push({
                        position: [pos.longitude, pos.latitude],
                        duration: ts,
                    });

                    carMarker.moveAlong(posList);
                } else {
                    carMarker.setPosition([pos.longitude, pos.latitude]);
                    map.setCenter([pos.longitude, pos.latitude]);
                }

                state.lastPos = pos;
            })

            // 实例化Autocomplete
            geoSearch = new AMap.Autocomplete({
                city: '全国'
            });

            // 规划
            driving = new AMap.Driving({
                // 驾车路线规划策略，AMap.DrivingPolicy.LEAST_TIME是最快捷模式
                policy: AMap.DrivingPolicy.LEAST_TIME,
                // map 指定将路线规划方案绘制到对应的AMap.Map对象上
                map: map,
                // panel 指定将结构化的路线详情数据显示的对应的DOM上，传入值需是DOM的ID
                // panel: 'panel'
            });
        })
        .catch(function (error) { // 请求失败处理
            console.log(error);
        });





})


onUnmounted(() => {
    postionState.removeListener("nav");
})
</script>

<template>
    <div class="nav-view">
        <div class="map-controller">
            <div class="search-input">
                <el-input placeholder="导航目的地" v-model="state.search.query" @input="searchSuggest" clearable
                    @focus="state.search.focus = true" size="large">
                </el-input>
                <div class="suggest" v-show="state.search.focus">
                    <div v-for="item in state.search.suggestList" class="suggest-item" @click="navToSuggestResult(item)">
                        <h3>{{ item.name }}</h3>
                        <p class="suggest-item-desc">{{ item.district }} {{ typeof (item.address) == 'string' ?
                            item.address : '' }}</p>
                    </div>
                </div>
            </div>

            <!-- controller -->
            <div class="float-controller">
                <div class="icon" :class="{ 'float-controller-icon-active': state.enableFollow }"
                    @click="changeFollowState">
                    <el-icon class="icon-nav">
                        <Position />
                    </el-icon>
                </div>
                <div class="icon" v-if="state.lowSignal">
                    <svg class="icon-signal"
                        style="width: 1em;height: 1em;vertical-align: middle;fill: currentColor;overflow: hidden;"
                        viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="3316">
                        <path
                            d="M584 352H440c-17.7 0-32 14.3-32 32v544c0 17.7 14.3 32 32 32h144c17.7 0 32-14.3 32-32V384c0-17.7-14.3-32-32-32zM892 64H748c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h144c17.7 0 32-14.3 32-32V96c0-17.7-14.3-32-32-32zM276 640H132c-17.7 0-32 14.3-32 32v256c0 17.7 14.3 32 32 32h144c17.7 0 32-14.3 32-32V672c0-17.7-14.3-32-32-32z"
                            p-id="3317"></path>
                    </svg>
                </div>
                <div class="icon" :class="{ 'float-controller-icon-active': state.showTrafficLayer }"
                    @click="switchTrafficLayer">
                    <svg class="icon"
                        style="top: -9px;width: 1em;height: 1em;vertical-align: middle;fill: currentColor;overflow: hidden;"
                        viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg">
                        <path
                            d="M853.333333 312.917333V796.444444a170.666667 170.666667 0 0 1-170.666666 170.666667H341.333333a170.666667 170.666667 0 0 1-170.666666-170.666667V170.666667a113.777778 113.777778 0 0 1 113.777777-113.777778h455.111112a113.777778 113.777778 0 0 1 113.777777 113.777778v142.250666zM512 170.666667a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z m0 256a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z m0 256a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z" />
                        <path
                            d="M853.333333 796.444444a170.666667 170.666667 0 0 1-170.666666 170.666667H341.333333a170.666667 170.666667 0 0 1-170.666666-170.666667V170.666667a113.777778 113.777778 0 0 1 113.777777-113.777778h455.111112a113.777778 113.777778 0 0 1 113.777777 113.777778v625.777777zM512 170.666667a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z m0 256a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z m0 256a85.333333 85.333333 0 1 0 0 170.666666 85.333333 85.333333 0 0 0 0-170.666666z" />
                    </svg>
                </div>
            </div>
        </div>
        <div id="container" style="width:100%; height:100%;resize:both;"></div>
    </div>
</template>

<style>
.icon-nav {
    transform: rotate(-45deg);
    position: absolute;
    top: 4px;
    left: 1px;
}

.icon-signal {
    top: -10px;
    color: #ffb100;
}

.nav-view {
    width: 100%;
    height: 100%;
    position: relative;
}

.map-controller {
    position: absolute;
    top: 10px;
    left: 10px;
    right: 10px;
    z-index: 99999;
    pointer-events: none;
}

.float-controller {
    position: absolute;
    top: 140px;
    right: 24px;
    pointer-events: all;
}

.float-controller-icon-active {
    color: #409eff;
}

.float-controller>.icon {
    background-color: #ffff;
    border-radius: 30px;
    font-size: 40px;
    width: 60px;
    height: 60px;
    text-align: center;
    line-height: 60px;
    padding-top: 4px;
    margin-bottom: 10px;
}

.search-input {
    width: 400px;
    height: 50px;
    font-size: 25px;
    pointer-events: all;
}

.suggest {
    background-color: #ffffff;
    padding-left: 10px;
    border-radius: 0 0 10px 10px;
    width: 400px;
    max-height: 800px;
    overflow: auto;
}

.suggest-item {
    border-bottom: solid 1px #cccccc;
    padding-bottom: 5px;
    padding-top: 5px;
}

.suggest-item-desc {
    font-size: 13px;
    margin-left: 10px;
    color: #856767;
}
</style>
