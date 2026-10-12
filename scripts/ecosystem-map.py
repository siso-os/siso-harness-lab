#!/usr/bin/env python3
"""ecosystem-map: site map and agent-relevant pages of every major agent-harness vendor, saved under _reference/ecosystem.

  ecosystem-map [--only anthropic,openai,...] [--max 600]

For each source: every URL its sitemap(s) or llms.txt lists goes in <vendor>/<source>.urls.txt (the site map); pages
whose URL matches the source's filter are downloaded as text into <vendor>/pages/. Docs sources (llms.txt) are taken
whole; marketing sitemaps are filtered to engineering/research/blog posts about agents. Repos are shallow clones.
Shaan, 12 Oct: "a proper site map of everything Anthropic, everything Google, everything OpenAI, everything Devin,
everything Codex, anything in this ecosystem".
"""
import argparse, concurrent.futures as cf, html, os, re, subprocess, sys, urllib.request

OUT = os.path.expanduser("~/SISO_Workspace/_reference/ecosystem")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) SISO-research"}
AGENTY = r"agent|context|harness|tool|codex|compact|cach|memory|orchestr|subagent|sub-agent|engineering|research|claude-code|coding|swe|long-running|eval|prompt|token|model|reason"
# vendor -> [(source name, url, kind, url filter or None for all)]
SOURCES = {
    "anthropic": [("www", "https://www.anthropic.com/sitemap.xml", "sitemap", r"/(engineering|research|news)/"),
                  ("claude-com", "https://claude.com/sitemap.xml", "sitemap", r"claude\.com/(blog|code-with-claude|resources/(articles|guides|best-practices))/"),
                  ("support", "https://support.claude.com/sitemap.xml", "sitemap", r"/en/articles/.*(claude-code|usage|limit|plan|agent|max|pro|context|model|cowork)"),
                  ("docs-platform", "https://docs.claude.com/llms.txt", "llms", None),
                  ("docs-code", "https://code.claude.com/docs/llms.txt", "llms", None)],
    "openai": [("platform-docs", "https://platform.openai.com/docs/llms.txt", "llms", None),
               ("developers", "https://developers.openai.com/llms.txt", "llms", None),
               ("codex-docs", "https://developers.openai.com/codex/llms.txt", "llms", None),
               ("agents-sdk", "https://openai.github.io/openai-agents-python/llms.txt", "llms", None),
               ("www", "https://openai.com/sitemap.xml", "sitemap", r"/(index|research)/.*(" + AGENTY + ")")],
    "google": [("gemini-api", "https://ai.google.dev/gemini-api/docs/llms.txt", "llms", None),
               ("adk", "https://google.github.io/adk-docs/llms.txt", "llms", None),
               ("jules", "https://jules.google/docs/llms.txt", "llms", None),
               ("gemini-cli", "https://geminicli.com/llms.txt", "llms", None),
               ("devblog", "https://developers.googleblog.com/sitemap.xml", "sitemap", r"(agent|gemini-cli|jules|adk|context|antigravity|coding)")],
    "cognition": [("devin-docs", "https://docs.devin.ai/llms.txt", "llms", None),
                  ("www", "https://cognition.ai/sitemap.xml", "sitemap", r"/blog/")],
    "cursor": [("docs", "https://cursor.com/docs/sitemap.xml", "sitemap", r"/docs/"),
               ("www", "https://cursor.com/sitemap.xml", "sitemap", r"/blog/")],
    "amp": [("www", "https://ampcode.com/sitemap.xml", "sitemap", r"/(manual|news|notes|how-to|chronicle)")],
    "manus": [("www", "https://manus.im/sitemap.xml", "sitemap", r"/blog/")],
    "factory": [("docs", "https://docs.factory.ai/llms.txt", "llms", None)],
}
REPOS = ["openai/codex", "openai/openai-agents-python", "google-gemini/gemini-cli", "google/adk-python", "badlogic/pi-mono",
         "All-Hands-AI/OpenHands", "SWE-agent/SWE-agent", "Aider-AI/aider", "sst/opencode", "anthropics/claude-code",
         "anthropics/claude-agent-sdk-python"]


