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
    const tone = (park ? 91 : 77) + (seed / 4294967296 - .5) * 9;
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
  // Fine aggregate relief, independent of painted parking/road markings.
  const grain = document.createElement('canvas'); grain.width = grain.height = 256;
  const ctx = grain.getContext('2d')!;
  const pixels = ctx.createImageData(256, 256);
  let seed = 1337;
  for (let i = 0; i < pixels.data.length; i += 4) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const value = 95 + (seed >>> 24) * .25;
    pixels.data.set([value, value, value, 255], i);
  }
  ctx.putImageData(pixels, 0, 0);
  const bump = new THREE.CanvasTexture(grain);
  bump.wrapS = bump.wrapT = THREE.RepeatWrapping;
  bump.repeat.set(8, 22); bump.anisotropy = 8;
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: .94,
    map: parkTexture, bumpMap: bump, bumpScale: .008 });
  const road = new THREE.Mesh(new THREE.PlaneGeometry(6.4,18), material);
  // Opaque ground extends to the horizon instead of fading into a blank backdrop.
  const surround = new THREE.Mesh(new THREE.PlaneGeometry(600, 600),
    new THREE.MeshStandardMaterial({ color: '#5b6065', roughness: .96, bumpMap: bump, bumpScale: .008 }));
  surround.position.z = -.006; surround.receiveShadow = true;
  road.add(surround);
  road.receiveShadow = true;
  road.rotation.x = -Math.PI/2; road.position.set(0,-.82,.45);
  road.userData.driveTexture = driveTexture; road.userData.parkTexture = parkTexture;
  return road;
}
