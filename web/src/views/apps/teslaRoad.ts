import * as THREE from 'three';

export const ROAD_TEXTURE_LENGTH = 96;
const ROAD_WIDTH = 16, ROAD_LENGTH = 384;

function surface(park: boolean) {
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 4096;
  const ctx = canvas.getContext('2d')!;
  let seed = 42;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  // Work in metres, with a complete road section instead of an isolated patch.
  ctx.scale(canvas.width / ROAD_WIDTH, canvas.height / ROAD_TEXTURE_LENGTH);
  ctx.translate(ROAD_WIDTH / 2, 0);
  for (const x of [-6.8, -3.8, -.65, .65, 3.3, 4.7]) {
    const wear = ctx.createLinearGradient(x - .3, 0, x + .3, 0);
    wear.addColorStop(0, '#0000'); wear.addColorStop(.5, '#00000018'); wear.addColorStop(1, '#0000');
    ctx.fillStyle = wear; ctx.fillRect(x - .3, 0, .6, ROAD_TEXTURE_LENGTH);
  }
  // Sealed repairs, patchwork and occasional utility covers break up flat asphalt.
  for (let i = 0; i < 18; i++) {
    const x = random() * 14 - 7, y = random() * ROAD_TEXTURE_LENGTH;
    ctx.fillStyle = i % 2 ? '#0000000b' : '#c4c9cc0c';
    ctx.fillRect(x, y, .5 + random() * 1.6, .8 + random() * 3);
    ctx.strokeStyle = '#20282b88'; ctx.lineWidth = .025;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + .25, y + .6); ctx.lineTo(x + .12, y + 1); ctx.stroke();
  }
  function line(x: number, color: string, dashed = false) {
    ctx.strokeStyle = color; ctx.lineWidth = .10; ctx.setLineDash(dashed ? [3, 6] : []);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, ROAD_TEXTURE_LENGTH); ctx.stroke();
  }
  line(-1.85, '#d6b768'); line(-2.05, '#d6b768');
  for (const x of [-5.15, 1.8, 5.1]) line(x, '#d1d3cc', true);
  for (const x of [-7.4, 7.4]) line(x, '#d1d3cc');
  ctx.setLineDash([]);
  for (const x of [-7.85, 7.85]) {
    ctx.fillStyle = '#777b7c'; ctx.fillRect(x - .15, 0, .3, ROAD_TEXTURE_LENGTH);
    ctx.strokeStyle = '#333b3d'; ctx.lineWidth = .025;
    for (let z = 0; z < ROAD_TEXTURE_LENGTH; z += 3) {
      ctx.beginPath();ctx.moveTo(x - .15, z);ctx.lineTo(x + .15, z);ctx.stroke();
    }
    for (let z = 6; z < ROAD_TEXTURE_LENGTH; z += 18) {
      ctx.fillStyle = '#262f33';ctx.fillRect(x - .17, z, .34, .7);
      ctx.strokeStyle = '#596065';ctx.lineWidth = .025;
      for (let j = 0; j < 7; j++) {ctx.beginPath();ctx.moveTo(x - .14, z + j * .1);ctx.lineTo(x + .14, z + j * .1);ctx.stroke();}
    }
  }
  for (const [x, y] of [[3.5, 18], [-3.5, 65]]) {
    ctx.fillStyle = '#424a4e';ctx.strokeStyle = '#242c30';ctx.lineWidth = .045;
    ctx.beginPath();ctx.ellipse(x, y, .36, .36, 0, 0, Math.PI * 2);ctx.fill();ctx.stroke();
    ctx.strokeStyle = '#747a7c';ctx.lineWidth = .016;
    for (let j = -2; j <= 2; j++) {ctx.beginPath();ctx.moveTo(x - .24, y + j * .08);ctx.lineTo(x + .24, y + j * .08);ctx.stroke();}
  }
  // One crossing per block, with stop lines and direction arrows before it.
  ctx.fillStyle = '#dadbd0';
  for (let x = -7.2; x < 7.2; x += 1.05) ctx.fillRect(x, 44, .55, 3.6);
  ctx.fillRect(-1.65, 50, 8.9, .2);ctx.fillRect(-7.3, 41.5, 5.1, .2);
  for (const x of [0, 3.45, 6.25]) {
    ctx.fillRect(x - .085, 55, .17, 2);
    ctx.beginPath();ctx.moveTo(x, 58);ctx.lineTo(x - .45, 56.7);ctx.lineTo(x + .45, 56.7);ctx.closePath();ctx.fill();
  }
  if (park) {
    ctx.strokeStyle = '#d7d9d2'; ctx.lineWidth = .08;
    for (const y of [0, ROAD_TEXTURE_LENGTH]) ctx.strokeRect(-1.4, y - 2.75, 2.8, 5.5);
  }
  // Wear belongs to the road texture, so it travels with the road and its markings.
  ctx.globalCompositeOperation='destination-out';
  for(let i=0;i<6500;i++) {
    ctx.fillStyle=`rgba(0,0,0,${.12+random()*.45})`;
    ctx.fillRect(random()*16-8,random()*ROAD_TEXTURE_LENGTH,.015+random()*.06,.02+random()*.12);
  }
  ctx.globalCompositeOperation='source-over';
  const composite = document.createElement('canvas'); composite.width = canvas.width; composite.height = canvas.height;
  const base = composite.getContext('2d')!; base.fillStyle = '#41464a';base.fillRect(0,0,composite.width,composite.height);base.drawImage(canvas,0,0);
  const texture = new THREE.CanvasTexture(composite);
  texture.userData.markings = canvas;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.y = ROAD_LENGTH / ROAD_TEXTURE_LENGTH;
  texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 8;
  return texture;
}

