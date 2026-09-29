const {NodeIO}=require('../../web/node_modules/@gltf-transform/core');
const {ALL_EXTENSIONS}=require('../../web/node_modules/@gltf-transform/extensions');
const {dedup,prune,weld,simplify,meshopt,unpartition}=require('../../web/node_modules/@gltf-transform/functions');
const {MeshoptEncoder,MeshoptDecoder,MeshoptSimplifier}=require('../../web/node_modules/meshoptimizer');
const sharp=require('../../web/node_modules/sharp');
(async()=>{await Promise.all([MeshoptEncoder.ready,MeshoptSimplifier.ready]);const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.encoder':MeshoptEncoder,'meshopt.decoder':MeshoptDecoder});const doc=await io.read('.local-data/tree-source/island_tree_01_1k.gltf');
const count=()=>doc.getRoot().listMeshes().reduce((n,m)=>n+m.listPrimitives().reduce((a,p)=>a+(p.getIndices()?.getCount()||0)/3,0),0);console.log('before',count());
await doc.transform(weld(),simplify({simplifier:MeshoptSimplifier,ratio:.1,error:.006}),dedup(),prune());
for(const texture of doc.getRoot().listTextures()){texture.setImage(await sharp(Buffer.from(texture.getImage())).resize({width:1024,height:1024,fit:'inside',withoutEnlargement:true}).jpeg({quality:85}).toBuffer()).setMimeType('image/jpeg').setURI('');}
for(const material of doc.getRoot().listMaterials())material.setAlphaMode('OPAQUE');
console.log('after',count());await doc.transform(meshopt({encoder:MeshoptEncoder,level:'medium'}),unpartition());await io.write('web/public/models/city-sample/tree.glb',doc);
})().catch(e=>{console.error(e);process.exitCode=1;});
