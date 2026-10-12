import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { evaluate, cycle, next, receipts } from '../scripts/efficiency-loop.mjs';
import { makeDiagnostic, quality } from '../scripts/output-policies.mjs';
const source = resolve(import.meta.dirname, '..');
const spec = JSON.parse(readFileSync(join(source,'experiments/output-retrieval.json')));
function fixture(t) {
  const root=mkdtempSync(join(tmpdir(),'efficiency-loop-test-'));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const dir of ['scripts','experiments','tests']) mkdirSync(join(root,dir));
  for(const file of ['scripts/efficiency-loop.mjs','scripts/output-policies.mjs','experiments/output-retrieval.json','tests/efficiency-loop.test.mjs']) copyFileSync(join(source,file),join(root,file));
  return root;
}
test('quality takes priority over smaller output, including held-out cases',()=>{
  const r=evaluate(spec);
  assert.equal(r.find(x=>x.policy==='blind_cap').verdict,'rejected_quality');
  const focused=r.find(x=>x.policy==='focused');
  assert.equal(focused.verdict,'fixture_gain');
  assert.ok(focused.cases.filter(c=>c.split==='held_out').every(c=>c.correct));
});
test('malformed fixtures and missing hold-out fail closed',()=>{
  assert.throws(()=>makeDiagnostic({...spec.cases[0],noise_records:10001}));
  assert.throws(()=>evaluate({...spec,cases:spec.cases.filter(c=>c.split==='development')}));
  assert.equal(quality('garbage',{}),false);
});
test('wrong producer exit is a failure despite matching error text',()=>{
  const d=makeDiagnostic(spec.cases[0]);
  assert.equal(quality(JSON.stringify({...d,exit_code:0}),d),false);
});
test('cycles persist across cold pickup and unchanged reruns are no-ops',t=>{
  const root=fixture(t);
  assert.equal(next(root).status,'ready_to_evaluate');
  assert.equal(cycle(root).status,'recorded');
  assert.equal(cycle(root).status,'unchanged');
  assert.equal(receipts(root).length,1);
  assert.equal(next(root).status,'needs_new_evidence');
  assert.equal(receipts(root)[0].promotion,'fixture_only');
});
test('changed source produces a successor without rewriting the old result',t=>{
  const root=fixture(t); cycle(root);
  const first=receipts(root)[0];
  const path=join(root,'experiments/output-retrieval.json');
  const changed=JSON.parse(readFileSync(path)); changed.cases[0].noise_records++;
  writeFileSync(path,JSON.stringify(changed)); cycle(root);
  const all=receipts(root); assert.equal(all.length,2);
  assert.deepEqual(all[0],first); assert.equal(all[1].previous,first.receipt_hash);
});
test('existing writer lock is refused and preserved',t=>{
  const root=fixture(t);mkdirSync(join(root,'.loop.lock'));
  assert.throws(()=>cycle(root),/EEXIST/); assert.ok(existsSync(join(root,'.loop.lock')));
});
test('bad input releases own lock and persists no result',t=>{
  const root=fixture(t);writeFileSync(join(root,'experiments/output-retrieval.json'),'{}');
  assert.throws(()=>cycle(root));assert.equal(existsSync(join(root,'.loop.lock')),false);assert.equal(receipts(root).length,0);
});
test('receipt lineage corruption is rejected',t=>{
  const root=fixture(t);const r=cycle(root);const path=join(root,r.receipt);
  const value=JSON.parse(readFileSync(path));value.previous='wrong';writeFileSync(path,JSON.stringify(value));
  assert.throws(()=>receipts(root),/receipt integrity mismatch/);
});