export function createVehicleRoadMesh() {
  const driveTexture = surface(false), parkTexture = surface(true);
  const loader = new THREE.TextureLoader();
  function detail(name: string) {
    const texture = loader.load(`/textures/city-sample/asphalt-${name}.jpg`);
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(ROAD_WIDTH / 4, ROAD_LENGTH / 4); texture.anisotropy = 8;
    return texture;
  }
  const normal = detail('normalgl'), roughness = detail('roughness');
  let disposed = false;
  const image = new Image();
  image.onload = () => {
    if (disposed) return;
    for (const texture of [driveTexture, parkTexture]) {
      const canvas = texture.image as HTMLCanvasElement, ctx = canvas.getContext('2d')!;
      const width = canvas.width * 4 / ROAD_WIDTH, height = canvas.height * 4 / ROAD_TEXTURE_LENGTH;
      for (let y=0; y<canvas.height; y+=height) for(let x=0;x<canvas.width;x+=width) ctx.drawImage(image,x,y,width,height);
      ctx.drawImage(texture.userData.markings,0,0); texture.needsUpdate = true;
    }
  };
  image.src = '/textures/city-sample/asphalt-color.jpg';
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: .94,
    map: parkTexture, normalMap: normal, normalScale: new THREE.Vector2(.28,.28), roughnessMap: roughness });
  const road = new THREE.Mesh(new THREE.PlaneGeometry(ROAD_WIDTH, ROAD_LENGTH), material);
  // Opaque ground extends to the horizon instead of fading into a blank backdrop.
  const surround = new THREE.Mesh(new THREE.PlaneGeometry(600, 600),
    new THREE.MeshStandardMaterial({ color: '#41494b', roughness: .96 }));
  surround.position.z = -.006; surround.receiveShadow = true;
  road.add(surround);
  road.receiveShadow = true;
  road.rotation.x = -Math.PI/2; road.position.set(0,-.82,.45);
  road.userData.updateTravel = (distance: number) => { normal.offset.y = roughness.offset.y = distance / 4; };
  road.userData.disposeDetails = () => { disposed = true; image.onload = null; normal.dispose(); roughness.dispose(); };
  road.userData.textureLength = ROAD_TEXTURE_LENGTH;
  road.userData.driveTexture = driveTexture; road.userData.parkTexture = parkTexture;
  return road;
}
