import * as T from 'three';
import type { SceneWeather } from './teslaWeatherData';

export function createVehicleWeather() {
  const group=new T.Group();group.name='Vehicle_weather';
  const count=2100, positions=new Float32Array(count*3),rainPositions=new Float32Array(count*6);
  let seed=891;
  const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  for(let i=0;i<count;i++){positions[i*3]=(random()-.5)*36;positions[i*3+1]=random()*18;positions[i*3+2]=(random()-.5)*48;}
  const snowGeometry=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(positions,3).setUsage(T.DynamicDrawUsage));
  const snowMaterial=new T.ShaderMaterial({transparent:true,depthWrite:false,uniforms:{brightness:{value:.8}},vertexShader:`void main(){vec4 p=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*p;gl_PointSize=clamp(38./max(1.,-p.z),1.,5.);}`,fragmentShader:`uniform float brightness;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(vec3(brightness),.8*(1.-smoothstep(.18,.5,d)));}`});
  snowGeometry.setDrawRange(0,900);
  const snow=new T.Points(snowGeometry,snowMaterial);snow.frustumCulled=false;
  const rainGeometry=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(rainPositions,3).setUsage(T.DynamicDrawUsage));
  const rainMaterial=new T.LineBasicMaterial({color:'#adbec9',transparent:true,opacity:.38,depthWrite:false});
  const rain=new T.LineSegments(rainGeometry,rainMaterial);rain.frustumCulled=false;group.add(snow,rain);
  // One small dynamic draw call for all vehicle impacts; no raycasts in the render loop.
  const splashCount=24,spokes=3,splashPositions=new Float32Array(splashCount*spokes*6);
  for(let i=1;i<splashPositions.length;i+=3)splashPositions[i]=-1000;
  const splashGeometry=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(splashPositions,3).setUsage(T.DynamicDrawUsage));
  const splashMaterial=new T.LineBasicMaterial({color:'#c9deeb',transparent:true,opacity:.5,depthWrite:false});
  const splashes=new T.LineSegments(splashGeometry,splashMaterial);splashes.name='Vehicle_rain_splashes';splashes.frustumCulled=false;group.add(splashes);
  const impacts:Array<{age:number;site:number;angle:number}>=Array.from({length:splashCount},()=>({age:-random()*.8,site:0,angle:random()*Math.PI*2}));
  let impactSites:T.Vector3[]=[];
  let mode:SceneWeather='clear',elapsed=0;
  function set(value:SceneWeather,night:boolean){mode=value;snow.visible=value==='snow';rain.visible=value==='rain';splashes.visible=value==='rain'&&impactSites.length>0;snowMaterial.uniforms.brightness.value=night?.42:.85;rainMaterial.opacity=night?.38:.58;splashMaterial.opacity=night?.64:.5;}
  set('clear',false);
  return {group,set,setImpactSurface(model:T.Object3D){
    model.updateWorldMatrix(true,true);group.updateWorldMatrix(true,false);
    const bounds=new T.Box3().setFromObject(model),cutoff=bounds.min.y+bounds.getSize(new T.Vector3()).y*.52;
    const cells=new Map<string,T.Vector3>(),point=new T.Vector3(),normal=new T.Vector3(),normalMatrix=new T.Matrix3();
    model.traverse(object=>{
      if(!(object instanceof T.Mesh))return;
      const materials=Array.isArray(object.material)?object.material:[object.material];
      if(!materials.some(material=>material.name==='Pearl_White_Clearcoat'||material.name==='Smoked_Panoramic_Glass'))return;
      const positions=object.geometry.getAttribute('position'),normals=object.geometry.getAttribute('normal');
      if(!positions||!normals)return;
      normalMatrix.getNormalMatrix(object.matrixWorld);
      for(let i=0;i<positions.count;i+=2){
        normal.fromBufferAttribute(normals,i).applyMatrix3(normalMatrix).normalize();
        if(normal.y<.4)continue;
        point.fromBufferAttribute(positions,i).applyMatrix4(object.matrixWorld);
        if(point.y<cutoff)continue;
        const key=`${Math.floor(point.x*5)},${Math.floor(point.z*5)}`;
        if(!cells.has(key)||cells.get(key)!.y<point.y)cells.set(key,point.clone());
      }
    });
    impactSites=Array.from(cells.values(),point=>group.worldToLocal(point));
    splashes.visible=mode==='rain'&&impactSites.length>0;
  },update(dt:number,speed=0){
    if(mode!=='rain'&&mode!=='snow')return;
    elapsed+=dt;
    for(let i=0;i<(mode==='rain'?count:900);i++){
      const p=i*3;positions[p+1]-=dt*(mode==='rain'?21:1.6);
      positions[p]+=dt*(mode==='rain'?1.4:Math.sin(elapsed+i)*.35);
      positions[p+2]-=dt*speed;
      if(positions[p+1]<.2)positions[p+1]=18;
      positions[p]=((positions[p]+18)%36+36)%36-18;
      positions[p+2]=((positions[p+2]+24)%48+48)%48-24;
      if(mode==='rain'){const r=i*6;rainPositions[r]=positions[p];rainPositions[r+1]=positions[p+1];rainPositions[r+2]=positions[p+2];rainPositions[r+3]=positions[p]-.06;rainPositions[r+4]=positions[p+1]+.85;rainPositions[r+5]=positions[p+2];}
    }
    (mode==='rain'?rainGeometry:snowGeometry).getAttribute('position').needsUpdate=true;
    if(mode==='rain'&&impactSites.length){
      for(let i=0;i<splashCount;i++){
        const impact=impacts[i];impact.age+=dt;
        if(impact.age>.28){impact.age=-random()*.5;impact.site=Math.floor(random()*impactSites.length);impact.angle=random()*Math.PI*2;}
        const active=impact.age>=0,phase=active?impact.age/.28:0,site=impactSites[impact.site%impactSites.length];
        for(let spoke=0;spoke<spokes;spoke++){
          const offset=(i*spokes+spoke)*6,angle=impact.angle+spoke*Math.PI*2/spokes;
          const radius=active?(.012+.055*phase)*(1-phase*.4):0;
          splashPositions[offset]=site.x;splashPositions[offset+1]=active?site.y+.012:-1000;splashPositions[offset+2]=site.z;
          splashPositions[offset+3]=site.x+Math.cos(angle)*radius;
          splashPositions[offset+4]=active?site.y+.012+.035*Math.sin(Math.PI*phase):-1000;
          splashPositions[offset+5]=site.z+Math.sin(angle)*radius;
        }
      }
      splashGeometry.getAttribute('position').needsUpdate=true;
    }
  },dispose(){snowGeometry.dispose();snowMaterial.dispose();rainGeometry.dispose();rainMaterial.dispose();splashGeometry.dispose();splashMaterial.dispose();group.removeFromParent();}};
}

