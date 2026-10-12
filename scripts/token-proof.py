#!/usr/bin/env python3
"""token-proof ACCOUNT — native-agents step 4's throwaway proof: does a `claude setup-token` token run a full SISO session
from one shared config folder?

A0 (2 Oct): prove it on one throwaway session (Opus 1M, /usage, the usage API under a setup-token) before any seat moves.
Shaan stores each token once, never echoed:  security add-generic-password -U -s siso-claude-oauth -a ACCOUNT -w
This reads it into memory (never printed or logged), runs claude with CLAUDE_CONFIG_DIR set to a fresh scratch folder (so
nothing comes from an existing login) and CLAUDE_CODE_OAUTH_TOKEN set, and checks:

  auth     `claude auth status` reports logged in
  opus-1m  `claude -p --model claude-opus-5-5[1m]` answers on claude-opus-5-5 with a 1,000,000-token context window
  account  the token is the account it is stored as: its weekly reset time (anthropic-ratelimit-unified-7d-reset, per
           account) equals that login's and differs from the other login's (each login read with its own credentials)
  usage    the 5-hour and weekly utilisation headers come back on the token's calls (what a statusline can show)
Informational, not part of GREEN: /api/oauth/profile and /api/oauth/usage under the token. setup-token tokens are
user:inference only (the claude binary says so), so expect these to be refused; /usage and claude-credits keep reading
each login's own credentials.

  token-proof.py ACCOUNT   ACCOUNT is the Keychain account name: fuzeheritage (claude-siso) | lordsisodia (claude-siso-3)
Exit 0 all green, 1 a check failed (each is printed PASS/FAIL), 3 no token stored for ACCOUNT, 4 the token is another
account's (the browser was signed in to the wrong claude.ai account; the line `wrong-account: <login>` names it).
Costs one short Opus call and three 5-token Haiku calls.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, urllib.error, urllib.request

SERVICE = os.environ.get("TOKEN_PROOF_SERVICE") or "siso-claude-oauth"
API = os.environ.get("TOKEN_PROOF_API") or "https://api.anthropic.com"
CLAUDE = os.environ.get("TOKEN_PROOF_CLAUDE") or os.path.expanduser("~/.local/bin/claude")
LOGIN = {"fuzeheritage": "~/.claude-siso", "lordsisodia": "~/.config/claude-siso-3"}  # never plain claude (Fahmy's)


def stored_token(account):
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def login_token(cfg):
    """A login's own OAuth access token (its Keychain item), in memory only; as bin/claude-credits reads it."""
    svc = "Claude Code-credentials-" + hashlib.sha256(os.path.expanduser(cfg).encode()).hexdigest()[:8]
    raw = subprocess.run(["security", "find-generic-password", "-s", svc, "-w"], capture_output=True, text=True).stdout.strip()
    try:
        return json.loads(raw)["claudeAiOauth"]["accessToken"]
    except (ValueError, KeyError, TypeError):
        return None


def limits(tok):
    """The unified rate-limit headers of one 5-token Haiku call with this token."""
    body = json.dumps({"model": "claude-haiku-4-5-20251001", "max_tokens": 5, "messages": [{"role": "user", "content": "ok"}]}).encode()
    req = urllib.request.Request(API + "/v1/messages", data=body, headers={"Authorization": "Bearer " + tok, "anthropic-version": "2023-06-01",
                                 "anthropic-beta": "oauth-2025-04-20", "content-type": "application/json"})
    try:
        h = urllib.request.urlopen(req, timeout=30).headers
    except urllib.error.HTTPError as e:
        h = e.headers
    return {k.lower().replace("anthropic-ratelimit-unified-", ""): v for k, v in h.items() if "ratelimit-unified" in k.lower()}


def api(path, tok):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main(argv):
    wrong = None
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    account = argv[0]
    tok = stored_token(account)
    if not tok:
        print(f"token-proof: no token stored for {account} (service {SERVICE}); Shaan runs `claude setup-token`, then "
              f"`security add-generic-password -U -s {SERVICE} -a {account} -w` and pastes it", file=sys.stderr)
        return 3
    home = tempfile.mkdtemp(prefix=".siso-ephemeral-token-proof.")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_OAUTH"))}
    env.update(CLAUDE_CONFIG_DIR=home, CLAUDE_CODE_OAUTH_TOKEN=tok)
    results = []

    def check(name, ok, detail):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")

    try:
        st = subprocess.run([CLAUDE, "auth", "status"], env=env, capture_output=True, text=True, timeout=60, cwd=home)
        try:
            j = json.loads(st.stdout)
        except ValueError:
            j = {}
        check("auth", bool(j.get("loggedIn")), f"loggedIn={j.get('loggedIn')} method={j.get('authMethod') or j.get('apiProvider') or '?'}")
        r = subprocess.run([CLAUDE, "-p", "--model", "claude-opus-5-5[1m]", "--output-format", "json", "reply ok"],
                           env=env, capture_output=True, text=True, timeout=180, cwd=home, stdin=subprocess.DEVNULL)
        try:
            mu = json.loads(r.stdout).get("modelUsage") or {}
        except ValueError:
            mu = {}
        key = next((k for k in mu if k.startswith("claude-opus-5-5")), None)  # reported as claude-opus-5-5[1m] under a token
        win = (mu.get(key) or {}).get("contextWindow")
        check("opus-1m", key is not None and win == 1_000_000, f"models={list(mu)} contextWindow={win}"
              + ("" if mu else f" stderr={r.stderr.strip()[-160:]!r}"))
        mine = limits(tok)
        check("usage", "5h-utilization" in mine and "7d-utilization" in mine,
              f"5h={mine.get('5h-utilization')} 7d={mine.get('7d-utilization')}")
        own = LOGIN.get(account)
        other = [c for a, c in LOGIN.items() if a != account]
        ref = {c: (lambda t: limits(t) if t else {})(login_token(c)) for c in ([own] if own else []) + other}
        same = own and mine.get("7d-reset") and ref.get(own, {}).get("7d-reset") == mine.get("7d-reset")
        clash = [c for c in other if ref.get(c, {}).get("7d-reset") == mine.get("7d-reset")]
        check("account", bool(same) and not clash, f"weekly reset matches {own}: {bool(same)}; matches another login: {bool(clash)}")
        if clash and not same:
            wrong = clash[0]
        for path in ("/api/oauth/profile", "/api/oauth/usage"):
            try:
                api(path, tok)
                print(f"info {path}: allowed under the token")
            except Exception as e:  # noqa: BLE001 (expected: user:inference scope only)
                print(f"info {path}: {type(e).__name__} {getattr(e, 'code', '')} (setup-token is user:inference only)")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    print("token-proof:", "GREEN" if all(results) else "RED", f"({sum(results)}/{len(results)})")
    if wrong:
        print(f"wrong-account: {next(a for a, c in LOGIN.items() if c == wrong)}")
        return 4
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
