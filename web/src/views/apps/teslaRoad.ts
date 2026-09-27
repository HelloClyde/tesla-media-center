import * as THREE from 'three';

// 6.4 x 18 metres. Paint belongs to the ground, not to the vehicle centreline.
function surface(park: boolean) {
  const canvas = document.createElement('canvas');
  canvas.width = 512; canvas.height = 1024;
  const ctx = canvas.getContext('2d')!;
  const pixels = ctx.createImageData(512, 1024);
  let seed = 42;
  for (let i = 0; i < pixels.data.length; i += 4) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const tone = (park ? 161 : 77) + (seed / 4294967296 - .5) * 9;
    pixels.data.set([tone, tone + 4, tone + 8, 255], i);
  }
  ctx.putImageData(pixels, 0, 0);
  ctx.strokeStyle = park ? '#e7ebeb' : '#d7dddd';
  ctx.lineWidth = 6; ctx.lineCap = 'butt';
  if (park) {
    // A 2.8 m wide bay, with subtle neighbouring bays and expansion joints.
    for (const x of [32, 144, 368, 480]) {
      ctx.beginPath(); ctx.moveTo(x, 355); ctx.lineTo(x, 685); ctx.stroke();
    }
    ctx.beginPath(); ctx.moveTo(32, 355); ctx.lineTo(480, 355); ctx.stroke();
    ctx.strokeStyle = 'rgba(75,87,96,.12)'; ctx.lineWidth = 1;
    for (const y of [170, 512, 854]) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(512,y); ctx.stroke(); }
  } else {
    for (const x of [116, 396]) {
      ctx.setLineDash(x === 116 ? [170, 170] : []);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 1024); ctx.stroke();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

export function createVehicleRoadMesh() {
  const driveTexture = surface(false), parkTexture = surface(true);
  const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 256;
  const ctx = canvas.getContext('2d')!;
  const pixels = ctx.createImageData(128, 256);
  for (let y=0; y<256; y++) for (let x=0; x<128; x++) {
    const edge = Math.min(x/20, (127-x)/20, y/65, (255-y)/65, 1);
    const v = Math.max(0, edge); const a = 255*v*v*(3-2*v);
    pixels.data.set([a,a,a,255], (y*128+x)*4);
  }
  ctx.putImageData(pixels,0,0);
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 1,
    map: parkTexture, alphaMap: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false });
  const road = new THREE.Mesh(new THREE.PlaneGeometry(6.4,18), material);
  road.receiveShadow = true;
  road.rotation.x = -Math.PI/2; road.position.set(0,-.82,.45);
  road.userData.driveTexture = driveTexture; road.userData.parkTexture = parkTexture;
  return road;
}
