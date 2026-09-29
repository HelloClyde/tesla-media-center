const {NodeIO,Document}=require('../../web/node_modules/@gltf-transform/core');
const {ALL_EXTENSIONS}=require('../../web/node_modules/@gltf-transform/extensions');
const {mergeDocuments,dedup,meshopt,prune,unpartition}=require('../../web/node_modules/@gltf-transform/functions');
const {MeshoptEncoder,MeshoptDecoder}=require('../../web/node_modules/meshoptimizer');
const sharp=require('../../web/node_modules/sharp');
const fs=require('fs'),path=require('path');
(async()=>{
await Promise.all([MeshoptEncoder.ready,MeshoptDecoder.ready]);
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.encoder':MeshoptEncoder,'meshopt.decoder':MeshoptDecoder});
const doc=new Document();
const source=process.argv[2]||'.local-data/city-assets/source';
for(const name of ['Building_Large_2','Building_Medium_2_001','Building_Small_1'])mergeDocuments(doc,await io.read(path.join(source,name+'.gltf')));
const scenes=doc.getRoot().listScenes(),scene=scenes[0];
for(const other of scenes.slice(1)){for(const node of other.listChildren())scene.addChild(node);other.dispose();}
doc.getRoot().setDefaultScene(scene);
await doc.transform(dedup());
for(const texture of doc.getRoot().listTextures()){
 const image=sharp(Buffer.from(texture.getImage()));const info=await image.metadata();
 const resized=image.resize({width:1024,height:1024,fit:'inside',withoutEnlargement:true});
 const bytes=info.hasAlpha?await resized.png().toBuffer():await resized.jpeg({quality:87}).toBuffer();
 texture.setImage(bytes).setMimeType(info.hasAlpha?'image/png':'image/jpeg').setURI('');
}
await doc.transform(dedup(),prune(),meshopt({encoder:MeshoptEncoder,level:'medium'}),unpartition());
fs.mkdirSync('web/public/models/city-sample',{recursive:true});
const output='web/public/models/city-sample/downtown.glb';await io.write(output,doc);
console.log({bytes:fs.statSync(output).size,materials:doc.getRoot().listMaterials().length,textures:doc.getRoot().listTextures().length,buildings:scene.listChildren().map(n=>n.getName())});
})().catch(e=>{console.error(e);process.exitCode=1});
