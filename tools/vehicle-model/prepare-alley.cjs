const {NodeIO}=require('../../web/node_modules/@gltf-transform/core');const {ALL_EXTENSIONS}=require('../../web/node_modules/@gltf-transform/extensions');const {dedup,prune,flatten,join,weld,simplify,meshopt,unpartition}=require('../../web/node_modules/@gltf-transform/functions');const {MeshoptEncoder,MeshoptDecoder,MeshoptSimplifier}=require('../../web/node_modules/meshoptimizer');const sharp=require('../../web/node_modules/sharp');
(async()=>{await Promise.all([MeshoptEncoder.ready,MeshoptSimplifier.ready]);const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.encoder':MeshoptEncoder,'meshopt.decoder':MeshoptDecoder});const d=await io.read('.local-data/facade-source/modular_urban_apartments_facade_1k.gltf');const scene=d.getRoot().listScenes()[0],source=new Map(scene.listChildren().map(n=>[n.getName(),n]));for(const n of scene.listChildren())scene.removeChild(n);
const building=d.createNode('Alley_apartments');scene.addChild(building);
function part(parent,name,offset){const src=source.get(name);if(!src)throw Error(name);const node=d.createNode(name).setMesh(src.getMesh()).setRotation(src.getRotation()).setScale(src.getScale());const t=src.getTranslation();node.setTranslation(t.map((v,i)=>v+offset[i]));parent.addChild(node);}
for(let side=0;side<4;side++){const count=side%2?4:5;const face=d.createNode('facade');face.setRotation([0,Math.sin(side*Math.PI/4),0,Math.cos(side*Math.PI/4)]);face.setTranslation([[0,0,0],[7.5,0,-6],[0,0,-12],[-7.5,0,-6]][side]);building.addChild(face);
for(let col=0;col<count;col++){const x=(col-(count-1)/2)*3;
for(let floor=0;floor<6;floor++){
 if(floor===0&&col===Math.floor(count/2)){for(const name of ['wall_door_centered_large_01','door_centered_large_01'])part(face,name,[x-9.5,0,0]);}
 else {const v=1+(col+floor+side)%3;for(const prefix of ['wall_window_centered_large_','window_centered_large_'])part(face,prefix+String(v).padStart(2,'0'),[x-9.5,floor*3-v*4,0]);}
}
part(face,'crown_standard_standard_01',[x+1.5,14,0]);
}}
for(const n of source.values())n.dispose();await d.transform(prune(),flatten(),join(),dedup(),weld(),simplify({simplifier:MeshoptSimplifier,ratio:.35,error:.01}));
for(const t of d.getRoot().listTextures()){t.setImage(await sharp(Buffer.from(t.getImage())).resize({width:1024,height:1024,fit:'inside'}).jpeg({quality:86}).toBuffer()).setMimeType('image/jpeg').setURI('');}
await d.transform(meshopt({encoder:MeshoptEncoder,level:'medium'}),unpartition());await io.write('web/public/models/city-sample/alley-apartments.glb',d);
})().catch(e=>{console.error(e);process.exitCode=1;});
