import * as T from 'three';
import type { SceneWeather } from './teslaWeatherData';

export function createVehicleWeather() {
  const group=new T.Group();group.name='Vehicle_weather';
  const count=900, positions=new Float32Array(count*3),rainPositions=new Float32Array(count*6);
  let seed=891;
  const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  for(let i=0;i<count;i++){positions[i*3]=(random()-.5)*36;positions[i*3+1]=random()*18;positions[i*3+2]=(random()-.5)*48;}
  const snowGeometry=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(positions,3));
  const snowMaterial=new T.ShaderMaterial({transparent:true,depthWrite:false,uniforms:{brightness:{value:.8}},vertexShader:`void main(){vec4 p=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*p;gl_PointSize=clamp(38./max(1.,-p.z),1.,5.);}`,fragmentShader:`uniform float brightness;void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;gl_FragColor=vec4(vec3(brightness),.8*(1.-smoothstep(.18,.5,d)));}`});
  const snow=new T.Points(snowGeometry,snowMaterial);snow.frustumCulled=false;
  const rainGeometry=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(rainPositions,3));
  const rainMaterial=new T.LineBasicMaterial({color:'#adbec9',transparent:true,opacity:.38,depthWrite:false});
  const rain=new T.LineSegments(rainGeometry,rainMaterial);rain.frustumCulled=false;group.add(snow,rain);
  let mode:SceneWeather='clear',elapsed=0;
  function set(value:SceneWeather,night:boolean){mode=value;snow.visible=value==='snow';rain.visible=value==='rain';snowMaterial.uniforms.brightness.value=night?.42:.85;rainMaterial.opacity=night?.2:.38;}
  set('clear',false);
  return {group,set,update(dt:number,speed=0){
    if(mode!=='rain'&&mode!=='snow')return;
    elapsed+=dt;
    for(let i=0;i<count;i++){
      const p=i*3;positions[p+1]-=dt*(mode==='rain'?15:1.6);
      positions[p]+=dt*(mode==='rain'?1.4:Math.sin(elapsed+i)*.35);
      positions[p+2]-=dt*speed;
      if(positions[p+1]<.2)positions[p+1]=18;
      positions[p]=((positions[p]+18)%36+36)%36-18;
      positions[p+2]=((positions[p+2]+24)%48+48)%48-24;
      if(mode==='rain'){const r=i*6;rainPositions[r]=positions[p];rainPositions[r+1]=positions[p+1];rainPositions[r+2]=positions[p+2];rainPositions[r+3]=positions[p]-.04;rainPositions[r+4]=positions[p+1]+.55;rainPositions[r+5]=positions[p+2];}
    }
    (mode==='rain'?rainGeometry:snowGeometry).getAttribute('position').needsUpdate=true;
  },dispose(){snowGeometry.dispose();snowMaterial.dispose();rainGeometry.dispose();rainMaterial.dispose();group.removeFromParent();}};
}

export function applyWeatherLighting(scene:T.Scene,sun:T.DirectionalLight,sky:T.Object3D,road:T.Mesh,mode:SceneWeather,night:boolean){
  const wet=mode==='rain',snow=mode==='snow',fog=mode==='fog',overcast=mode!=='clear';
  sky.visible=!night&&!overcast;
  const horizon=scene.getObjectByName('Distant_city_horizon');if(horizon)horizon.visible=mode==='clear'||mode==='cloudy';
  if(overcast){const color=night?'#0b1420':fog?'#b8c1c7':'#9daab5';scene.background=new T.Color(color);scene.fog=new T.Fog(color,fog?8:25,fog?85: snow?130:180);sun.intensity*=.35;}
  const material=road.material as T.MeshStandardMaterial;
  material.roughness=wet?.24:.94;
  material.color.set(wet?'#79828a':'#ffffff');
  material.normalScale?.setScalar(wet?.18:.28);
}
