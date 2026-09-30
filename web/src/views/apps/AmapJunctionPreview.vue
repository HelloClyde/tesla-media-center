<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import L from 'leaflet';
import 'leaflet-rotate';
import { attachAppMap } from './amapVectorMap';
import { bearingBetween } from './amapHeading';
import { type AppRoute, type Point } from './amapNavigation';
const props = defineProps<{ route: AppRoute; stepIndex: number; distance: number; position?: Point }>();
const element = ref<HTMLElement>(), message = ref('');
let map: L.Map | undefined, layer: ReturnType<typeof attachAppMap> | undefined;
let routeLines: L.Polyline[] = [], vehicle: L.CircleMarker | undefined, resize: ResizeObserver | undefined;
function draw() {
 if (!map) return;
 routeLines.forEach(line=>line.remove()); routeLines=[];
 const step=props.route.steps[props.stepIndex], next=props.route.steps[props.stepIndex+1];
 if (!step || !next) return;
 const index=step.end, point=props.route.path[index];
 const heading=bearingBetween(props.route.path[Math.max(step.start,index-1)],point);
 map.setBearing(-heading); map.setView([point[1],point[0]],18,{animate:false});
 let segment: L.LatLngTuple[]=[];
 const breaks=new Set(props.route.breaks);
 const flush=()=>{ if(segment.length>1) {
   routeLines.push(L.polyline(segment,{color:'#fff',weight:12,opacity:.95}).addTo(map!));
   routeLines.push(L.polyline(segment,{color:'#00b88a',weight:7,opacity:1}).addTo(map!));
 } segment=[]; };
 for(let i=Math.max(0,step.start);i<=next.end;i++) {
  if(breaks.has(i)) flush();
  const p=props.route.path[i]; segment.push([p[1],p[0]]);
 }
 flush(); updateVehicle();
}
function updateVehicle() {
 if(!map || !props.position) { vehicle?.remove(); vehicle=undefined; return; }
 const p: L.LatLngTuple=[props.position[1],props.position[0]];
 if(!vehicle) vehicle=L.circleMarker(p,{radius:7,color:'#fff',weight:3,fillColor:'#168ee5',fillOpacity:1}).addTo(map);
 else vehicle.setLatLng(p);
}
onMounted(()=>{
 if(!element.value) return;
 map=L.map(element.value,{rotate:true,rotateControl:false,zoomControl:false,attributionControl:false,
  dragging:false,touchZoom:false,scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,minZoom:18,maxZoom:18});
 map.setView([0,0],18);
 draw(); layer=attachAppMap(map,value=>message.value=value);
 resize=new ResizeObserver(()=>map?.invalidateSize({pan:false})); resize.observe(element.value);
});
watch(()=>[props.route,props.stepIndex],draw);
watch(()=>props.position,updateVehicle);
onBeforeUnmount(()=>{resize?.disconnect();layer?.dispose();map?.remove();});
</script>
<template>
 <aside class="junction-preview" aria-label="路口放大预览">
  <header><strong>路口放大</strong><span>{{ Math.round(Math.max(0,distance)) }} 米</span></header>
  <div ref="element" class="junction-map"></div>
  <small v-if="message" role="status">{{ message }}</small>
  <footer>绿色为应走路线 · © 高德地图</footer>
 </aside>
</template>
<style scoped>
.junction-preview{position:absolute;right:66px;top:126px;width:280px;height:238px;z-index:490;overflow:hidden;border:1px solid #ffffff80;border-radius:16px;box-shadow:0 6px 24px #102b3540;background:#142b32;color:#fff}
header{height:38px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;background:#123f38}header span{color:#8af0ca;font-variant-numeric:tabular-nums}.junction-map{height:174px;width:100%;background:#142b32}footer{height:26px;text-align:center;font-size:11px;line-height:26px;color:#b5cfc9}small{position:absolute;bottom:29px;left:6px;right:6px;background:#142b32de;font-size:11px;padding:4px;border-radius:5px}
@media(max-width:850px){.junction-preview{top:126px;right:64px;width:210px;height:194px}.junction-map{height:130px}}
@media(max-height:550px){.junction-preview{top:116px;width:205px;height:160px}.junction-map{height:96px}}
</style>
