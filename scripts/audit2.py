#!/usr/bin/env python3
"""Second pass: context size per turn, hook bytes, search split, user-channel mix, BLOCKED re-dispatch, refined corrections/waits."""
import json, os, glob, re, sys, collections, statistics
from datetime import datetime, timezone
HOME=os.path.expanduser("~"); PROJ=os.path.join(HOME,".claude","projects")
W0=datetime(2026,8,20,tzinfo=timezone.utc); W1=datetime(2026,9,4,tzinfo=timezone.utc)
def ts(s):
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except: return None
def blocks(m):
    c=(m or {}).get("content")
    if isinstance(c,str): return [{"type":"text","text":c}]
    return c if isinstance(c,list) else []
def pn(p):
    d=os.path.basename(os.path.dirname(p)); return d.replace("-Users-shaansisodia-","").replace("-Users-shaansisodia","home") or "home"

LEAD=re.compile(r'(?:^|&&|;|\|\||\n)\s*(?:cd [^&;|]*&&\s*)?(rg|grep|egrep|find|ag)\b')
PIPE=re.compile(r'\|\s*(grep|egrep|rg)\b')
GITGREP=re.compile(r'\bgit\s+(grep|log|diff|show|status|ls-files)\b')
CORR=re.compile(r"(^|\W)(no,|no\.|no\s+(?:i|that|it|we|you|this)|nope|don'?t|do not|stop\b|why did you|why are you|why do you|why have you|i said|i told you|i asked|wrong|fuck|wtf|you didn'?t|you did not|not what i|that'?s not|isn'?t what|i never|didn'?t ask|useless|wasting|waste\b|what the|seriously|ffs|stupid|are you kidding|still not|not working|read the|ignore|listen|again\b|bro\b|bruh)", re.I)
HUMANISH=re.compile(r"^(Another Claude session|<teammate-message|<cross-session|\[from:|<task-notification|<command-name|<local-command|<system-reminder|Resume as|This session is being continued)")
SLASH=re.compile(r"^/\w+")

files=[f for f in glob.glob(os.path.join(PROJ,"*","*.jsonl")) if os.path.getmtime(f)>=W0.timestamp()]
ctx=[]  # (model, context_tokens, output_tokens, sid)
hookbytes=collections.Counter(); hookfires=collections.Counter()
search=collections.Counter(); search_ex=collections.defaultdict(list)
chan=collections.Counter()
corr=[]; corr_sess=collections.Counter()
waits=[]
agent_calls={}  # id -> (sid, ts, desc, prompt_norm)
agent_res={}
blocked_redispatch=[]
sess_ctx=collections.defaultdict(list)
sess_proj={}
sess_human=collections.Counter()
mid_seen=set()
for f in files:
    sid=os.path.basename(f)[:-6]; proj=pn(f); sess_proj[sid]=proj
    events=[]; in_win=False
    with open(f,errors="replace") as fh:
        for line in fh:
            if len(line)<20: continue
            try:o=json.loads(line)
            except: continue
            t=o.get("type"); tm=ts(o.get("timestamp") or "")
            if tm and W0<=tm<W1: in_win=True
            if t=="attachment":
                a=o.get("attachment") or {}
                if a.get("type") in ("hook_success","hook_additional_context"):
                    hn=a.get("hookName") or "ctx"
                    s=a.get("stdout") or ""
                    if isinstance(a.get("content"),list): s=s or " ".join(map(str,a["content"]))
                    hookbytes[hn]+=len(s); hookfires[hn]+=1
                continue
            if t=="assistant":
                m=o.get("message") or {}; mid=m.get("id") or o.get("uuid"); model=m.get("model") or "?"
                if mid not in mid_seen:
                    mid_seen.add(mid); u=m.get("usage") or {}
                    c=(u.get("input_tokens") or 0)+(u.get("cache_creation_input_tokens") or 0)+(u.get("cache_read_input_tokens") or 0)
                    if c>0:
                        ctx.append((model,c,u.get("output_tokens") or 0,sid)); sess_ctx[sid].append(c)
                for b in blocks(m):
                    if b.get("type")=="tool_use":
                        name=b.get("name"); inp=b.get("input") or {}
                        events.append((tm,"tool",name))
                        if name=="Bash":
                            cmd=inp.get("command") or ""
                            if GITGREP.search(cmd) and not LEAD.search(cmd): search["git-native"]+=1
                            elif LEAD.search(cmd):
                                search["lead-search"]+=1
                                if len(search_ex["lead"])<10: search_ex["lead"].append((proj,cmd[:150].replace("\n"," ")))
                            elif PIPE.search(cmd): search["pipe-filter"]+=1
                            else: search["other-bash"]+=1
                        if name in("Agent","Task"):
                            agent_calls[b.get("id")]=(sid,o.get("timestamp"),inp.get("description"),re.sub(r"\s+"," ",(inp.get("prompt") or "").lower())[:400])
                    elif b.get("type")=="text" and (b.get("text") or "").strip():
                        events.append((tm,"text",len(b["text"])))
                continue
            if t=="user":
                m=o.get("message") or {}; bl=blocks(m)
                if any(b.get("type")=="tool_result" for b in bl):
                    for b in bl:
                        if b.get("type")=="tool_result" and b.get("tool_use_id") in agent_calls:
                            c=b.get("content"); txt=c if isinstance(c,str) else " ".join(x.get("text","") for x in (c or []) if isinstance(x,dict))
                            agent_res[b["tool_use_id"]]=txt[:200]
                    continue
                txt=" ".join(b.get("text","") for b in bl if b.get("type")=="text").strip()
                if not txt: continue
                if txt.startswith("<task-notification>"):
                    chan["task-notification"]+=1
                    tid=re.search(r"<tool-use-id>(.*?)</tool-use-id>",txt); sm=re.search(r"<summary>(.*?)</summary>",txt,re.S)
                    if tid and tid.group(1) in agent_calls: agent_res[tid.group(1)]=(sm.group(1) if sm else "")[:200]
                    continue
                if o.get("isCompactSummary") or txt.startswith("This session is being continued"): chan["compact-resume"]+=1; continue
                if o.get("isMeta"): chan["meta"]+=1; continue
                if txt.startswith("<command-name>") or SLASH.match(txt): chan["slash-command"]+=1; continue
                if txt.startswith("<local-command"): chan["local-command"]+=1; continue
                if txt.startswith("[from:") or "<teammate-message" in txt[:80] or txt.startswith("Another Claude session"): chan["relay/teammate"]+=1; continue
                if txt.startswith("<cross-session") or "[Cross-session" in txt[:40]: chan["cross-session"]+=1; continue
                if txt.startswith("Resume as") or len(txt)>2500: chan["long-brief(>2.5k or Resume as)"]+=1; continue
                chan["human-ish"]+=1; sess_human[sid]+=1
                events.append((tm,"user",re.sub(r"\s+"," ",txt)[:200]))
                if CORR.search(txt[:300]):
                    corr.append((o.get("timestamp","")[:10],proj,re.sub(r"\s+"," ",txt)[:200],sid)); corr_sess[sid]+=1
    if not in_win: continue
    ev=sorted([e for e in events if e[0]],key=lambda e:e[0])
    for i,e in enumerate(ev):
        if e[1]!="user": continue
        tools=collections.Counter(); ft=None
        for e2 in ev[i+1:]:
            if e2[1]=="user": break
            if e2[1]=="tool": tools[e2[2]]+=1
            if e2[1]=="text": ft=e2[0]; break
        if ft: waits.append(((ft-e[0]).total_seconds(),proj,sid,e[0].isoformat()[:16],e[2][:100],dict(tools.most_common(4)),sum(tools.values())))

