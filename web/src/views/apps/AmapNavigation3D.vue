<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { createTeslaMapGround } from './teslaMapGround';
import { createAmapLandmarks, disposeGltfScenes } from './amapLandmarks';
import { groundOffset, groundPoint, type MapPoint } from './teslaMapCoordinates';
import { followCameraBearing, navigationSceneCenter, positionNavigationCamera, rebaseNavigationCamera } from './amapNavigationCamera';
import { matchPosition, meters, type AppRoute } from './amapNavigation';
import { congestionSegmentProgresses, type CongestionRun } from './amapRouteTraffic';
import { ribbonJoinNormal, roundedRoutePoints, routeRibbonCutProgress, trimRouteRibbon, type RibbonSpan } from './amapRouteRibbon';
import { cameraAssetReady, cameraSign, routeCameraSigns, trafficLightAssetReady, trafficLightSign, type MapSign } from './amapMapSigns';
import type { SpeedLimitCamera } from './amapSpeedLimit';
import type { UpcomingTrafficSignal } from './amapTrafficSignals';
const props = defineProps<{ center: MapPoint; position?: MapPoint; heading: number; bearing: number; zoom: number; route?: AppRoute; progress: number; trafficRuns: CongestionRun[]; cameras?: SpeedLimitCamera[]; signal?: UpcomingTrafficSignal | null; navigating: boolean; following: boolean; headingUp: boolean; theme: 'day' | 'night' }>();
const emit = defineEmits<{ status: [string]; failed: []; pick: [MapPoint]; interaction: []; viewcenter: [MapPoint] }>();
const host = ref<HTMLElement>();
let renderer: THREE.WebGLRenderer | undefined, ground: ReturnType<typeof createTeslaMapGround> | undefined;
let landmarks: ReturnType<typeof createAmapLandmarks> | undefined;
let controls: OrbitControls | undefined, manualCenter: MapPoint | undefined, manualView = false;
let settingCamera = false, suppressPickUntil = 0, followedBearing: number | undefined;
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(45, 1, 1, 1400);
const ambient = new THREE.HemisphereLight(0xffffff,0x81979c,2.5);
const routeGroup = new THREE.Group();
const trafficGroup = new THREE.Group();
const signGroup = new THREE.Group();
const vehicle = new THREE.Group();
const arrowShape = new THREE.Shape(); arrowShape.moveTo(0, -9); arrowShape.lineTo(6, 7); arrowShape.lineTo(0, 4); arrowShape.lineTo(-6, 7); arrowShape.closePath();
const arrow = new THREE.Mesh(new THREE.ShapeGeometry(arrowShape), new THREE.MeshBasicMaterial({ color: '#078cda', side: THREE.DoubleSide, depthTest: false }));
arrow.rotation.x = Math.PI / 2; arrow.position.y = 2; arrow.renderOrder = 20; vehicle.add(arrow);
const halo = new THREE.Mesh(new THREE.RingGeometry(4, 8, 32), new THREE.MeshBasicMaterial({ color: '#3ba5f2', transparent: true, opacity: .42, side: THREE.DoubleSide, depthWrite: false }));
halo.rotation.x = -Math.PI / 2; halo.position.y = .12; vehicle.add(halo);
let vehicleModel: THREE.Group | undefined, vehicleRequested = false, destroyed = false;
function loadVehicle() {
  if (vehicleRequested) return;
  vehicleRequested = true;
  new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load('/models/2022_tesla_model_y.glb', ({scene: model}) => {
    if (destroyed) { disposeGltfScenes([model]); return; }
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    if (!Number.isFinite(size.x + size.y + size.z) || Math.max(size.x,size.y,size.z) <= 0) {
      disposeGltfScenes([model]); return;
    }
    const scale = 4.8 / Math.max(size.x,size.y,size.z);
    // This GLB faces +Z; the map's north-facing vehicle points toward -Z.
    model.scale.setScalar(scale);
    model.position.set(-center.x*scale, -bounds.min.y*scale, -center.z*scale);
    model.rotation.y = Math.PI;
    model.traverse(child => { if ((child as THREE.Mesh).isMesh) (child as THREE.Mesh).castShadow = false; });
    vehicle.add(model); vehicleModel = model; arrow.visible = false;
  }, undefined, () => { vehicleRequested = false; });
}
let observer: ResizeObserver | undefined, frame = 0;
let routeAnchor: MapPoint | undefined, renderedRoute: AppRoute | undefined, renderedNavigating = false;
let trafficAnchor: MapPoint | undefined, renderedTraffic: CongestionRun[] | undefined;
let signAnchor: MapPoint | undefined, renderedSignRoute: AppRoute | undefined, renderedCameras: SpeedLimitCamera[] | undefined;
let renderedSignNavigating = false;
let signGroundRevision = -1;
const signTextures = new Map<string, THREE.CanvasTexture>();
let lightSprites: { point: MapPoint; sprite: THREE.Sprite }[] = [], liveLightSprite: THREE.Sprite | undefined;
let countdownTexture: THREE.CanvasTexture | undefined, countdownKey = '', liveLightPoint = '';
let routeGroundRevision = -1, trafficGroundRevision = -1;
type TrafficRibbon = { end: number; spans: RibbonSpan[]; original: Float32Array };
const trafficRibbons = new Map<THREE.Mesh<THREE.BufferGeometry>, TrafficRibbon>();
function sceneCenter() { return manualCenter ?? navigationSceneCenter(props.center, props.position, props.following); }
function signTexture(sign: MapSign) {
  let texture = signTextures.get(sign.key);
  if (!texture) {
    texture = new THREE.CanvasTexture(sign.canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    signTextures.set(sign.key, texture);
  }
  return texture;
}
function makeSign(sign: MapSign, width: number, height: number, texture = signTexture(sign)) {
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true,
    depthTest: false, depthWrite: false, toneMapped: false }));
  sprite.center.set(sign.anchorX / sign.width, 0);
  sprite.scale.set(width, height, 1); sprite.renderOrder = 14;
  return sprite;
}
function clearMapSigns() {
  for (const child of [...signGroup.children]) {
    (child as THREE.Sprite).material.dispose();
    signGroup.remove(child);
  }
  lightSprites = []; liveLightSprite = undefined;
  countdownTexture?.dispose(); countdownTexture = undefined; countdownKey = ''; liveLightPoint = '';
}
function signRoadHeight(point: MapPoint, route: AppRoute) {
  const index = route.path.length > 1 ? matchPosition(route, point, 0, true).index : -1;
  const direction: [number, number] = index >= 0 ? groundOffset(route.path[index + 1], route.path[index]) : [0, 0];
  return ground?.roadHeight(point, direction) ?? 0;
}
function updateMapSigns(center: MapPoint) {
  const route = props.route;
  if (route !== renderedSignRoute || props.cameras !== renderedCameras || props.navigating !== renderedSignNavigating || !signAnchor
      || signGroundRevision !== ground?.revision() || Math.hypot(...groundOffset(center, signAnchor)) > 120) {
    clearMapSigns();
    renderedSignRoute = route; renderedCameras = props.cameras; renderedSignNavigating = props.navigating;
    signGroundRevision = ground?.revision() ?? -1;
    signAnchor = [...center];
    if (route) {
      for (const point of props.navigating ? route.trafficLights || [] : []) {
        const [x, z] = groundOffset(point, signAnchor);
        if (Math.abs(x) > 280 || Math.abs(z) > 280) continue;
        const sprite = makeSign(trafficLightSign(), 2.6, 4.1);
        sprite.position.set(x, signRoadHeight(point, route) + .7, z);
        signGroup.add(sprite); lightSprites.push({ point, sprite });
      }
      for (const sign of routeCameraSigns(route, props.cameras)) {
        const [x, z] = groundOffset(sign.displayPoint, signAnchor);
        if (Math.abs(x) > 280 || Math.abs(z) > 280) continue;
        const sprite = makeSign(cameraSign(sign.type, sign.limit), 3.6, 3.6);
        sprite.position.set(x, (ground?.roadHeight(sign.point, sign.direction) ?? 0) + .7, z);
        signGroup.add(sprite);
      }
    }
  }
  const [x, z] = groundOffset(signAnchor, center);
  signGroup.position.set(x, 0, z);
  const signal = props.navigating ? props.signal : undefined;
  const activeSign = signal ? trafficLightSign(signal.color, signal.seconds) : undefined;
  const desiredCountdownKey = signal ? `${signal.color}:${signal.seconds}` : '';
  const oldCountdownTexture = countdownTexture;
  if (desiredCountdownKey !== countdownKey) {
    countdownTexture = activeSign ? new THREE.CanvasTexture(activeSign.canvas) : undefined;
    if (countdownTexture) countdownTexture.colorSpace = THREE.SRGBColorSpace;
    countdownKey = desiredCountdownKey;
  }
  let matched = false;
  for (const item of lightSprites) {
    const color = signal && meters(item.point, signal.point) <= 25 ? signal.color : undefined;
    const material = item.sprite.material;
    const texture = color && countdownTexture ? countdownTexture : signTexture(trafficLightSign());
    if (material.map !== texture) { material.map = texture; material.needsUpdate = true; }
    const sign = color && activeSign ? activeSign : trafficLightSign();
    item.sprite.center.set(sign.anchorX / sign.width, 0);
    item.sprite.scale.set(sign.width / sign.height * 4.1, 4.1, 1);
    if (color) matched = true;
  }
  if (!route || !signal || matched) {
    if (liveLightSprite) { liveLightSprite.material.dispose(); signGroup.remove(liveLightSprite); liveLightSprite = undefined; liveLightPoint = ''; }
  } else {
    const [lx, lz] = groundOffset(signal.point, signAnchor);
    if (Math.abs(lx) <= 280 && Math.abs(lz) <= 280) {
      const pointKey = signal.point.join(',');
      if (liveLightSprite && liveLightPoint !== pointKey) {
        liveLightSprite.material.dispose(); signGroup.remove(liveLightSprite); liveLightSprite = undefined;
      }
      if (!liveLightSprite) {
        const sign = activeSign ?? trafficLightSign(signal.color, signal.seconds);
        liveLightSprite = makeSign(sign, sign.width / sign.height * 4.1, 4.1,
          countdownTexture ?? signTexture(sign));
      }
      if (liveLightSprite.material.map !== countdownTexture) {
        liveLightSprite.material.map = countdownTexture ?? null; liveLightSprite.material.needsUpdate = true;
      }
      liveLightSprite.position.set(lx, signRoadHeight(signal.point, route) + .7, lz);
      if (!liveLightSprite.parent) signGroup.add(liveLightSprite);
      liveLightPoint = pointKey;
    } else if (liveLightSprite) {
      liveLightSprite.material.dispose(); signGroup.remove(liveLightSprite); liveLightSprite = undefined; liveLightPoint = '';
    }
  }
  if (oldCountdownTexture && oldCountdownTexture !== countdownTexture) oldCountdownTexture.dispose();
}
function beginManualView() {
  if (manualView) return;
  manualCenter = [...sceneCenter()];
  manualView = true;
  followedBearing = undefined;
  emit('interaction');
}
function manualFocus(): MapPoint | undefined {
  return controls && groundPoint(sceneCenter(), controls.target.x, controls.target.z);
}
function onCameraChange() {
  if (settingCamera || !controls) return;
  beginManualView();
  suppressPickUntil = performance.now() + 250;
  const nextCenter = rebaseNavigationCamera(camera, controls.target, sceneCenter());
  if (!nextCenter) return;
  manualCenter = nextCenter;
  settingCamera = true;
  controls.update();
  settingCamera = false;
  update();
  emit('viewcenter', nextCenter);
}
function onCameraEnd() {
  if (!manualView) return;
  const focus = manualFocus();
  if (focus) emit('viewcenter', focus);
}
function zoomBy(steps: number) {
  if (!controls) return;
  beginManualView();
  const distance = camera.position.clone().sub(controls.target);
  camera.position.copy(controls.target).addScaledVector(distance, 2 ** (-steps * .5));
  controls.update();
  onCameraEnd();
}
function clearTraffic() {
  for (const child of [...trafficGroup.children]) {
    const mesh = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>;
    mesh.geometry.dispose(); mesh.material.dispose(); trafficGroup.remove(child);
  }
  trafficRibbons.clear();
}
function updateTraffic(cutProgress: number) {
  const center = sceneCenter();
  if (props.trafficRuns !== renderedTraffic || !trafficAnchor || trafficGroundRevision !== ground?.revision() || Math.hypot(...groundOffset(center, trafficAnchor)) > 120) {
    clearTraffic();
    renderedTraffic = props.trafficRuns;
    trafficGroundRevision = ground?.revision() ?? -1;
    trafficAnchor = [...center];
    for (const run of props.trafficRuns) {
      const vertices: number[] = [], spans: { start: number; end: number }[] = [];
      const routeSpans = congestionSegmentProgresses(run);
      if (routeSpans.length !== run.path.length - 1) continue;
      for (let i = 1; i < run.path.length; i++) {
        const a = groundOffset(run.path[i - 1], trafficAnchor), b = groundOffset(run.path[i], trafficAnchor);
        if ((Math.abs(a[0]) > 300 && Math.abs(b[0]) > 300) || (Math.abs(a[1]) > 300 && Math.abs(b[1]) > 300)) continue;
        const dx = b[0] - a[0], dz = b[1] - a[1], length = Math.hypot(dx, dz);
        if (length < .1 || length > 1000) continue;
        const ox = -dz / length * 3, oz = dx / length * 3;
        const fromHeight=(ground?.roadHeight(run.path[i-1] as MapPoint,[dx,dz]) || 0)+1.3;
        const toHeight=(ground?.roadHeight(run.path[i] as MapPoint,[dx,dz]) || 0)+1.3;
        vertices.push(a[0]+ox,fromHeight,a[1]+oz, b[0]+ox,toHeight,b[1]+oz, a[0]-ox,fromHeight,a[1]-oz,
          a[0]-ox,fromHeight,a[1]-oz, b[0]+ox,toHeight,b[1]+oz, b[0]-ox,toHeight,b[1]-oz);
        spans.push(routeSpans[i - 1]);
      }
      if (!vertices.length) continue;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
      const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: run.status === 4 ? '#923d6d' : run.status === 3 ? '#e44650' : '#f5a623', side: THREE.DoubleSide, depthTest: false }));
      mesh.renderOrder = 12; trafficGroup.add(mesh);
      trafficRibbons.set(mesh, { end: run.end, spans, original: new Float32Array(vertices) });
    }
  }
  const [x, z] = groundOffset(trafficAnchor!, center);
  trafficGroup.position.set(x, 0, z);
  for (const [mesh, ribbon] of trafficRibbons) {
    if (cutProgress >= ribbon.end) { mesh.geometry.setDrawRange(0, 0); continue; }
    trimRouteRibbon(mesh.geometry, ribbon.spans, ribbon.original, cutProgress);
  }
}
let routeSectionSpans: RibbonSpan[] = [];
const routeRibbons = new Map<THREE.Mesh<THREE.BufferGeometry>, Float32Array>();
function clearRoute() {
  for (const child of [...routeGroup.children]) { const mesh = child as THREE.Mesh<THREE.BufferGeometry, THREE.Material>; mesh.geometry.dispose(); mesh.material.dispose(); routeGroup.remove(child); }
  routeSectionSpans = [];
  routeRibbons.clear();
}
function trimDrivenRoute(cutProgress: number) {
  for (const [mesh, original] of routeRibbons)
    trimRouteRibbon(mesh.geometry, routeSectionSpans, original, cutProgress);
}
function update() {
  if (!renderer) return;
  const background=props.theme==='night'?'#1b2634':'#dce5e5';
  // The APK sky image sits behind the transparent WebGL canvas. Keep fog on
  // the same base color so distant geometry still fades into the horizon.
  scene.background=null;
  scene.fog=new THREE.Fog(background,280,600);
  ambient.intensity=props.theme==='night'?1.15:2.5;
  ground?.setTheme(props.theme);
  const center = sceneCenter();
  ground?.update(center, -180, 0);
  landmarks?.update(center, props.theme);
  ground?.setRoute(props.route, props.progress, props.navigating);
  const [x,z] = groundOffset(props.position || center, center);
  if (!manualView) {
    const guidedFollow = props.following && !!props.position && props.headingUp;
    if (!guidedFollow) followedBearing = undefined;
    else followedBearing ??= props.bearing;
    const target = positionNavigationCamera(camera, followedBearing ?? props.bearing, props.zoom, [x, z], props.following && !!props.position, props.headingUp);
    if (controls) {
      settingCamera = true;
      controls.target.copy(target);
      controls.update();
      settingCamera = false;
    }
  }
  const headingRadians = props.heading * Math.PI / 180;
  const roadDirection: [number, number] = [Math.sin(headingRadians), -Math.cos(headingRadians)];
  const vehicleRoadHeight = props.position ? ground?.roadHeight(props.position, roadDirection) ?? 0 : 0;
  vehicle.visible = !!props.position;
  vehicle.position.set(x, vehicleRoadHeight + .2, z);
  if (ground) ground.group.userData.vehicleFocus = vehicle.visible ? vehicle.position : undefined;
  vehicle.rotation.y = -headingRadians;
  const route = props.route;
  if (route !== renderedRoute || props.navigating !== renderedNavigating || !routeAnchor || routeGroundRevision !== ground?.revision() || Math.hypot(...groundOffset(center, routeAnchor)) > 120) {
    clearRoute();
    renderedRoute = route;
    renderedNavigating = props.navigating;
    routeGroundRevision = ground?.revision() ?? -1;
    routeAnchor = [...center];
    if (route) {
      const vertices: number[] = [], outlines: number[] = [];
      const visual = roundedRoutePoints(route, routeAnchor);
      type Piece = { a: MapPoint; b: MapPoint; start: number; end: number; section: number;
        normal: MapPoint; fromHeight: number; toHeight: number };
      const pieces: Piece[] = [];
      for (let i=1; i<visual.length; i++) {
        if (visual[i].section !== visual[i-1].section) continue;
        const a=groundOffset(visual[i-1].point,routeAnchor), b=groundOffset(visual[i].point,routeAnchor);
        // Clip each segment to the loaded local map square, including long crossing segments.
        let low=0, high=1; const dx=b[0]-a[0], dz=b[1]-a[1];
        for (const [p,q] of [[-dx,a[0]+280],[dx,280-a[0]],[-dz,a[1]+280],[dz,280-a[1]]]) {
          if (p===0) { if(q<0) high=-1; } else if(p<0) low=Math.max(low,q/p); else high=Math.min(high,q/p);
        }
        if(low>=high) continue;
        const length=Math.hypot(dx,dz); if(length<.01) continue;
        const subdivisions=Math.max(1,Math.ceil((high-low)*length/12));
        for(let piece=0;piece<subdivisions;piece++) {
          const from=low+(high-low)*piece/subdivisions, to=low+(high-low)*(piece+1)/subdivisions;
          const ax=a[0]+dx*from, az=a[1]+dz*from, bx=a[0]+dx*to, bz=a[1]+dz*to;
          const fromPoint=groundPoint(routeAnchor,ax,az), toPoint=groundPoint(routeAnchor,bx,bz);
          const fromHeight=ground?.roadHeight(fromPoint,[dx,dz]) || 0, toHeight=ground?.roadHeight(toPoint,[dx,dz]) || 0;
          pieces.push({a:[ax,az],b:[bx,bz],start:visual[i-1].distance+(visual[i].distance-visual[i-1].distance)*from,
            end:visual[i-1].distance+(visual[i].distance-visual[i-1].distance)*to,
            section:visual[i].section,normal:[-dz/length,dx/length],fromHeight,toHeight});
        }
      }
      const joined=(left:Piece,right:Piece)=>left.section===right.section &&
        Math.hypot(left.b[0]-right.a[0],left.b[1]-right.a[1])<.01;
      for(let i=0;i<pieces.length;i++) {
        const part=pieces[i], previous=pieces[i-1], next=pieces[i+1];
        const before=previous && joined(previous,part) ? previous : undefined;
        const after=next && joined(part,next) ? next : undefined;
        const startNormal=ribbonJoinNormal(part.normal,before?.normal);
        const endNormal=ribbonJoinNormal(part.normal,after?.normal);
        const fromHeight=before ? Math.max(before.toHeight,part.fromHeight) : part.fromHeight;
        const toHeight=after ? Math.max(part.toHeight,after.fromHeight) : part.toHeight;
        for (const [target,halfWidth,lift] of [[outlines,4.1,1],[vertices,3.1,1.04]] as const) {
          const [ax,az]=part.a, [bx,bz]=part.b;
          target.push(ax+startNormal[0]*halfWidth,fromHeight+lift,az+startNormal[1]*halfWidth,
            bx+endNormal[0]*halfWidth,toHeight+lift,bz+endNormal[1]*halfWidth,
            ax-startNormal[0]*halfWidth,fromHeight+lift,az-startNormal[1]*halfWidth,
            ax-startNormal[0]*halfWidth,fromHeight+lift,az-startNormal[1]*halfWidth,
            bx+endNormal[0]*halfWidth,toHeight+lift,bz+endNormal[1]*halfWidth,
            bx-endNormal[0]*halfWidth,toHeight+lift,bz-endNormal[1]*halfWidth);
        }
        routeSectionSpans.push({start:part.start,end:part.end});
      }
      for (const [positions,color,heightOrder] of [[outlines,'#e4f8ee',10],[vertices,props.navigating?'#25c66e':'#13b68a',11]] as const) {
        const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
        const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,depthTest:false}));
        mesh.renderOrder=heightOrder; routeGroup.add(mesh);
        routeRibbons.set(mesh,new Float32Array(positions));
      }
    }
  }
  const [routeX, routeZ] = groundOffset(routeAnchor, center);
  routeGroup.position.set(routeX, 0, routeZ);
  const cutProgress = route ? routeRibbonCutProgress(route, props.progress, props.position) : 0;
  trimDrivenRoute(cutProgress);
  updateTraffic(cutProgress);
  updateMapSigns(center);
}
function pick(event: MouseEvent) {
  if(!host.value || performance.now() < suppressPickUntil) return;
  const rect=host.value.getBoundingClientRect(), ray=new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);
  const point=ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
  const center = sceneCenter();
  if(point && Math.abs(point.x)<280 && Math.abs(point.z)<280) emit('pick',groundPoint(center, point.x, point.z));
}
function lost(event: Event) { event.preventDefault(); emit('failed'); }
function initialize() {
  if (renderer || !host.value) return;
  try {
    renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'}); renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
    host.value!.appendChild(renderer.domElement); renderer.domElement.addEventListener('webglcontextlost',lost);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.screenSpacePanning = false;
    controls.minPolarAngle = .12; controls.maxPolarAngle = 1.38;
    controls.minDistance = 35; controls.maxDistance = 450;
    controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
    controls.mouseButtons.RIGHT = THREE.MOUSE.ROTATE;
    controls.touches.ONE = THREE.TOUCH.PAN;
    controls.touches.TWO = THREE.TOUCH.DOLLY_ROTATE;
    controls.addEventListener('change', onCameraChange);
    controls.addEventListener('end', onCameraEnd);
    scene.add(ambient,routeGroup,trafficGroup,signGroup,vehicle);
    loadVehicle();
    ground=createTeslaMapGround((text,ready)=>{
      emit('status',ready?text:text.replace('已显示示意路面','请重试或切换 2D'));
      if(ready && !text.startsWith('正在')) queueMicrotask(update);
    },props.theme); scene.add(ground.group);
    try {
      landmarks=createAmapLandmarks(renderer, bounds => ground?.setLandmarkBounds(bounds));
      scene.add(landmarks.group);
    } catch { landmarks=undefined; }
    observer=new ResizeObserver(()=>{if(!host.value||!renderer)return;const {clientWidth:w,clientHeight:h}=host.value;renderer.setSize(w,h);camera.aspect=w/Math.max(h,1);camera.updateProjectionMatrix();}); observer.observe(host.value!);
    update(); let last=0;
    const render=(time:number)=>{
      frame=requestAnimationFrame(render);
      if(time-last<32||document.hidden)return;
      const elapsed = last ? time-last : 0; last=time;
      if (!manualView && props.following && props.headingUp && props.position && followedBearing !== undefined) {
        const next = followCameraBearing(followedBearing, props.bearing, elapsed);
        const turn = Math.abs(((props.bearing - followedBearing + 540) % 360) - 180);
        if (turn > .05) {
          followedBearing = next;
          const [x,z] = groundOffset(props.position, sceneCenter());
          const target = positionNavigationCamera(camera, next, props.zoom, [x,z], true, true);
          if (controls) {
            settingCamera = true; controls.target.copy(target); controls.update(); settingCamera = false;
          }
        }
      }
      renderer?.render(scene,camera);
    }; frame=requestAnimationFrame(render);
  } catch { dispose(); emit('failed'); }
}
function dispose() {
  cancelAnimationFrame(frame); frame = 0;
  controls?.removeEventListener('change', onCameraChange);
  controls?.removeEventListener('end', onCameraEnd);
  controls?.dispose(); controls = undefined;
  manualCenter = undefined; manualView = false;
  followedBearing = undefined;
  observer?.disconnect(); observer = undefined;
  ground?.dispose(); ground = undefined;
  landmarks?.dispose(); landmarks = undefined;
  clearRoute(); renderedRoute = undefined; renderedNavigating = false; routeAnchor = undefined; routeGroundRevision = -1;
  clearTraffic(); renderedTraffic = undefined; trafficAnchor = undefined; trafficGroundRevision = -1;
  clearMapSigns(); renderedSignRoute = undefined; renderedCameras = undefined; signAnchor = undefined; signGroundRevision = -1;
  for (const texture of signTextures.values()) texture.dispose();
  signTextures.clear();
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
void trafficLightAssetReady.then(ready => {
  if (!ready || !renderer) return;
  clearMapSigns();
  for (const [key, texture] of signTextures) if (key.startsWith('light:')) { texture.dispose(); signTextures.delete(key); }
  renderedSignRoute = undefined;
  update();
});
void cameraAssetReady.then(ready => {
  if (!ready || !renderer) return;
  clearMapSigns();
  for (const [key, texture] of signTextures) if (key.startsWith('camera:')) { texture.dispose(); signTextures.delete(key); }
  renderedSignRoute = undefined;
  update();
});
watch(()=>props.following, following => {
  if (following) { manualCenter = undefined; manualView = false; followedBearing = undefined; update(); }
});
watch(()=>[props.center,props.position,props.heading,props.bearing,props.zoom,props.route,props.progress,props.trafficRuns,props.cameras,props.signal,props.navigating,props.following,props.headingUp,props.theme],update);
defineExpose({retry:()=>ground?.retry(), zoomBy});
onBeforeUnmount(()=>{destroyed=true;dispose();if(vehicleModel)disposeGltfScenes([vehicleModel]);arrow.geometry.dispose();arrow.material.dispose();halo.geometry.dispose();halo.material.dispose();});
</script>
<template><div ref="host" class="map-3d" :class="`sky-${theme}`" aria-label="3D 导航地图" @click="pick"><small>© 高德地图 · App 立体地图</small></div></template>
<style scoped>.map-3d{position:absolute;inset:0;z-index:1;overflow:hidden;background-color:#dce5e5;background-size:100% 100%;background-repeat:no-repeat}.map-3d.sky-day{background-image:url('/amap/sky/day.png')}.map-3d.sky-night{background-color:#1b2634;background-image:url('/amap/sky/night.png')}.map-3d small{position:absolute;right:5px;bottom:2px;font-size:10px;color:#536c68;pointer-events:none}.map-3d :deep(canvas){display:block;width:100%;height:100%;touch-action:none;cursor:grab}.map-3d :deep(canvas):active{cursor:grabbing}</style>
