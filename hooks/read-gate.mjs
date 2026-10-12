#!/usr/bin/env node
// read-gate: PreToolUse hook on Read. The first time a main chat reads a text file of 32 KB or more whole (no offset or
// limit), the read is turned back once with the file's size and line count and a better route: a window with
// offset/limit, a grep for what is needed, or a scout. Reading the same file again goes through, so it never blocks
// work. Sub-agents, files under 32 KB, windowed reads, images, PDFs and notebooks pass untouched.
// Why: a whole read of a big file is carried on every later call at Opus rates until the next compaction. Idea:
// claude-mem's file-read gate and Continuous-Claude's tldr-read-enforcer; claude-mem's own eval: reads of ~49 KB files
// -32% tokens, ~19 KB files +20%, so only big files are gated. Measure with token-where's Read share before and after.
// Any error lets the read through. READ_GATE=0 turns it off. State: ~/.local/state/read-gate/<session>.json
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export const MIN = 32 * 1024;
const SKIP = /\.(png|jpe?g|gif|webp|svg|pdf|ipynb|ico|bmp|tiff?)$/i;

// Pure: whether to turn this read back, given the file's size and the paths already turned back this session.
export function gate(toolInput, size, asked) {
  const p = toolInput?.file_path;
  if (!p || SKIP.test(p) || toolInput.offset != null || toolInput.limit != null) return false;
  return size >= MIN && !asked.includes(p);
}

export function reason(p, size, lines) {
  const kb = Math.round(size / 1024);
  return `${path.basename(p)} is ${kb} KB, ${lines} lines (~${Math.round(size / 4 / 1000)}k tokens), carried on every later ` +
    `call until compaction. Read only what you need: Grep for the symbol or text, then Read with offset/limit around it; ` +
    `or ask the scout agent one question about it. If you need the whole file, Read it again and it will go through.`;
}

async function main() {
  if (process.env.READ_GATE === "0") return;
  let raw = "";
  for await (const c of process.stdin) raw += c;
  const input = JSON.parse(raw);
  if (input.agent_id || input.tool_name !== "Read" || !input.session_id) return;
  const p = input.tool_input?.file_path;
  const size = statSync(p).size;
  const dir = process.env.READ_GATE_STATE || path.join(homedir(), ".local", "state", "read-gate");
  const file = path.join(dir, `${input.session_id}.json`);
  let asked = [];
  try { asked = JSON.parse(readFileSync(file, "utf8")); } catch {}
  if (!gate(input.tool_input, size, asked)) return;
  const text = readFileSync(p, "utf8");
  if (text.includes("\u0000")) return; // binary
  const lines = text.split("\n").length;
  mkdirSync(dir, { recursive: true });
  writeFileSync(file, JSON.stringify([...asked, p].slice(-200)));
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: reason(p, size, lines) } }));
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(() => {});
