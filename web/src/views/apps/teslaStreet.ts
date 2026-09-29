import * as T from 'three';

// A lightweight streetscape with shared geometry/materials for the car browser.
export function createVehicleStreet() {
  const group = new T.Group();
  const textures:T.Texture[]=[];
  const loader=new T.TextureLoader();
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
  // Alpha-cut leaf clusters keep the canopy porous, rather than solid green blobs.
  const leafCanvas=document.createElement('canvas'); leafCanvas.width=leafCanvas.height=128;
  const context=leafCanvas.getContext('2d')!;
  let seed=471;
  function random() { seed=(seed*1664525+1013904223)>>>0; return seed/4294967296; }
  for(let i=0;i<23;i++) {
    const x=14+random()*100,y=14+random()*100;
    context.save();context.translate(x,y);context.rotate(random()*Math.PI);
    context.fillStyle=['#466536','#648046','#35502b','#7c914e'][i%4];
    const length=5+random()*5,width=2+random()*3;
    context.beginPath();context.ellipse(0,0,length,width,0,0,Math.PI*2);context.fill();
    context.strokeStyle='rgba(189,192,107,.55)';context.lineWidth=.5;
    context.beginPath();context.moveTo(-length,0);context.lineTo(length,0);
    for(let vein=-2;vein<=2;vein++){context.moveTo(vein*2,0);context.lineTo(vein*2+2,width*.75);context.moveTo(vein*2,0);context.lineTo(vein*2+2,-width*.75);}context.stroke();context.restore();
  }
  const leafTexture=new T.CanvasTexture(leafCanvas);leafTexture.colorSpace=T.SRGBColorSpace;
  const leaves = new T.MeshStandardMaterial({ map:leafTexture, roughness: .85, side:T.DoubleSide, alphaTest:.45 });
  const facade = textured('brick_wall_001');
  const glass = new T.MeshStandardMaterial({ color: '#354859', roughness: .3, metalness: .3, emissive: '#ffd9a0', emissiveIntensity: 0 });
  const pole = new T.MeshStandardMaterial({ color: '#454b50', metalness: .65, roughness: .45 });
  const bulb = new T.MeshStandardMaterial({ color: '#fff1cf', emissive: '#ffd59a', emissiveIntensity: 0 });
  const box = new T.BoxGeometry(1, 1, 1);
  const trunk = new T.CylinderGeometry(.12, .19, 2.7, 7);
  const leafGeometry = new T.PlaneGeometry(1.1,1.1);
  const foliage=new T.InstancedMesh(leafGeometry, leaves, 28*240);
  foliage.castShadow=true;foliage.receiveShadow=true;group.add(foliage);
  const transform=new T.Object3D();let leafIndex=0;
  const branchGeometry=new T.CylinderGeometry(1,1,1,6);
  function branch(start:T.Vector3,end:T.Vector3,radius:number) {
    const delta=end.clone().sub(start);
    const m=mesh(branchGeometry,bark,0,0,0,radius,delta.length(),radius*.8);
    m.position.copy(start).add(end).multiplyScalar(.5);
    m.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.normalize());
  }
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
    m.castShadow = true; m.receiveShadow = true; group.add(m); return m;
  }
  const lamps: T.PointLight[] = [];
  for (const side of [-1, 1]) {
    mesh(box, concrete, side*10, .08, 0, 4, .16, 150);
    mesh(box, concrete, side*7.95, .12, 0, .16, .24, 150);
    for (let i=0; i<14; i++) {
      const z = i*10-65;
      const x=side*10.5, height=3.8+random()*.7;
      mesh(trunk, bark, x, 1.5, z);
      for(let j=0;j<7;j++) {
        const angle=j*Math.PI*2/7+i;
        branch(new T.Vector3(x,1.9,z),new T.Vector3(x+Math.cos(angle)*1.3,height+.3*random(),z+Math.sin(angle)*1.3),.065);
      }
      for(let j=0;j<240;j++) {
        const theta=random()*Math.PI*2, vertical=random()*2-1, radius=Math.cbrt(random())*1.85;
        const horizontal=Math.sqrt(1-vertical*vertical);
        transform.position.set(x+Math.cos(theta)*horizontal*radius,height+vertical*radius*.8,z+Math.sin(theta)*horizontal*radius);
        transform.rotation.set(random()*Math.PI,random()*Math.PI,random()*Math.PI);
        transform.scale.setScalar(.65+random()*.65);transform.updateMatrix();foliage.setMatrixAt(leafIndex++,transform.matrix);
      }
    }
    for (let i=0; i<10; i++) {
      const z=i*15-67, height=8+(i*7%5)*2.5;
      const wall=facade.clone();wall.color.set(['#ffffff','#c9c3b7','#ebe1cc','#b3b3aa'][i%4]);
      mesh(box, wall, side*19, height/2, z, 8, height, 12);
      // Recessed shop fronts, horizontal stone bands and projecting window sills.
      mesh(box,glass,side*14.94,1.35,z,.06,2.2,10.6);
      mesh(box,concrete,side*14.6,2.65,z,.9,.18,11);
      for(let f=1;f<Math.floor(height/2.5);f++) mesh(box,concrete,side*14.9,f*2.5,z,.22,.12,12);
      for(let c=0;c<5;c++) mesh(box,concrete,side*14.8,1.35,z-5+c*2.5,.3,2.7,.14);
      mesh(box, concrete, side*19, height+.12, z, 8.3, .24, 12.3);
      for (let floor=0; floor<Math.floor(height/2.5); floor++) for (let column=0; column<4; column++) {
        const wy=1.7+floor*2.5,wz=z-4.5+column*3;
        mesh(box, glass, side*14.98, wy, wz, .035, 1.3, 1.5);
        mesh(box,pole,side*14.94,wy,wz,.06,1.32,.045);
        mesh(box,concrete,side*14.8,wy-.7,wz,.4,.1,1.75);
        if(i%3===1 && floor>0) {
          mesh(box,concrete,side*14.35,wy-.8,wz,1.4,.15,2.1);
          mesh(box,pole,side*13.68,wy-.3,wz,.06,.05,2.1);
          for(let rail=0;rail<5;rail++) mesh(box,pole,side*13.68,wy-.55,wz-.95+rail*.475,.035,.5,.035);
        }
      }
    }
    for (const z of [-22, 0, 22]) {
      mesh(box,pole,side*4.9,2.7,z,.1,5.4,.1);
      mesh(box,pole,side*4.5,5.35,z,.9,.08,.1);
      mesh(box,bulb,side*4.1,5.3,z,.5,.07,.28);
      const light=new T.PointLight('#ffd49a',0,16,2);light.position.set(side*4.1,5.1,z);group.add(light);lamps.push(light);
    }
  }
  return { group, setNight(night: boolean) {
    glass.emissiveIntensity=night ? .65 : 0;
    bulb.emissiveIntensity=night ? 5 : 0;
    lamps.forEach(light=>light.intensity=night ? 70 : 0);
  }, dispose() {
    const geometries=new Set<T.BufferGeometry>(), materials=new Set<T.Material>();
    group.traverse(o=>{if(o instanceof T.Mesh){geometries.add(o.geometry);materials.add(o.material as T.Material);}});
    facade.dispose();textures.forEach(t=>t.dispose());foliage.dispose();leafTexture.dispose();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());group.removeFromParent();
  }};
}