BINARY = re.compile(r"\.(exe|zip|tar|gz|tgz|dmg|pkg|deb|rpm|whl|bin|so|dylib|png|jpe?g|gif|webp|mp4|pdf)$|/releases/download/", re.I)


def get(url, timeout=30):
    """Text only, at most 2 MB: a docs index can link release binaries (12 Oct: 215 MB of them saved as pages)."""
    if BINARY.search(url):
        return ""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            if ct and not re.search(r"text|xml|json|markdown", ct):
                return ""
            return r.read(2_000_000).decode("utf-8", "ignore")
    except Exception as e:
        return ""


def sitemap_urls(url, depth=0):
    body = get(url)
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
    if "<sitemapindex" in body and depth < 2:
        out = []
        for child in locs:
            out += sitemap_urls(html.unescape(child), depth + 1)
        return out
    return [html.unescape(u) for u in locs]


def llms_urls(url):
    body = get(url)
    return body, list(dict.fromkeys(re.findall(r"\((https?://[^)\s]+)\)", body)))


def to_text(body):
    if "<html" not in body[:2000].lower():
        return body
    m = re.search(r"<article.*?</article>", body, re.S) or re.search(r"<main.*?</main>", body, re.S)
    s = m.group(0) if m else body
    s = re.sub(r"<(script|style|svg|nav|footer)[^>]*>.*?</\1>", "", s, flags=re.S)
    s = re.sub(r"<h([1-4])[^>]*>", lambda m: "\n\n" + "#" * int(m.group(1)) + " ", s)
    s = re.sub(r"<(p|li|br|div|tr)[^>]*>", "\n", s)
    t = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def fetch(url, dest):
    if os.path.exists(dest):
        return 1
    t = to_text(get(url))
    if len(t) < 200:
        return 0
    open(dest, "w").write(f"Source: {url}\n\n{t}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--max", type=int, default=600, help="pages to download per source")
    ap.add_argument("--no-repos", action="store_true")
    a = ap.parse_args()
    summary = []
    for vendor, sources in SOURCES.items():
        if a.only and vendor not in a.only.split(","):
            continue
        os.makedirs(f"{OUT}/{vendor}/pages", exist_ok=True)
        for name, url, kind, filt in sources:
            if kind == "llms":
                body, urls = llms_urls(url)
                open(f"{OUT}/{vendor}/{name}.llms.txt", "w").write(body)
            else:
                urls = sitemap_urls(url)
            open(f"{OUT}/{vendor}/{name}.urls.txt", "w").write("\n".join(urls) + "\n")
            pick = [u for u in urls if not filt or re.search(filt, u, re.I)][: a.max]
            jobs = {}
            with cf.ThreadPoolExecutor(8) as ex:
                for u in pick:
                    slug = re.sub(r"[^a-z0-9]+", "-", u.split("://", 1)[-1].lower()).strip("-")[:150]
                    jobs[ex.submit(fetch, u, f"{OUT}/{vendor}/pages/{name}--{slug}.md")] = u
                got = sum(f.result() for f in cf.as_completed(jobs))
            line = f"{vendor:10} {name:14} mapped {len(urls):6}  picked {len(pick):4}  saved {got:4}"
            summary.append(line)
            print(line, flush=True)
    if not a.no_repos:
        os.makedirs(f"{OUT}/repos", exist_ok=True)
        for r in REPOS:
            d = f"{OUT}/repos/{r.replace('/', '__')}"
            if not os.path.exists(d):
                p = subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:limit=2m", f"https://github.com/{r}.git", d], capture_output=True, text=True)
                line = f"repo {r}: {'ok' if p.returncode == 0 else 'FAILED ' + p.stderr.strip()[-120:]}"
                summary.append(line)
                print(line, flush=True)
    open(f"{OUT}/MAP.txt", "w").write("\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
