const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const script=html.split('<script>')[1].split('</script>')[0];
const ctx={TextEncoder};vm.createContext(ctx);vm.runInContext(script.split('let p={')[0],ctx);
const project={version:1,language:'Vietnamese',characters:[{name:'Anna',appearance:'Dark hair.\nBlue coat.',voice:'Warm voice.'}],shots:[1,2,3].map(i=>({id:'SC00'+i,characters:['Anna'],speaker:'Anna',dialogue:'Xin chào.',location:'Room\nDaytime',wardrobe:'Coat',action:'Anna turns.\nAnna smiles.',camera:'Close-up',duration:8}))};
ctx.project=project;
for(const mode of ['characters','keyframes']){
const output=vm.runInContext(`videoText(project,'${mode}')`,ctx);const lines=output.split('\n');
assert.equal(lines.length,3);assert(lines.every(line=>line.length>0&&!line.includes('\r')));
assert(lines.every(line=>line.startsWith('Cinematic film, 16:9, 8 seconds.')));
assert(!output.includes('References:'));assert(!output.includes('[SC'));assert(!output.includes('opening keyframe'));
assert.equal((output.match(/Only Anna speaks exactly/g)||[]).length,3);
}
console.log('Video TXT: exactly one complete prompt per shot, no headers or blank lines, both export modes.');