export function applyWeatherLighting(scene:T.Scene,sun:T.DirectionalLight,sky:T.Object3D,road:T.Mesh,mode:SceneWeather,night:boolean){
  const wet=mode==='rain',snow=mode==='snow',fog=mode==='fog',overcast=mode!=='clear';
  sky.visible=!night&&!overcast;
  const horizon=scene.getObjectByName('Distant_city_horizon');if(horizon)horizon.visible=!fog;
  if(overcast){
    const color=night?'#0b1420':fog?'#b8c1c7':'#9daab5';
    scene.background=new T.Color(color);
    scene.fog=new T.Fog(color,fog?8:25,fog?85: wet?280: snow?220:240);
    // An overcast sky is a broad light source, not a low-angle sun. Keep the
    // shadow map allocated, but fade its contribution instead of casting a
    // sharp, contradictory sunny-day shadow across the wet road.
    const diffuse=mode==='cloudy'? .45 : wet? .18 : snow? .25 : .08;
    sun.intensity*=diffuse;
    sun.shadow.intensity=night? .04 : mode==='cloudy'? .38 : wet? .1 : snow? .18 : .06;
    const fill=scene.children.find(child=>child instanceof T.HemisphereLight) as T.HemisphereLight|undefined;
    if(fill&&!night)fill.intensity=mode==='cloudy'? .38 : wet? .65 : snow? .72 : .78;
  }
  const material=road.material as T.MeshStandardMaterial;
  road.userData.setSnow?.(snow);
  material.roughness=wet?.24:.94;
  material.color.set(wet?'#79828a':'#ffffff');
  material.normalScale?.setScalar(snow?.08:wet?.18:.28);
}
