import * as T from 'three';

/** Capture only when the street loads or lighting changes, never every frame. */
export function captureStreetReflections(renderer:T.WebGLRenderer, scene:T.Scene, car:T.Object3D, position:T.Vector3) {
  const cube=new T.WebGLCubeRenderTarget(128,{type:T.HalfFloatType,generateMipmaps:true,minFilter:T.LinearMipmapLinearFilter});
  const camera=new T.CubeCamera(.15,350,cube);camera.position.copy(position);
  const visible=car.visible, environment=scene.environment;
  const target=renderer.getRenderTarget();
  const pmrem=new T.PMREMGenerator(renderer);
  try {
    car.visible=false;scene.environment=null;
    camera.update(renderer,scene);
    return pmrem.fromCubemap(cube.texture);
  } finally {
    car.visible=visible;scene.environment=environment;renderer.setRenderTarget(target);cube.dispose();pmrem.dispose();
  }
}
