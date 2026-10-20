import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,existsSync,chmodSync,statSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';
import {prepare,packageFingerprint,safeCacheRead,CODEX_CAPS} from '../bin/serena-lazy.mjs';
const launcher=fileURLToPath(new URL('../bin/serena-lazy.mjs',import.meta.url));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const source=`
import {appendFileSync,readFileSync} from 'node:fs';
appendFileSync(process.env.FAKE_LOG,JSON.stringify({pid:process.pid})+'\\n');
let init=false,state='',buf='',asked;
const send=m=>process.stdout.write(JSON.stringify({jsonrpc:'2.0',...m})+'\\n');
process.stdin.setEncoding('utf8');process.stdin.on('end',()=>process.exit(0));
process.stdin.on('data',chunk=>{buf+=chunk;let n;while((n=buf.indexOf('\\n'))>=0){const raw=buf.slice(0,n);buf=buf.slice(n+1);const m=JSON.parse(raw);
 if(m.method==='initialize'){if(process.env.FAKE_FAIL==='init')send({id:m.id,error:{code:-32000,message:'fixture initialize failed'}});else send({id:m.id,result:{protocolVersion:m.params.protocolVersion,capabilities:{tools:{listChanged:false}},serverInfo:{name:'fake',version:'1'},instructions:'public connection prompt'}});}
 else if(m.method==='notifications/initialized')init=true;
 else if(m.method==='tools/list')send(init?{id:m.id,result:{tools:[{name:readFileSync(process.env.FAKE_CONFIG,'utf8').trim()||'echo',inputSchema:{type:'object'}}]}}:{id:m.id,error:{code:-32000,message:'not initialized'}});
 else if(m.method==='resources/list')send({id:m.id,result:{resources:[]}});
 else if(m.method==='resources/templates/list')send({id:m.id,result:{resourceTemplates:[]}});
 else if(m.method==='prompts/list')send({id:m.id,result:{prompts:[]}});
 else if(m.method==='notify')send({method:'notifications/progress',params:{progress:1}});
 else if(m.method==='die')process.exit(7);
 else if(m.method==='ask'){asked=m.id;send({id:m.id,method:'fixture/question',params:{}});}
 else if(!m.method&&m.id===asked)send({id:asked,result:{reply:m.result}});
 else if(m.id!==undefined){if(!init)send({id:m.id,error:{code:-32000,message:'not initialized'}});else {if(m.method==='set')state=m.params.value;send({id:m.id,result:{pid:process.pid,state,method:m.method}});}}
}});
`;
function fixture(){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'efficiency-serena-')));const pkg=join(dir,'pkg'),home=join(dir,'home');
 mkdirSync(join(pkg,'serena'),{recursive:true});mkdirSync(home);writeFileSync(join(pkg,'serena','test.py'),'# fixture');writeFileSync(join(home,'serena_config.yml'),'echo');
 const backend=join(dir,'backend.mjs');writeFileSync(backend,source);
 return {dir,options:{command:process.execPath,args:[backend],cwd:dir,cacheFile:join(dir,'cache.json'),packageRoot:pkg,
 env:{...process.env,SERENA_HOME:home,FAKE_LOG:join(dir,'launches.jsonl'),FAKE_CONFIG:join(home,'serena_config.yml')},stderr:'pipe'}};
}
function count(f){const p=f.options.env.FAKE_LOG;return existsSync(p)?readFileSync(p,'utf8').trim().split('\n').filter(Boolean).length:0;}
async function seed(f){await prepare(f.options);writeFileSync(f.options.env.FAKE_LOG,'');}
function start(f,overrides={}){
 const opts={...f.options,...overrides};const publicOpts={...opts};delete publicOpts.env;
 const code=`import {run} from ${JSON.stringify(launcher)};const h=run({...${JSON.stringify(publicOpts)},env:process.env,onExit:code=>process.exitCode=code});for(const s of ['SIGTERM','SIGINT'])process.once(s,()=>h.close());`;
 const p=spawn(process.execPath,['--input-type=module','-e',code],{cwd:f.dir,env:opts.env,stdio:['pipe','pipe','pipe']});
 const rows=[],waiters=[];let buf='';p.stdout.setEncoding('utf8');p.stdout.on('data',chunk=>{buf+=chunk;let n;while((n=buf.indexOf('\n'))>=0){const m=JSON.parse(buf.slice(0,n));buf=buf.slice(n+1);if(waiters.length)waiters.shift()(m);else rows.push(m);}});
 const receive=()=>new Promise((resolve,reject)=>{if(rows.length)return resolve(rows.shift());const timer=setTimeout(()=>reject(Error('fixture response timeout')),2000);waiters.push(m=>{clearTimeout(timer);resolve(m);});});
 return {p,send:m=>p.stdin.write(JSON.stringify({jsonrpc:'2.0',...m})+'\n'),receive,
 close:async()=>{p.stdin.end();if(p.exitCode===null&&p.signalCode===null)await Promise.race([once(p,'exit'),pause(4000).then(()=>{if(p.exitCode===null)throw Error('owned fixture did not exit');})]);}};
}
async function boot(c,capabilities=CODEX_CAPS,protocolVersion='2025-06-18'){
 c.send({id:1,method:'initialize',params:{protocolVersion,capabilities,clientInfo:{name:'fixture',version:'1'}}});const init=await c.receive();
 c.send({method:'notifications/initialized'});return init;
}
function noChildren(pid){const rows=execFileSync('ps',['-axo','pid=,ppid='],{encoding:'utf8'}).trim().split('\n');return rows.filter(l=>Number(l.trim().split(/\s+/)[1])===pid).length===0;}

