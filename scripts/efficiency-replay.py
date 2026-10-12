#!/usr/bin/env python3
"""Replay read/log candidates on recorded tool payloads, without model calls.

No installation, suppression, credentials, private stores or raw payload exports.
Characters are payload measurements, NOT native model tokens or Max quota savings.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

HOME = Path.home()
PRIVATE = ("fahmy", "bykonz", "whatsapp", "personal", "credentials", ".env")
PROJECTS = ("siso-harness-lab", "siso-firstmate", "siso-agent-zero",
            "siso-internal-labs-agent-base")


def safe(value):
    return not any(word in str(value).lower() for word in PRIVATE)


def project(value):
    return safe(value) and any(part in str(value).split("/") for part in PROJECTS)


def text_content(value):
    # Base64 screenshots must never be counted as text tokens.
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(b.get("text", "") for b in value
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def log_replay(text):
    """Replace only long identical error lines; retain position/count and all context.

    Includes a lossless reconstruction check. No numeric normalization: HTTP 404,
    HTTP 500, paths, IDs and stack locations are consequential distinct evidence.
    """
    lines = text.splitlines(keepends=True)
    seen, packed, saved, repeats = {}, [], 0, 0
    for index, line in enumerate(lines):
        reference = seen.get(line)
        marker = f"[repeat of line {reference + 1}]\n" if reference is not None else ""
        if reference is not None and len(marker) < len(line):
            packed.append(reference)
            saved += len(line) - len(marker)
            repeats += 1
        else:
            packed.append(line)
            if re.search(r"\b(error|warn(?:ing)?|fatal|exception)\b", line, re.I):
                seen[line] = index
    restored = []
    for value in packed:
        restored.append(restored[value] if isinstance(value, int) else value)
    return {"before_chars": len(text), "after_chars": len(text) - saved,
            "duplicate_lines": repeats, "roundtrip_pass": "".join(restored) == text}


class Replay:
    def __init__(self):
        self.reads = {}
        self.stats = collections.Counter()
        self.examples = []

    def reset(self):
        self.reads.clear()

    def read(self, key, text):
        self.stats["successful_text_reads"] += 1
        self.stats["read_before_chars"] += len(text)
        digest = hashlib.sha256(text.encode()).hexdigest()
        # Require identical observed bytes and identical range, not mtime alone.
        if self.reads.get(key) == digest:
            notice = "Identical read already in this uncompacted task; explicit reread available."
            self.stats["identical_range_reads"] += 1
            self.stats["read_saved_chars"] += max(0, len(text) - len(notice))
        self.reads[key] = digest

    def log(self, text, source):
        result = log_replay(text)
        self.stats["log_payloads"] += 1
        for key in ("before_chars", "after_chars", "duplicate_lines"):
            self.stats["log_" + key] += result[key]
        if not result["roundtrip_pass"]:
            raise ValueError("lossless replay failed")
        if result["before_chars"] > result["after_chars"]:
            self.examples.append({"source": source, "sha256": hashlib.sha256(text.encode()).hexdigest(), **result})

    def report(self):
        stats = dict(self.stats)
        stats["read_after_chars"] = stats.get("read_before_chars", 0) - stats.get("read_saved_chars", 0)
        return {"stats": stats, "examples": sorted(self.examples,
                key=lambda r: r["before_chars"] - r["after_chars"], reverse=True)[:3]}


def records(path):
    with path.open(errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def on_day(stamp, day):
    try:
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")) if isinstance(stamp, str) else dt.datetime.fromtimestamp(stamp).astimezone()
        return when.tzinfo is not None and when.astimezone().date().isoformat() == day
    except (TypeError, ValueError, OverflowError):
        return False


def claude(root, day):
    if root.resolve() != (HOME / ".config/claude-siso-3/projects").resolve():
        raise ValueError("only separate SISO login accepted; mixed/private stores refused")
    replay = Replay()
    for path in sorted(root.glob("*/*.jsonl")):
        if not safe(path):
            continue
        replay.reset()
        tools, completed = {}, set()
        for row in records(path):
            if row.get("subtype") == "compact_boundary":
                replay.reset()
            if not project(row.get("cwd", "")) or row.get("isSidechain") or not on_day(row.get("timestamp"), day):
                continue
            blocks = (row.get("message") or {}).get("content", [])
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name, inp = block.get("name"), block.get("input") or {}
                    if not safe(json.dumps(inp)):
                        continue
                    tools[block["id"]] = (name, inp)
                    if name != "Read":
                        replay.reset()  # Bash/Serena may mutate; conservative invalidation.
                elif block.get("type") == "tool_result":
                    tid = block.get("tool_use_id")
                    if tid not in tools or tid in completed:
                        continue
                    completed.add(tid)
                    name, inp = tools[tid]
                    text = text_content(block.get("content"))
                    if block.get("is_error"):
                        replay.reset()
                        if name == "Bash" and text:
                            replay.log(text, path.name + ":" + str(tid))
                        continue
                    if not text:
                        continue
                    source = path.name + ":" + str(tid)
                    if name == "Read":
                        key = (inp.get("file_path"), inp.get("offset", 1), inp.get("limit"))
                        replay.read(key, text)
                    elif name == "Bash":
                        replay.log(text, source)
    return replay.report()


def codex(root, day):
    replay, runs = Replay(), 0
    for meta in sorted(root.glob("*.meta.json")):
        row = next(records(meta), {})
        if not project(row.get("dir", "")) or not on_day(row.get("started"), day):
            continue
        path = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        if not path.exists():
            continue
        runs += 1
        for event in records(path):
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") == "command_execution" and safe(item.get("command", "")):
                # Include failed commands: diagnostics are the log candidate's point.
                replay.log(item.get("aggregated_output") or "", path.name + ":" + str(item.get("id")))
    return {"runs": runs, **replay.report()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=dt.datetime.now().astimezone().date().isoformat())
    args = parser.parse_args()
    result = {"day": args.day, "measured_at": dt.datetime.now().astimezone().isoformat(),
              "kind": "offline replay of real recorded task tool payloads",
              "claude": claude(HOME / ".config/claude-siso-3/projects", args.day),
              "codex_run": codex(HOME / ".local/state/codex-run/runs", args.day),
              "limits": ["Character counts are NOT measured model tokens or Max quota.",
                         "No live model replay, task-acceptance improvement or causal daily-share gain proven.",
                         "Read cache reset on any non-Read tool, error, compaction and session boundary.",
                         "No raw payloads exported; unsafe command/path inputs excluded."]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
