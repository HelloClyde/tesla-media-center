import * as T from 'three';
import { loadStreetTrees } from './teslaTreeAssets';
import { createStreetTree } from './teslaTrees';
import { createAssetCity } from './teslaCityAssets';
import { createVehicleSkyline } from './teslaSkyline';
import { createShopfrontMaterials } from './teslaShopfronts';

// A lightweight streetscape with shared geometry/materials for the car browser.
export function createVehicleStreet(manager?: T.LoadingManager) {
  const group = new T.Group();
  const skyline = createVehicleSkyline();
  const shops = createShopfrontMaterials();
  const city = createAssetCity(manager);
  const fallbackBuildings: T.Group[] = [];
  group.add(city.group);
  const ready = city.ready.then(loaded => { if (loaded) fallbackBuildings.forEach(building => building.visible = false); return loaded; });
  group.add(skyline.group);
  const moving: { group: T.Group; period: number }[] = [];
  let parent: T.Group = group;
  function section(z: number, period: number) {
    parent = new T.Group();
    parent.position.z = z;
    group.add(parent);
    moving.push({ group: parent, period });
  }
  const textures:T.Texture[]=[];
  const loader=new T.TextureLoader(manager);
  function textured(name:string,repeatX=1,repeatY=1) {
    function load(kind:string) {
      const texture=loader.load(`/textures/streetscape/${name}_${kind}.jpg`);
      texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.repeat.set(repeatX,repeatY);texture.anisotropy=4;
      if(kind==='Diffuse')texture.colorSpace=T.SRGBColorSpace;
      textures.push(texture);return texture;
    }
    return new T.MeshStandardMaterial({map:load('Diffuse'),normalMap:load('nor_gl'),roughnessMap:load('Rough'),
      roughness:1,normalScale:new T.Vector2(.65,.65)});
  }
  const concrete = textured('concrete_wall_006');
  const bark = textured('bark_brown_02',1,2.7);
  const trees: T.Group[] = [];
  const facade = textured('brick_wall_001');
  const glass = new T.MeshStandardMaterial({ color: '#354859', roughness: .3, metalness: .3, emissive: '#ffd9a0', emissiveIntensity: 0 });
  const pole = new T.MeshStandardMaterial({ color: '#454b50', metalness: .65, roughness: .45 });
  const bulb = new T.MeshStandardMaterial({ color: '#fff1cf', emissive: '#ffd59a', emissiveIntensity: 0 });
  const box = new T.BoxGeometry(1, 1, 1);
  function mesh(geometry: T.BufferGeometry, material: T.Material, x: number, y: number, z: number, sx=1, sy=1, sz=1) {
    // Box UVs are rescaled per face in metres; long pavements must not stretch one tile.
    if(geometry===box && (material as T.MeshStandardMaterial).map) {
      geometry=geometry.clone();
      const uv=geometry.getAttribute('uv'),normal=geometry.getAttribute('normal');
      const tile=material===concrete ? 2 : 3;
      for(let i=0;i<uv.count;i++) {
        const nx=Math.abs(normal.getX(i)),ny=Math.abs(normal.getY(i));
        const width=nx>.5 ? sz : sx, height=ny>.5 ? sz : sy;
        uv.setXY(i,uv.getX(i)*width/tile,uv.getY(i)*height/tile);
      }
    }
    const m = new T.Mesh(geometry, material); m.position.set(x,y,z); m.scale.set(sx,sy,sz);
    m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
  }
  const lamps: T.PointLight[] = [];
  const lampGroups: T.Group[] = [];
  const lampHalos: T.Sprite[] = [];
  const haloPixels=new Uint8Array(64*64*4);
  for(let y=0;y<64;y++)for(let x=0;x<64;x++){
    const distance=Math.hypot(x-31.5,y-31.5)/31.5,index=(y*64+x)*4;
    haloPixels[index]=255;haloPixels[index+1]=220;haloPixels[index+2]=169;
    haloPixels[index+3]=Math.round(255*Math.pow(Math.max(0,1-distance),3));
  }
  const haloTexture=new T.DataTexture(haloPixels,64,64,T.RGBAFormat);
  haloTexture.needsUpdate=true;
  const haloMaterial=new T.SpriteMaterial({map:haloTexture,color:'#ffe4b8',transparent:true,opacity:.9,depthWrite:false,blending:T.AdditiveBlending});
  let parked = true, nightMode = false;
  function updateLampVisibility() {
    // Keep light objects in the scene in both modes so material shaders do not
    // recompile when night is toggled. Hide only the near poles while parked.
    for (const lamp of lampGroups) {
      const showPole = nightMode || !parked || Math.abs(lamp.position.z) >= 15;
      for (const child of lamp.children) if (child instanceof T.Mesh) child.visible = showPole;
    }
    // Two shadowless lights are enough to shade the car without multiplying shadow work.
    const nearest = [...lamps].sort((a,b) => Math.abs(a.parent!.position.z) - Math.abs(b.parent!.position.z)).slice(0,2);
    for (const light of lamps) light.visible = nearest.includes(light);
  }
  for (const side of [-1, 1]) {
    parent = group;
    mesh(box, concrete, side*10, .08, 0, 4, .16, 150);
    mesh(box, concrete, side*7.95, .12, 0, .16, .24, 150);
    for (let i=0; i<14; i++) {
      section(i*10-65, 140);
      const tree=createStreetTree(471+i*37+(side===1?163:0),bark);
      tree.position.x=side*(10.1+(i%3)*.3);
      parent.add(tree); trees.push(tree);
    }
    for (let i=0; i<10; i++) {
      section(i*15-67, 150);
      fallbackBuildings.push(parent);
      const z=0, height=8+(i*7%5)*2.5;
      const variant=(i+(side===1?2:0))%5;
      const style=shops.styles[variant];
      const wall=(variant===2||variant===3?concrete:facade).clone();wall.color.set(['#d2b59c','#c9c3b7','#e9e1cf','#aebcc5','#b7a095'][variant]);
      mesh(box, wall, side*19, height/2, z, 8, height, 12);
      // Recessed shop fronts, horizontal stone bands and projecting window sills.
      function frontage(material:T.Material, y:number, z:number, width:number, height:number, x=14.78) {
        const face=new T.Mesh(new T.PlaneGeometry(width,height),material);
        face.rotation.y=-side*Math.PI/2;face.position.set(side*x,y,z);parent.add(face);
      }
      // Individual shop windows and a separate glazed entrance with frame/handle/step.
      for(const z of [-4.05,-1.35,4.05]) {
        frontage(style.interior,1.35,z,2.35,2.25);
        mesh(box,style.trim,side*14.72,1.35,z-1.2,.16,2.4,.09);
        mesh(box,style.trim,side*14.72,1.35,z+1.2,.16,2.4,.09);
      }
      frontage(style.interior,1.27,1.35,1.15,2.25);
      for(const z of [.72,1.98])mesh(box,style.trim,side*14.7,1.27,z,.2,2.5,.11);
      mesh(box,style.trim,side*14.7,2.5,1.35,.2,.13,1.35);
      mesh(box,pole,side*14.55,1.2,1.73,.05,.42,.045);
      mesh(box,concrete,side*14.35,.09,1.35,1.1,.18,1.7);
      frontage(style.sign,2.93,0,10.7,.65,14.65);
      if(variant===0||variant===1||variant===4) {
        const canopy=mesh(box,style.trim,side*14.1,2.58,0,1.8,.12,11.2);
        canopy.rotation.z=side*.1;
      }
      if(variant!==3)for(let f=1;f<Math.floor(height/2.5);f++) mesh(box,concrete,side*14.9,f*2.5+.8,0,.22,.12,12);
      if(variant===2||variant===4)for(const z of [-5.85,0,5.85])mesh(box,concrete,side*14.7,height/2,z,.45,height,.25);
      mesh(box, concrete, side*19, height+.12, z, 8.3, .24, 12.3);
      for (let floor=1; floor<Math.floor(height/2.5); floor++) for (let column=0; column<4; column++) {
        const wy=1.7+floor*2.5,wz=z-4.5+column*3;
        frontage((floor+column+i)%3===0?style.interior:glass,wy,wz,variant===3?2.2:1.5,1.3,14.85);
        mesh(box,pole,side*14.94,wy,wz,.06,1.32,.045);
        mesh(box,concrete,side*14.8,wy-.7,wz,.4,.1,1.75);
        if(i%3===1 && floor>0) {
          mesh(box,concrete,side*14.35,wy-.8,wz,1.4,.15,2.1);
          mesh(box,pole,side*13.68,wy-.3,wz,.06,.05,2.1);
          for(let rail=0;rail<5;rail++) mesh(box,pole,side*13.68,wy-.55,wz-.95+rail*.475,.035,.5,.035);
        }
      }
    }
    for (const origin of [-60, 0, 60]) {
      section(origin, 180);
      lampGroups.push(parent);
      const z = 0;
      mesh(box,pole,side*8.35,2.7,z,.1,5.4,.1);
      mesh(box,pole,side*7.95,5.35,z,.9,.08,.1);
      mesh(box,bulb,side*7.55,5.3,z,.5,.07,.28);
      const halo=new T.Sprite(haloMaterial);halo.position.set(side*7.55,5.3,z);halo.scale.set(1.6,1.6,1);halo.visible=false;parent.add(halo);lampHalos.push(halo);
      const light=new T.PointLight('#ffd49a',0,16,2);light.position.set(side*7.55,5.1,z);light.castShadow=false;parent.add(light);lamps.push(light);
    }
  }
  const treeAssets=loadStreetTrees(trees, manager);
  updateLampVisibility();
  return { group, ready: Promise.all([ready, treeAssets.ready]), setParked(value: boolean) {
    if (parked === value) return;
    parked = value; updateLampVisibility();
  }, advance(distance: number) {
    if (!Number.isFinite(distance) || distance === 0) return;
    skyline.advance(distance);
    city.advance(distance);
    for (const item of moving) {
      item.group.position.z = wrapStreetPosition(item.group.position.z + distance, item.period);
    }
    updateLampVisibility();
  }, setNight(night: boolean) {
    nightMode = night; updateLampVisibility();
    skyline.setNight(night);
    city.setNight(night);
    shops.setNight(night);
    glass.emissiveIntensity=night ? .65 : 0;
    bulb.emissiveIntensity=night ? 5 : 0;
    lampHalos.forEach(halo=>halo.visible=night);
    lamps.forEach(light=>light.intensity=night ? 70 : 0);
  }, dispose() {
    treeAssets.dispose();
    city.dispose();
    skyline.dispose();
    shops.dispose();
    const geometries=new Set<T.BufferGeometry>(), materials=new Set<T.Material>();
    group.traverse(o=>{if(o instanceof T.Mesh){geometries.add(o.geometry);materials.add(o.material as T.Material);}});
    facade.dispose();textures.forEach(t=>t.dispose());trees.forEach(tree=>tree.userData.dispose());geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());group.removeFromParent();
    haloMaterial.dispose();haloTexture.dispose();
  }};
}

// Recycle complete objects beyond the visible foreground, preserving all their parts.
export function wrapStreetPosition(z: number, period: number) {
  return ((z + period / 2) % period + period) % period - period / 2;
}
