<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import * as THREE from 'three';
import { createTeslaMapGround } from './teslaMapGround';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';
import { cumulative, type AppRoute } from './amapNavigation';
const props = defineProps<{ center: MapPoint; position?: MapPoint; heading: number; bearing: number; zoom: number; route?: AppRoute; progress: number }>();
const emit = defineEmits<{ status: [string]; failed: []; pick: [MapPoint] }>();
const host = ref<HTMLElement>();
let renderer: THREE.WebGLRenderer | undefined, ground: ReturnType<typeof createTeslaMapGround> | undefined;
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(45, 1, 1, 1400);
const routeGroup = new THREE.Group();
const arrowShape = new THREE.Shape(); arrowShape.moveTo(0, -9); arrowShape.lineTo(6, 7); arrowShape.lineTo(0, 4); arrowShape.lineTo(-6, 7); arrowShape.closePath();
const arrow = new THREE.Mesh(new THREE.ShapeGeometry(arrowShape), new THREE.MeshBasicMaterial({ color: '#078cda', side: THREE.DoubleSide, depthTest: false }));
arrow.rotation.x = Math.PI / 2; arrow.renderOrder = 20;
let observer: ResizeObserver | undefined, frame = 0;
let routeAnchor: MapPoint | undefined, renderedRoute: AppRoute | undefined;
let routeSectionEnds: number[] = [];
function clearRoute() {
  for (const child of [...routeGroup.children]) { const mesh = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>; mesh.geometry.dispose(); mesh.material.dispose(); routeGroup.remove(child); }
  routeSectionEnds = [];
}
function trimDrivenRoute() {
  const mesh = routeGroup.children[0] as THREE.Mesh<THREE.BufferGeometry> | undefined;
  if (!mesh) return;
  let low = 0, high = routeSectionEnds.length;
  while (low < high) { const middle = (low + high) >> 1; if (routeSectionEnds[middle] <= props.progress) low = middle + 1; else high = middle; }
  mesh.geometry.setDrawRange(low * 6, (routeSectionEnds.length - low) * 6);
}
function update() {
  if (!renderer) return;
  ground?.update(props.center, -180, 0);
  ground?.setRoute(props.route, props.progress);
  const angle = props.bearing * Math.PI / 180, distance = Math.max(95, Math.min(330, 170 * 2 ** (17 - props.zoom)));
  camera.position.set(-Math.sin(angle) * distance, distance * (props.zoom < 16 ? 1.1 : .95), Math.cos(angle) * distance);
  camera.lookAt(0, 0, 0);
  const [x,z] = groundOffset(props.position || props.center, props.center);
  arrow.visible = !!props.position; arrow.position.set(x, 3, z); arrow.rotation.z = props.heading * Math.PI / 180;
  const route = props.route;
  if (route !== renderedRoute || !routeAnchor || Math.hypot(...groundOffset(props.center, routeAnchor)) > 120) {
    clearRoute();
    renderedRoute = route;
    routeAnchor = [...props.center];
    if (route) {
      const vertices: number[] = [], breaks = new Set(route.breaks), lengths = cumulative(route);
      for (let i=1; i<route.path.length; i++) {
        if (breaks.has(i)) continue;
        const a=groundOffset(route.path[i-1],routeAnchor), b=groundOffset(route.path[i],routeAnchor);
        // Clip each segment to the loaded local map square, including long crossing segments.
        let low=0, high=1; const dx=b[0]-a[0], dz=b[1]-a[1];
        for (const [p,q] of [[-dx,a[0]+280],[dx,280-a[0]],[-dz,a[1]+280],[dz,280-a[1]]]) {
          if (p===0) { if(q<0) high=-1; } else if(p<0) low=Math.max(low,q/p); else high=Math.min(high,q/p);
        }
        if(low>high) continue;
        const length=Math.hypot(dx,dz); if(length<.01) continue;
        const ox=-dz/length*3, oz=dx/length*3;
        const pieces=Math.max(1,Math.ceil((high-low)*length/12));
        for(let piece=0;piece<pieces;piece++) {
          const from=low+(high-low)*piece/pieces, to=low+(high-low)*(piece+1)/pieces;
          const ax=a[0]+dx*from, az=a[1]+dz*from, bx=a[0]+dx*to, bz=a[1]+dz*to;
          vertices.push(ax+ox,1,az+oz, bx+ox,1,bz+oz, ax-ox,1,az-oz, ax-ox,1,az-oz,bx+ox,1,bz+oz,bx-ox,1,bz-oz);
          routeSectionEnds.push(lengths[i-1]+(lengths[i]-lengths[i-1])*to);
        }
      }
      const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
      const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:'#0cbb8a',side:THREE.DoubleSide,depthTest:false})); mesh.renderOrder=10; routeGroup.add(mesh);
    }
  }
  const [routeX, routeZ] = groundOffset(routeAnchor, props.center);
  routeGroup.position.set(routeX, 0, routeZ);
  trimDrivenRoute();
}
function pick(event: MouseEvent) {
  if(!host.value) return;
  const rect=host.value.getBoundingClientRect(), ray=new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);
  const point=ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
  if(point && Math.abs(point.x)<280 && Math.abs(point.z)<280) emit('pick',[props.center[0]+point.x/(111319.49079327358*Math.cos(props.center[1]*Math.PI/180)),props.center[1]-point.z/111319.49079327358]);
}
function lost(event: Event) { event.preventDefault(); emit('failed'); }
function initialize() {
  if (renderer || !host.value) return;
  try {
    renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'}); renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
    host.value!.appendChild(renderer.domElement); renderer.domElement.addEventListener('webglcontextlost',lost);
    scene.background=new THREE.Color('#dce5e5'); scene.fog=new THREE.Fog('#dce5e5',280,600);
    scene.add(new THREE.HemisphereLight(0xffffff,0x81979c,2.5),routeGroup,arrow);
    ground=createTeslaMapGround((text,ready)=>emit('status',ready?text:text.replace('已显示示意路面','请重试或切换 2D'))); scene.add(ground.group);
    observer=new ResizeObserver(()=>{if(!host.value||!renderer)return;const {clientWidth:w,clientHeight:h}=host.value;renderer.setSize(w,h);camera.aspect=w/Math.max(h,1);camera.updateProjectionMatrix();}); observer.observe(host.value!);
    update(); let last=0;
    const render=(time:number)=>{frame=requestAnimationFrame(render);if(time-last<32||document.hidden)return;last=time;renderer?.render(scene,camera);}; frame=requestAnimationFrame(render);
  } catch { dispose(); emit('failed'); }
}
function dispose() {
  cancelAnimationFrame(frame); frame = 0;
  observer?.disconnect(); observer = undefined;
  ground?.dispose(); ground = undefined;
  clearRoute(); renderedRoute = undefined; routeAnchor = undefined;
  scene.clear();
  if (renderer) {
    renderer.domElement.removeEventListener('webglcontextlost',lost);
    renderer.forceContextLoss();
    renderer.dispose();
    renderer.domElement.remove();
    renderer = undefined;
  }
}
onMounted(initialize);
onActivated(initialize);
onDeactivated(dispose);
watch(()=>[props.center,props.position,props.heading,props.bearing,props.zoom,props.route,props.progress],update);
defineExpose({retry:()=>ground?.retry()});
onBeforeUnmount(()=>{dispose();arrow.geometry.dispose();arrow.material.dispose();});
</script>
<template><div ref="host" class="map-3d" aria-label="3D 导航地图" @click="pick"><small>© 高德地图 · App 立体地图</small></div></template>
<style scoped>.map-3d{position:absolute;inset:0;z-index:1;overflow:hidden}.map-3d small{position:absolute;right:5px;bottom:2px;font-size:10px;color:#536c68;pointer-events:none}.map-3d :deep(canvas){display:block;width:100%;height:100%}</style>