test('valid cache really starts zero backends; all native discovery and first call parity',async t=>{
 const f=fixture();await seed(f);assert.equal(statSync(f.options.cacheFile).mode&0o077,0);
 const c=start(f);t.after(()=>c.close());const init=await boot(c);assert.equal(init.result.protocolVersion,'2025-06-18');
 for(const [i,method]of ['tools/list','resources/templates/list','resources/list','prompts/list'].entries()){
  c.send({id:i+10,method,params:{_meta:{progressToken:i+10}}});const r=await c.receive();assert.equal(r.id,i+10);assert.ok(r.result);
 }
 await pause(100);assert.equal(count(f),0);assert.ok(noChildren(c.p.pid),'unused launcher must have no child');
 c.send({id:1,method:'set',params:{value:'A'}});c.send({id:2,method:'get',params:{}});
 const a=await c.receive(),b=await c.receive();assert.equal(a.id,1);assert.equal(a.result.state,'A');assert.equal(b.result.state,'A');assert.equal(count(f),1);
 c.send({method:'notify'});assert.equal((await c.receive()).method,'notifications/progress');
});
test('two clients retain separate mutable project state and independent backends',async t=>{
 const f=fixture();await seed(f);const a=start(f),b=start(f);t.after(()=>a.close());t.after(()=>b.close());await boot(a,{});await boot(b,{});
 a.send({id:2,method:'set',params:{value:'A'}});b.send({id:2,method:'set',params:{value:'B'}});
 const ra=await a.receive(),rb=await b.receive();assert.notEqual(ra.result.pid,rb.result.pid);assert.equal(ra.result.state,'A');assert.equal(rb.result.state,'B');assert.equal(count(f),2);
});
test('server-initiated request can reuse a client ID without interception',async t=>{
 const f=fixture();await seed(f);const c=start(f);t.after(()=>c.close());await boot(c);
 c.send({id:1,method:'ask'});const req=await c.receive();assert.equal(req.method,'fixture/question');assert.equal(req.id,1);
 c.send({id:1,result:{accepted:true}});assert.deepEqual((await c.receive()).result,{reply:{accepted:true}});
});
test('unknown capabilities, protocol and paginated discovery reach original backend',async t=>{
 for(const [caps,version]of [[{roots:{listChanged:true}},'2025-06-18'],[{},'2025-03-26']]){
  const f=fixture();await seed(f);const c=start(f);t.after(()=>c.close());const r=await boot(c,caps,version);assert.equal(r.result.protocolVersion,version);assert.equal(count(f),1);
 }
 for(const params of [{cursor:'next'},{_meta:{other:'unknown'}}]){
 const f=fixture();await seed(f);const c=start(f);t.after(()=>c.close());await boot(c);c.send({id:2,method:'tools/list',params});assert.ok((await c.receive()).result);assert.equal(count(f),1);
 }
});
test('config/dependency change, malformed and exposed caches fall back without hiding tools',async t=>{
 for(const change of ['config','dependency','malformed','exposed']){
  const f=fixture();await seed(f);
  if(change==='config')writeFileSync(f.options.env.FAKE_CONFIG,'changed');
  if(change==='dependency'){const d=join(f.options.packageRoot,'fake.dist-info');mkdirSync(d);writeFileSync(join(d,'METADATA'),'Version: 2');}
  if(change==='malformed')writeFileSync(f.options.cacheFile,'{bad');
  if(change==='exposed')chmodSync(f.options.cacheFile,0o644);
  const c=start(f);t.after(()=>c.close());await boot(c);c.send({id:2,method:'tools/list'});const r=await c.receive();assert.equal(r.result.tools.length,1);assert.equal(count(f),1);
 }
});
test('runtime logs do not invalidate or get included in fingerprint',async()=>{
 const f=fixture();await seed(f);const before=packageFingerprint(f.options.cwd,f.options.args,f.options.env,f.options.packageRoot);
 mkdirSync(join(f.options.env.SERENA_HOME,'logs'));writeFileSync(join(f.options.env.SERENA_HOME,'logs','fixture.txt'),'not configuration');
 assert.equal(packageFingerprint(f.options.cwd,f.options.args,f.options.env,f.options.packageRoot),before);assert.ok(safeCacheRead(f.options.cacheFile,before));
});
test('fixed no-project catalog reuses across cwd; relative paths remain scoped',()=>{
 const f=fixture(),o=f.options;const e={...o.env,PATH:'/usr/bin:/bin'};delete e.PYTHONPATH;
 const a=packageFingerprint('/tmp/A',o.args,e,o.packageRoot),b=packageFingerprint('/tmp/B',o.args,e,o.packageRoot);assert.equal(a,b);
 const relative={...e,PYTHONPATH:'.'};assert.notEqual(packageFingerprint('/tmp/A',o.args,relative,o.packageRoot),packageFingerprint('/tmp/B',o.args,relative,o.packageRoot));
});
test('initialize error remains visible on passthrough; cached backend exit closes transport',async t=>{
 const f=fixture();await seed(f);writeFileSync(f.options.cacheFile,'{}');const opts={...f.options,env:{...f.options.env,FAKE_FAIL:'init'}};
 const c=start(f,opts);t.after(()=>c.close());const result=await boot(c);assert.equal(result.error.message,'fixture initialize failed');
 const g=fixture();await seed(g);const d=start(g);await boot(d);d.send({id:2,method:'die'});await once(d.p,'exit');assert.equal(d.p.exitCode,7);
});
test('producer failure is bounded and owned process closes',async()=>{
 const f=fixture();const started=Date.now();await assert.rejects(prepare({...f.options,env:{...f.options.env,FAKE_FAIL:'init'},timeoutMs:500}),/discovery failed/);assert.ok(Date.now()-started<2000);
});
test('production cache miss replaces proxy before consuming stdin',async t=>{
 const f=fixture();const c=start(f,{execFallback:true,env:{...f.options.env,HOME:f.dir}});t.after(()=>c.close());await boot(c);
 c.send({id:2,method:'get'});const r=await c.receive();assert.equal(r.result.pid,c.p.pid);assert.ok(noChildren(c.p.pid));
});
test('native Codex arg0 directory changes do not invalidate the catalog',()=>{
 const f=fixture(),o=f.options;const e={...o.env,PATH:`${homedir()}/.codex/tmp/arg0/codex-arg0-A:/usr/bin:/bin`};delete e.PYTHONPATH;
 const b={...e,PATH:`${homedir()}/.codex/tmp/arg0/codex-arg0-B:/usr/bin:/bin`};
 assert.equal(packageFingerprint(o.cwd,o.args,e,o.packageRoot),packageFingerprint(o.cwd,o.args,b,o.packageRoot));
 assert.notEqual(packageFingerprint(o.cwd,o.args,e,o.packageRoot),packageFingerprint(o.cwd,o.args,{...b,PATH:b.PATH+':/opt/bin'},o.packageRoot));
});