# blocked -> redispatch within 180s with same normalized prompt
by=collections.defaultdict(list)
for aid,(sid,t,d,p) in agent_calls.items(): by[sid].append((t,aid,d,p))
blocked_total=0; redis_after_block=0; redis_examples=[]
for sid,L in by.items():
    L.sort()
    for i,(t,aid,d,p) in enumerate(L):
        r=agent_res.get(aid,"")
        if r.startswith("BLOCKED") or "BLOCKED" in r[:40]:
            blocked_total+=1
            for t2,aid2,d2,p2 in L[i+1:]:
                dt=(ts(t2)-ts(t)).total_seconds()
                if dt>600: break
                if p2[:300]==p[:300]:
                    redis_after_block+=1
                    if len(redis_examples)<6: redis_examples.append((sess_proj[sid],d,round(dt),r[:110]))
                    break
blocked_kinds=collections.Counter()
for aid,r in agent_res.items():
    if "BLOCKED" in r[:40]:
        blocked_kinds[re.sub(r"[^a-z ]","",r[:60].lower())[:50]]+=1

def q(xs,p): xs=sorted(xs); return xs[min(len(xs)-1,int(p*len(xs)))] if xs else 0
by_model=collections.defaultdict(list)
for m,c,o_,s in ctx: by_model[m].append(c)
ctx_all=[c for _,c,_,_ in ctx]
out=dict(
  context=dict(turns=len(ctx), total_context_tokens=sum(ctx_all), median=q(ctx_all,.5), p75=q(ctx_all,.75), p90=q(ctx_all,.9), max=max(ctx_all),
      over_200k=sum(1 for c in ctx_all if c>200000), over_400k=sum(1 for c in ctx_all if c>400000), over_600k=sum(1 for c in ctx_all if c>600000),
      tokens_in_turns_over_200k=sum(c for c in ctx_all if c>200000),
      by_model={m:dict(turns=len(v),median=q(v,.5),p90=q(v,.9),total=sum(v)) for m,v in by_model.items()},
      top_sessions=sorted([(sess_proj[s],s[:8],len(v),q(v,.5),max(v),sum(v)) for s,v in sess_ctx.items()],key=lambda r:-r[5])[:12]),
  hooks=dict(fires=hookfires.most_common(20), bytes=hookbytes.most_common(20), total_bytes=sum(hookbytes.values())),
  search=dict(search), search_examples=search_ex["lead"],
  channel=dict(chan), human_sessions=len(sess_human),
  blocked=dict(total=blocked_total, redispatched_same_prompt=redis_after_block, examples=redis_examples, kinds=blocked_kinds.most_common(8)),
  corrections=dict(total=len(corr), sessions=len(corr_sess), top=[(sess_proj[s],s[:8],n) for s,n in corr_sess.most_common(8)], quotes=corr),
  waits=dict(n=len(waits), median=round(statistics.median([w[0] for w in waits]),1), p90=round(q([w[0] for w in waits],.9),1), over_5min=sum(1 for w in waits if w[0]>300),
      top=sorted(waits,key=lambda w:-w[0])[:12]),
)
json.dump(out,open(sys.argv[1],"w"),indent=1,default=str); print("ok")
