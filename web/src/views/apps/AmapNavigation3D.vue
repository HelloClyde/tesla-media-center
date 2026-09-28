<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import * as THREE from 'three';
import { createTeslaMapGround } from './teslaMapGround';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';
import type { AppRoute } from './amapNavigation';
const props = defineProps<{ center: MapPoint; position?: MapPoint; heading: number; bearing: number; zoom: number; route?: AppRoute }>();
const emit = defineEmits<{ status: [string]; failed: []; pick: [MapPoint] }>();
const host = ref<HTMLElement>();
let renderer: THREE.WebGLRenderer | undefined, ground: ReturnType<typeof createTeslaMapGround> | undefined;
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(45, 1, 1, 1400);
const routeGroup = new THREE.Group();
const arrowShape = new THREE.Shape(); arrowShape.moveTo(0, -9); arrowShape.lineTo(6, 7); arrowShape.lineTo(0, 4); arrowShape.lineTo(-6, 7); arrowShape.closePath();
const arrow = new THREE.Mesh(new THREE.ShapeGeometry(arrowShape), new THREE.MeshBasicMaterial({ color: '#078cda', side: THREE.DoubleSide, depthTest: false }));
arrow.rotation.x = Math.PI / 2; arrow.renderOrder = 20;
let observer: ResizeObserver | undefined, frame = 0;
function clearRoute() {
  for (const child of [...routeGroup.children]) { const mesh = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>; mesh.geometry.dispose(); mesh.material.dispose(); routeGroup.remove(child); }
}
function update() {
  if (!renderer) return;
  ground?.update(props.center, -180, 0);
  const angle = props.bearing * Math.PI / 180, distance = Math.max(95, Math.min(270, 170 * 2 ** (17 - props.zoom)));
  camera.position.set(-Math.sin(angle) * distance, distance * .95, Math.cos(angle) * distance);
  camera.lookAt(0, 0, 0);
  const [x,z] = groundOffset(props.position || props.center, props.center);
  arrow.visible = !!props.position; arrow.position.set(x, 3, z); arrow.rotation.z = props.heading * Math.PI / 180;
  clearRoute();
  const route = props.route;
  if (route) {
    const vertices: number[] = [], breaks = new Set(route.breaks);
    for (let i=1; i<route.path.length; i++) {
      if (breaks.has(i)) continue;
      const a=groundOffset(route.path[i-1],props.center), b=groundOffset(route.path[i],props.center);
      // Clip each segment to the loaded local map square, including long crossing segments.
      let low=0, high=1; const dx=b[0]-a[0], dz=b[1]-a[1];
      for (const [p,q] of [[-dx,a[0]+280],[dx,280-a[0]],[-dz,a[1]+280],[dz,280-a[1]]]) {
        if (p===0) { if(q<0) high=-1; } else if(p<0) low=Math.max(low,q/p); else high=Math.min(high,q/p);
      }
      if(low>high) continue;
      const length=Math.hypot(dx,dz); if(length<.01) continue;
      const ox=-dz/length*3, oz=dx/length*3;
      const ax=a[0]+dx*low, az=a[1]+dz*low, bx=a[0]+dx*high, bz=a[1]+dz*high;
      vertices.push(ax+ox,1,az+oz, bx+ox,1,bz+oz, ax-ox,1,az-oz, ax-ox,1,az-oz,bx+ox,1,bz+oz,bx-ox,1,bz-oz);
    }
    const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
    const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:'#0cbb8a',side:THREE.DoubleSide,depthTest:false})); mesh.renderOrder=10; routeGroup.add(mesh);
  }
}
function pick(event: MouseEvent) {
  if(!host.value) return;
  const rect=host.value.getBoundingClientRect(), ray=new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);
  const point=ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
  if(point && Math.abs(point.x)<280 && Math.abs(point.z)<280) emit('pick',[props.center[0]+point.x/(111319.49079327358*Math.cos(props.center[1]*Math.PI/180)),props.center[1]-point.z/111319.49079327358]);
}
function lost(event: Event) { event.preventDefault(); emit('failed'); }
onMounted(() => {
  try {
    renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'}); renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
    host.value!.appendChild(renderer.domElement); renderer.domElement.addEventListener('webglcontextlost',lost);
    scene.background=new THREE.Color('#dce5e5'); scene.fog=new THREE.Fog('#dce5e5',280,600);
    scene.add(new THREE.HemisphereLight(0xffffff,0x81979c,2.5),routeGroup,arrow);
    ground=createTeslaMapGround((text,ready)=>emit('status',ready?text:text.replace('已显示示意路面','请重试或切换 2D'))); scene.add(ground.group);
    observer=new ResizeObserver(()=>{if(!host.value||!renderer)return;const {clientWidth:w,clientHeight:h}=host.value;renderer.setSize(w,h);camera.aspect=w/Math.max(h,1);camera.updateProjectionMatrix();}); observer.observe(host.value!);
    update(); let last=0;
    const render=(time:number)=>{frame=requestAnimationFrame(render);if(time-last<32||document.hidden)return;last=time;renderer?.render(scene,camera);}; frame=requestAnimationFrame(render);
  } catch { emit('failed'); }
});
watch(()=>[props.center,props.position,props.heading,props.bearing,props.zoom,props.route],update);
defineExpose({retry:()=>ground?.retry()});
onBeforeUnmount(()=>{cancelAnimationFrame(frame);observer?.disconnect();ground?.dispose();clearRoute();arrow.geometry.dispose();arrow.material.dispose();renderer?.domElement.removeEventListener('webglcontextlost',lost);renderer?.dispose();renderer?.forceContextLoss();});
</script>
<template><div ref="host" class="map-3d" aria-label="3D 导航地图" @click="pick"><small>© 高德地图 · App 立体地图</small></div></template>
<style scoped>.map-3d{position:absolute;inset:0;z-index:1;overflow:hidden}.map-3d small{position:absolute;right:5px;bottom:2px;font-size:10px;color:#536c68;pointer-events:none}.map-3d :deep(canvas){display:block;width:100%;height:100%}</style>
