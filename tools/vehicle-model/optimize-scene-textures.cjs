// Recompress scene textures without reducing resolution or simplifying geometry.
const {NodeIO}=require('../../web/node_modules/@gltf-transform/core');
const {ALL_EXTENSIONS}=require('../../web/node_modules/@gltf-transform/extensions');
const {MeshoptEncoder,MeshoptDecoder}=require('../../web/node_modules/meshoptimizer');
const sharp=require('../../web/node_modules/sharp');
const fs=require('fs'),path=require('path');
(async()=>{
 await Promise.all([MeshoptEncoder.ready,MeshoptDecoder.ready]);
 const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.encoder':MeshoptEncoder,'meshopt.decoder':MeshoptDecoder});
 const backup='.local-data/scene-size-originals';fs.mkdirSync(backup,{recursive:true});
 let before=0,after=0;
 for(const folder of ['web/public/models/city-sample','web/public/textures/city-sample','web/public/textures/streetscape'])for(const file of fs.readdirSync(folder)){
  if(!/\.(glb|jpg|png)$/.test(file))continue;
  const target=path.join(folder,file),original=path.join(backup,file);
  if(!fs.existsSync(original))fs.copyFileSync(target,original);
  const input=fs.readFileSync(original);before+=input.length;
  if(file.endsWith('.glb')){
   const doc=await io.read(original);
   for(const texture of doc.getRoot().listTextures()){
    const source=Buffer.from(texture.getImage()),img=sharp(source),stats=await img.stats();
    const alpha=!stats.isOpaque;
    const bytes=alpha?await sharp(source).png({compressionLevel:9,effort:10}).toBuffer():await sharp(source).removeAlpha().jpeg({quality:84,chromaSubsampling:'4:4:4',mozjpeg:true}).toBuffer();
    if(bytes.length<source.length)texture.setImage(bytes).setMimeType(alpha?'image/png':'image/jpeg').setURI('');
   }
   const bytes=Buffer.from(await io.writeBinary(doc));if(bytes.length<input.length)fs.writeFileSync(target,bytes);
  }else{
   // Keep public URLs stable. JPEG inputs retain full resolution and 4:4:4 chroma.
   const image=sharp(input);
   if(file.endsWith('.jpg')){const bytes=await image.jpeg({quality:84,chromaSubsampling:'4:4:4',mozjpeg:true}).toBuffer();if(bytes.length<input.length)fs.writeFileSync(target,bytes);}
   else if(file==='brick-realistic.png'){const output=target.replace(/png$/,'jpg');fs.writeFileSync(output,await image.jpeg({quality:88,chromaSubsampling:'4:4:4',mozjpeg:true}).toBuffer());fs.unlinkSync(target);after+=fs.statSync(output).size;console.log(file,input.length,'->',fs.statSync(output).size);continue;}
  }
  const size=fs.statSync(target).size;after+=size;console.log(file,input.length,'->',size);
 }
 console.log({before,after,reduction:1-after/before});
})().catch(e=>{console.error(e);process.exitCode=1;});
