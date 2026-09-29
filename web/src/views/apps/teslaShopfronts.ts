import * as T from 'three';

/** Shared interior cards: visible depth behind shop glass without a heavy room mesh. */
export function createShopfrontMaterials() {
  const names = ['COFFEE', 'BOOKS', 'MARKET', 'ATELIER', 'RESIDENCE'];
  const colors = ['#31584f', '#773f35', '#546749', '#384958', '#655d53'];
  const textures: T.Texture[] = [], interiors: T.MeshBasicMaterial[] = [];
  function texture(canvas: HTMLCanvasElement) {
    const map = new T.CanvasTexture(canvas); map.colorSpace = T.SRGBColorSpace; map.anisotropy = 4; textures.push(map); return map;
  }
  const styles = names.map((name, index) => {
    const canvas = document.createElement('canvas'); canvas.width = 512; canvas.height = 384;
    const ctx = canvas.getContext('2d')!;
    const wall = ['#b6a38c', '#bbaf93', '#a5b2a0', '#afbbc4', '#b4aea3'][index];
    ctx.fillStyle = '#4a4844'; ctx.fillRect(0, 0, 512, 384);
    ctx.fillStyle = wall; ctx.fillRect(75, 48, 362, 222);
    function polygon(points: number[][], color: string) {
      ctx.fillStyle = color; ctx.beginPath(); points.forEach(([x,y], i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.closePath(); ctx.fill();
    }
    polygon([[0,0],[512,0],[437,48],[75,48]], '#ded3bc');
    polygon([[0,384],[512,384],[437,270],[75,270]], '#756652');
    polygon([[0,0],[75,48],[75,270],[0,384]], '#8b8578');
    polygon([[512,0],[437,48],[437,270],[512,384]], '#777c77');
    ctx.strokeStyle = '#b7a68a'; ctx.lineWidth = 2;
    for (let x=-200;x<800;x+=100) {ctx.beginPath();ctx.moveTo(256+(x-256)*.25,270);ctx.lineTo(x,384);ctx.stroke();}
    for (const y of [290,322,365]) {ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(512,y);ctx.stroke();}
    if (index === 1 || index === 2) {
      for (let row=0;row<4;row++) {
        ctx.fillStyle='#3b332d';ctx.fillRect(95,85+row*40,315,7);
        for(let column=0;column<19;column++) {ctx.fillStyle=['#b96a4e','#c2a45e','#648e80','#eee1b4','#6d7e91'][(row*7+column)%5];ctx.fillRect(99+column*16,62+row*40,10,22);}
      }
    } else {
      ctx.fillStyle='#413e38';ctx.fillRect(115,74,118,88);ctx.fillStyle='#a7b9af';ctx.fillRect(122,81,104,74);
      ctx.fillStyle='#dac08c';ctx.beginPath();ctx.arc(174,112,23,0,Math.PI*2);ctx.fill();
      ctx.fillStyle=colors[index];ctx.fillRect(268,166,125,78);ctx.fillRect(263,186,137,22);
      ctx.fillStyle='#604b37';ctx.fillRect(108,218,139,17);ctx.fillRect(121,235,9,47);ctx.fillRect(226,235,9,47);
      ctx.fillStyle='#e5d8bd';ctx.fillRect(145,203,16,15);ctx.fillRect(190,204,14,14);
    }
    for(const x of [150,350]) {ctx.strokeStyle='#484337';ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,45);ctx.stroke();polygon([[x-27,60],[x+27,60],[x+14,42],[x-14,42]],'#ffe4a8');}
    ctx.fillStyle='#6d573e';ctx.fillRect(390,243,26,37);
    for(let i=0;i<7;i++){ctx.fillStyle=i%2?'#436c40':'#607d49';ctx.beginPath();ctx.ellipse(402+(i%3-1)*12,219-i*5,10,23,(i-3)*.3,0,Math.PI*2);ctx.fill();}
    // Subtle reflected glazing while keeping furniture and shelves visible.
    const reflection=ctx.createLinearGradient(0,0,512,384);reflection.addColorStop(0,'#bfe3ee30');reflection.addColorStop(.5,'#ffffff06');reflection.addColorStop(1,'#a8d1e71a');ctx.fillStyle=reflection;ctx.fillRect(0,0,512,384);
    const map=texture(canvas), interior=new T.MeshBasicMaterial({map,color:'#9aa8ad',toneMapped:false});interiors.push(interior);
    const sign=document.createElement('canvas');sign.width=512;sign.height=96;const text=sign.getContext('2d')!;
    text.fillStyle=colors[index];text.fillRect(0,0,512,96);text.strokeStyle='#d6c9a8';text.strokeRect(7,7,498,82);text.fillStyle='#f3ecd9';text.font='500 42px sans-serif';text.textAlign='center';text.textBaseline='middle';text.fillText(name,256,50);
    const signMap=texture(sign), signMaterial=new T.MeshStandardMaterial({map:signMap,roughness:.8});
    const trim=new T.MeshStandardMaterial({color:colors[index],roughness:.7});
    return {interior,sign:signMaterial,trim};
  });
  return {styles,setNight(night:boolean){interiors.forEach(m=>m.color.set(night ? '#e6d1ad' : '#9aa8ad'));},dispose(){textures.forEach(t=>t.dispose());styles.forEach(s=>{s.interior.dispose();s.sign.dispose();s.trim.dispose();});}};
}
