#!/usr/bin/env python3
"""Lossless, on-demand log-block deduplication. No hooks or persistent cache.

Reads stdin; --restore reconstructs it and checks its SHA-256. Returns the
original when references plus their explanation would be larger. Distinct
numbers, paths, causes and stack traces are never normalized or discarded.
"""
import argparse
import hashlib
import re
import sys

PREFIX = "SISO-LOG-PACK/1 "
MARKER = re.compile(r"\[SISO repeat original lines (\d+)-(\d+)\]\n")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack(text):
    # Refuse ambiguous literal markers rather than changing their meaning.
    if PREFIX in text or "[SISO repeat original lines " in text:
        return text
    lines = text.splitlines(keepends=True)
    starts, parts, index = {}, [], 0
    while index < len(lines):
        best = None
        for previous in starts.get(lines[index], []):
            count = 0
            while (index + count < len(lines) and previous + count < index
                   and lines[previous + count] == lines[index + count]):
                count += 1
            # References are standalone lines; an unterminated line stays literal.
            while count and not lines[index + count - 1].endswith("\n"):
                count -= 1
            if not count:
                continue
            marker = f"[SISO repeat original lines {previous + 1}-{previous + count}]\n"
            gain = sum(len(line) for line in lines[index:index + count]) - len(marker)
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, count, marker)
        count = best[1] if best else 1
        parts.append(best[2] if best else lines[index])
        for offset in range(count):
            # Bound search cost even for thousands of repeated empty lines.
            positions = starts.setdefault(lines[index + offset], [])
            positions.append(index + offset)
            del positions[:-16]
        index += count
    header = (f"{PREFIX}sha256={digest(text)} lines={len(lines)}\n"
              "References below reproduce exact original line ranges, including their order.\n")
    packed = header + "".join(parts)
    if len(packed) >= len(text):
        return text
    if restore(packed) != text:
        raise ValueError("lossless verification failed")
    return packed


def restore(text):
    if not text.startswith(PREFIX):
        return text
    header, explanation, payload = text.split("\n", 2)
    match = re.fullmatch(r"SISO-LOG-PACK/1 sha256=([0-9a-f]{64}) lines=(\d+)", header)
    if not match:
        raise ValueError("invalid pack header")
    lines = []
    for line in payload.splitlines(keepends=True):
        marker = MARKER.fullmatch(line)
        if marker:
            start, end = map(int, marker.groups())
            if not 1 <= start <= end <= len(lines):
                raise ValueError("invalid or forward line reference")
            lines.extend(lines[start - 1:end])
        else:
            lines.append(line)
    restored = "".join(lines)
    if len(lines) != int(match[2]) or digest(restored) != match[1]:
        raise ValueError("restored hash or line count differs")
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    try:
        # Preserve CRLF and unterminated lines, including on CLI round trips.
        text = sys.stdin.buffer.read().decode("utf-8")
        output = restore(text) if args.restore else pack(text)
        sys.stdout.buffer.write(output.encode("utf-8"))
    except (ValueError, UnicodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
