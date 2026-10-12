#!/usr/bin/env node
// Public discovery cache only. Every client retains its own real Serena backend.
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { constants, openSync, closeSync, fstatSync, lstatSync, mkdirSync, readFileSync, writeFileSync, renameSync, readdirSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
const ORIGINAL=join(homedir(),'.local/bin/serena');
const ARGS=['start-mcp-server','--context','codex'];
const CACHE_ROOT=join(homedir(),'.cache/serena-lazy');
const PROTOCOL='2025-06-18';
const DISCOVERY=['tools/list','resources/list','resources/templates/list','prompts/list'];
const CODEX_CAPS={experimental:{'codex/auth-change':{}},elicitation:{form:{},url:{}}};
const MAX=8*1024*1024;
function stable(v){if(Array.isArray(v))return v.map(stable);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));return v;}
const same=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
function cachedDiscoveryParams(params={}){
  if(!params||typeof params!=='object'||Array.isArray(params))return false;
  if(Object.keys(params).some(k=>k!=='_meta'))return false;
  if(params._meta===undefined)return true;
  const meta=params._meta;
  return meta&&typeof meta==='object'&&!Array.isArray(meta)&&Object.keys(meta).every(k=>k==='progressToken')&&
    (meta.progressToken===undefined||typeof meta.progressToken==='string'||typeof meta.progressToken==='number');
}
function spec(o){return {command:o.command||ORIGINAL,args:o.args||ARGS};}
function packageFingerprint(cwd,args,env,packageRoot){
  try{
    const root=packageRoot||join(homedir(),'.local/share/uv/tools/serena-agent/lib/python3.13/site-packages');
    const h=createHash('sha256');
    const file=p=>{const s=lstatSync(p);if(!s.isFile())throw Error('nonregular fingerprint input');h.update(p);h.update(readFileSync(p));};
    const walk=p=>{for(const e of readdirSync(p,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){if(e.name==='__pycache__')continue;const f=join(p,e.name);if(e.isDirectory())walk(f);else if(e.isFile()&&/\.(py|yml|yaml|toml|json)$/.test(e.name))file(f);}};
    walk(join(root,'serena'));
    for(const d of readdirSync(root).sort())if(d.endsWith('.dist-info'))for(const name of ['METADATA','RECORD']){const p=join(root,d,name);try{file(p);}catch(e){if(e.code!=='ENOENT')throw e;}}
    const home=(env.SERENA_HOME||join(homedir(),'.serena')).trim();
    // Logs, memories, indexes and news are NOT configuration; never read them.
    for(const name of ['serena_config.yml','contexts','modes','prompt_templates']){const p=join(home,name);try{if(lstatSync(p).isDirectory())walk(p);else file(p);}catch(e){if(e.code!=='ENOENT')throw e;h.update('missing:'+p);}}
    const binary=realpathSync(ORIGINAL),st=lstatSync(binary);h.update(JSON.stringify([binary,st.size,st.mtimeMs]));
    const relevant=Object.fromEntries(Object.entries(env).filter(([k])=>/^(SERENA_|FAST(MCP|_MCP)|PYTHON|UV_|VIRTUAL_ENV$|PATH$|HOME$|LANG$|LC_)/.test(k)).sort(([a],[b])=>a.localeCompare(b)));
    // Native Codex creates a fresh arg0 shim directory on every launch. It
    // contains Codex/apply_patch, not Serena imports or language tools.
    // Keep the actual backend environment intact; normalize only its identity.
    const arg0=join(env.CODEX_HOME||join(homedir(),'.codex'),'tmp/arg0')+'/';
    if(relevant.PATH)relevant.PATH=relevant.PATH.split(':').filter(p=>!p.startsWith(arg0)).join(':');
    // Fixed arguments never select a project or infer one from cwd. Only
    // relative import/lookup/config paths can make this public catalog vary.
    const paths=[...(env.PATH||'').split(':'),...(env.PYTHONPATH?env.PYTHONPATH.split(':'):[]),
      ...[env.SERENA_HOME,env.PYTHONHOME].filter(Boolean)];
    const cwdSensitive=paths.some(p=>!isAbsolute(p));
    h.update(JSON.stringify(stable({cwd:cwdSensitive?resolve(cwd):null,args,env:relevant})));return h.digest('hex');
  }catch{return null;}
}
function privateParent(file,create=false){const p=dirname(file);if(create)mkdirSync(p,{recursive:true,mode:0o700});const s=lstatSync(p);if(!s.isDirectory()||(s.mode&0o077)||s.uid!==process.getuid()||realpathSync(p)!==resolve(p))throw Error('unsafe cache directory');}
function valid(d,fp){return d?.version===2&&d.fingerprint===fp&&d.initialize?.protocolVersion===PROTOCOL&&typeof d.initialize?.serverInfo?.name==='string'&&d.initialize.capabilities&&DISCOVERY.every(k=>d.discovery?.[k]&&typeof d.discovery[k]==='object')&&Array.isArray(d.discovery['tools/list'].tools);}
function safeCacheRead(file,fp){if(!fp)return null;let fd;try{privateParent(file);fd=openSync(file,constants.O_RDONLY|constants.O_NOFOLLOW);const s=fstatSync(fd);if(!s.isFile()||s.size>MAX||(s.mode&0o077)||s.uid!==process.getuid())return null;const d=JSON.parse(readFileSync(fd,'utf8'));return valid(d,fp)?d:null;}catch{return null;}finally{if(fd!==undefined)closeSync(fd);}}
function writeCache(file,data){privateParent(file,true);const tmp=`${file}.${randomUUID()}.tmp`;const fd=openSync(tmp,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);try{writeFileSync(fd,JSON.stringify(data)+'\n');}finally{closeSync(fd);}renameSync(tmp,file);}
function cacheFile(o,fp){return o.cacheFile||join(CACHE_ROOT,`${fp}.json`);}
function childFor(o,cwd,env){const s=spec(o);return spawn(s.command,s.args,{cwd,env,stdio:['pipe','pipe',o.stderr||'inherit']});}
async function closeChild(child){if(!child.pid||child.exitCode!==null||child.signalCode!==null)return;child.stdin.end();await new Promise(r=>{const timer=setTimeout(()=>child.kill('SIGTERM'),2000);child.once('exit',()=>{clearTimeout(timer);r();});});}
function lines(stream,receive,end){let buf='';stream.setEncoding('utf8');stream.on('data',chunk=>{buf+=chunk;if(buf.length>MAX){end(Error('discovery frame exceeds limit'));stream.pause();return;}let n;while((n=buf.indexOf('\n'))>=0){const l=buf.slice(0,n);buf=buf.slice(n+1);if(l.trim())receive(l);}});stream.once('end',()=>end());stream.once('error',end);}
async function prepare(o={}){
  const cwd=o.cwd||process.cwd(),env=o.env||process.env,child=childFor(o,cwd,env);let seq=0;const pending=new Map();
  const rejectAll=e=>{for(const p of pending.values())p.reject(e);pending.clear();};
  lines(child.stdout,raw=>{let m;try{m=JSON.parse(raw);}catch{return;}if(!m.method&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error('Serena discovery failed')):p.resolve(m.result);}},()=>rejectAll(Error('Serena discovery closed')));
  child.on('error',rejectAll);child.stdin.on('error',()=>{});
  const call=(method,params={})=>new Promise((resolveCall,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error('Serena discovery timeout'));},o.timeoutMs||15000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolveCall(v);},reject:e=>{clearTimeout(timer);reject(e);}});child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');});
  try{
    const initialize=await call('initialize',{protocolVersion:PROTOCOL,capabilities:CODEX_CAPS,clientInfo:{name:'serena-lazy-prepare',version:'2'}});
    child.stdin.write(JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})+'\n');
    const discovery={};for(const method of DISCOVERY)discovery[method]=await call(method);
    const fingerprint=packageFingerprint(cwd,spec(o).args,env,o.packageRoot),data={version:2,fingerprint,initialize,discovery};
    if(!fingerprint||!valid(data,fingerprint))throw Error('Serena discovery cache not valid');
    const file=cacheFile(o,fingerprint);writeCache(file,data);return {file,tools:discovery['tools/list'].tools.length};
  }finally{await closeChild(child);}
}
function run(o={}){
  const input=o.input||process.stdin,output=o.output||process.stdout,cwd=o.cwd||process.cwd(),env=o.env||process.env;
  const fp=packageFingerprint(cwd,spec(o).args,env,o.packageRoot),cache=safeCacheRead(cacheFile(o,fp),fp);
  // Before reading stdin, a miss can replace this process with the original
  // server. Unprepared environments then pay no persistent proxy overhead.
  if(!cache&&o.execFallback&&typeof process.execve==='function'){
    const s=spec(o),python=join(homedir(),'.local/share/uv/tools/serena-agent/bin/python');
    // Node can leave inherited pipes nonblocking. Python's synchronous stdin
    // reader would interpret EAGAIN as EOF; restore original stdio flags.
    const shim='import os,fcntl,sys\nfor fd in (0,1,2):\n try: fcntl.fcntl(fd,fcntl.F_SETFL,fcntl.fcntl(fd,fcntl.F_GETFL)&~os.O_NONBLOCK)\n except OSError: pass\nos.execv(sys.argv[1],sys.argv[1:])';
    process.execve(python,[python,'-c',shim,s.command,...s.args],env);
  }
  let mode='cold',child,init,initialized,pending=[],buffered='',serverBuf='',phase='init',closed=false;
  const inventoryId=`serena-lazy-${randomUUID()}`;
  const send=m=>output.write(JSON.stringify(m)+'\n');
  const write=raw=>{if(!child.stdin.write(raw)){input.pause();child.stdin.once('drain',()=>{if(!closed)input.resume();});}};
  function close(code=0){if(closed)return;closed=true;input.pause();for(const raw of pending)try{const m=JSON.parse(raw);if(m.method&&m.id!==undefined)send({jsonrpc:'2.0',id:m.id,error:{code:-32000,message:'Serena backend disconnected; reconnect required'}});}catch{}pending=[];if(child)closeChild(child).finally(()=>{output.end();o.onExit?.(code);});else{output.end();o.onExit?.(code);}}
  function ready(){mode='direct';for(const raw of pending)write(raw+'\n');pending=[];input.resume();}
  function launch(lazy){
    child=childFor(o,cwd,env);child.stdin.on('error',()=>close(1));child.on('error',()=>close(1));child.once('exit',code=>close(code||0));
    if(!lazy){mode='direct';child.stdout.pipe(output,{end:false});return;}
    mode='warming';write(JSON.stringify(init)+'\n');child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>{
      if(mode==='direct'){if(!output.write(chunk)){child.stdout.pause();output.once('drain',()=>child.stdout.resume());}return;}
      serverBuf+=chunk;if(serverBuf.length>MAX){close(1);return;}let n;
      while((n=serverBuf.indexOf('\n'))>=0){const raw=serverBuf.slice(0,n);serverBuf=serverBuf.slice(n+1);let m;try{m=JSON.parse(raw);}catch{close(1);return;}
        if(!m.method&&phase==='init'&&m.id===init.id){
          if(m.error||!same(m.result,cache.initialize)){console.error('serena-lazy: backend initialization differs from cached discovery');close(1);return;}
          phase='inventory';if(initialized)write(JSON.stringify(initialized)+'\n');
          write(JSON.stringify({jsonrpc:'2.0',id:inventoryId,method:'tools/list',params:{}})+'\n');
        }else if(!m.method&&phase==='inventory'&&m.id===inventoryId){
          if(m.error||!same(m.result,cache.discovery['tools/list'])){console.error('serena-lazy: backend tool inventory differs from cached discovery');close(1);return;}
          ready();if(serverBuf)output.write(serverBuf);serverBuf='';return;
        }else output.write(raw+'\n');
      }
    });
  }
  function receive(raw){
    let m;try{m=JSON.parse(raw);}catch{launch(false);write(raw+'\n');return;}
    if(mode==='cold'&&m.method==='initialize'){
      const p=m.params,known=cache&&m.id!==undefined&&p?.protocolVersion===PROTOCOL&&(same(p.capabilities||{},{})||same(p.capabilities,CODEX_CAPS))&&Object.keys(p).every(k=>['protocolVersion','capabilities','clientInfo'].includes(k));
      if(known){init=m;mode='cached';send({jsonrpc:'2.0',id:m.id,result:cache.initialize});return;}
      launch(false);write(raw+'\n');return;
    }
    if(mode==='cached'){
      if(m.method==='notifications/initialized'){initialized=m;return;}
      if(initialized&&DISCOVERY.includes(m.method)&&m.id!==undefined&&cachedDiscoveryParams(m.params)){send({jsonrpc:'2.0',id:m.id,result:cache.discovery[m.method]});return;}
      pending.push(raw);launch(true);return;
    }
    if(mode==='warming'){
      if(!m.method)write(raw+'\n');else pending.push(raw);
      if(pending.reduce((n,r)=>n+r.length,0)>65536)input.pause();return;
    }
    if(mode==='cold'){launch(false);write(raw+'\n');}else write(raw+'\n');
  }
  input.setEncoding('utf8');input.on('data',chunk=>{
    if(closed)return;if(mode==='direct'){write(chunk);return;}buffered+=chunk;if(buffered.length>MAX){close(1);return;}
    let n;while((n=buffered.indexOf('\n'))>=0){const raw=buffered.slice(0,n);buffered=buffered.slice(n+1);if(raw.trim())receive(raw);if(mode==='direct'){if(buffered)write(buffered);buffered='';return;}}
  });
  input.once('end',()=>close());input.once('error',()=>close(1));return {cached:!!cache,close};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  if(process.argv.includes('--prepare'))prepare().then(r=>console.error(JSON.stringify(r))).catch(()=>{console.error('Serena discovery preparation failed; original backend remains the fallback.');process.exitCode=1;});
  else{
    const handle=run({execFallback:true,onExit:code=>{process.exitCode=code;}});for(const sig of ['SIGTERM','SIGINT'])process.once(sig,()=>handle.close());
  }
}
export {prepare,run,packageFingerprint,safeCacheRead,CODEX_CAPS};
