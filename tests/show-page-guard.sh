#!/usr/bin/env bash
# Exercise only the production guard; never stage, deploy, or contact a server.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
eval "$(sed -n '/^show_page_guard() {/,/^}/p' "$repo/bin/show-page")"
fixture="$(mktemp -d "${TMPDIR:-/tmp}/show-page-guard.XXXXXX")"
trap 'rm -f "$fixture/index.html"; rmdir "$fixture"' EXIT
check() {
  local name="$1" expected="$2" content="$3" found
  printf '%s\n' "$content" > "$fixture/index.html"
  found="$(show_page_guard "$fixture")"
  if [[ "$expected" == pass && -n "$found" ]] || [[ "$expected" == refuse && -z "$found" ]]; then
    printf 'FAIL: %s (expected %s)\n' "$name" "$expected"
    exit 1
  fi
  printf 'PASS: %s\n' "$name"
}
check 'SVG paths pass' pass '<svg><path d="c0 .55.47.98.97 1.21"/><path d="-9.591-3.676.6.6 0"/></svg>'
check 'documentation IPv4 refused' refuse '<p>203.0.113.7</p>'
check 'fake key refused' refuse '<p>sk-abcdefghijklmnopqrst</p>'
check 'local addresses allowed' pass '<p>127.0.0.1 0.0.0.0</p>'
check 'longer dotted runs pass' pass '<p>.198.51.100.4 198.51.100.4. 1198.51.100.4 198.51.100.4444</p>'
check 'octets above 255 pass' pass '<p>256.51.100.4 198.999.100.4 198.51.999.4 198.51.100.999</p>'
check 'real IP beside SVG refused' refuse '<svg d="c0 .55.47.98.97 1.21"/> 198.51.100.4'
check 'email still refused' refuse '<p>fixture@example.test</p>'
printf '8 of 8 checks passed\n'
