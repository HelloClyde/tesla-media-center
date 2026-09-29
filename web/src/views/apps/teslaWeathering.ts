import { MeshStandardMaterial } from 'three';

// Local-space stains stay attached to buildings when street blocks wrap around.
export function addFacadeWeathering(material: MeshStandardMaterial) {
  if(material.userData.weathered)return;
  material.userData.weathered=true;
  material.onBeforeCompile=shader=>{
    shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nattribute vec3 wearPosition;\nvarying vec3 vWearPosition;').replace('#include <begin_vertex>','#include <begin_vertex>\nvWearPosition = wearPosition;');
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>
      varying vec3 vWearPosition;
      float wearHash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
      float wearNoise(vec2 p) { vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(wearHash(i),wearHash(i+vec2(1,0)),f.x),mix(wearHash(i+vec2(0,1)),wearHash(i+vec2(1,1)),f.x),f.y); }
    `).replace('#include <color_fragment>',`#include <color_fragment>
      vec3 p=vWearPosition;
      float horizontal=p.x+p.z*.73;
      float patches=wearNoise(vec2(horizontal*.65,p.y*.45));
      float streak=pow(wearNoise(vec2(horizontal*5.0,p.y*.18)),3.0);
      float foot=(1.0-smoothstep(.0,2.4,p.y))*(.35+.65*patches);
      float grime=clamp(foot*.32+streak*.3+patches*.08,0.0,.5);
      diffuseColor.rgb *= mix(vec3(1.0),vec3(.43,.39,.31),grime);
    `);
  };
  material.customProgramCacheKey=()=> 'facade-weathering-v1';
  material.needsUpdate=true;
}
