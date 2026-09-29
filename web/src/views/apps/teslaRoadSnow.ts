import * as THREE from 'three';

/** Snow shares the asphalt draw call and UV travel: no overlay or extra texture. */
export function addRoadSnow(material: THREE.MeshStandardMaterial) {
  const amount = { value: 0 };
  material.onBeforeCompile = shader => {
    shader.uniforms.roadSnow = amount;
    shader.fragmentShader = `uniform float roadSnow;
float snowHash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float snowNoise(vec2 p) {
  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(snowHash(i),snowHash(i+vec2(1.,0.)),f.x),
    mix(snowHash(i+vec2(0.,1.)),snowHash(i+vec2(1.)),f.x),f.y);
}
` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <map_fragment>', `
#include <map_fragment>
float snowCoverage = 0.0;
#ifdef USE_MAP
if (roadSnow > 0.0) {
  vec2 snowUv = vMapUv;
  float x = (snowUv.x - .5) * 16.0 + (snowNoise(vec2(snowUv.y*32.,4.))-.5)*.09;
  float patches = snowNoise(vec2(snowUv.x*26.0,snowUv.y*150.0));
  // Only one faint pair in the vehicle's lane; other lanes stay snow-covered.
  float trackDistance = abs(abs(x)-.8);
  float tracks = 1.0-smoothstep(.06,.18+(patches-.5)*.06,trackDistance);
  float edge = smoothstep(5.8,7.8,abs(x));
  float slush = snowNoise(vec2(snowUv.x*12.,snowUv.y*75.));
  snowCoverage = roadSnow * clamp(.64+patches*.3-tracks*(.16+slush*.12)+edge*.20,0.,1.);
  vec3 snowColor = mix(vec3(.60,.66,.71),vec3(.88,.92,.95),patches);
  diffuseColor.rgb = mix(diffuseColor.rgb,snowColor,snowCoverage);
}
#endif
`);
    shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>', `
#include <roughnessmap_fragment>
roughnessFactor = mix(roughnessFactor,.98,snowCoverage);
`);
  };
  material.customProgramCacheKey = () => 'road-snow-v2';
  return (enabled: boolean) => { amount.value = enabled ? 1 : 0; };
}
