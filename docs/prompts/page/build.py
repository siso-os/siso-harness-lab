#!/usr/bin/env python3
"""Builds the cost-orchestrator V1->V2 review page: data.json for siso-shell U7, then compose -> page.html."""
import html, json, pathlib, subprocess

HERE = pathlib.Path(__file__).resolve().parent
PROMPTS = HERE.parent
SHELL = pathlib.Path.home() / 'SISO_Workspace/Great_Library_of_SISO/banks/siso-shell'
v2 = (PROMPTS / 'cost-orchestrator.v2.md').read_text()

CHANGES = [
    ('"Jev decides in about 81 ms", with <code>TYPESAFE_API_KEY</code>',
     'Jev is a second reader for three moments only: route, progress and complete. Key from <code>~/.config/siso/.env</code>',
     '3 live calls: 940, 494 and 506 ms at $0.000018 each'),
    ('"Cut spend 60–80%", "read the invoice line by line"',
     'No invoice exists. Measure uncached input, output, context per request and weekly-window %. No dollars, and no saving unless it was measured',
     'Codex rollouts carry <code>used_percent</code> over a 10080-minute window'),
    ('Levers: route SMALL/MEDIUM/HIGH to the right model',
     'Levers in order: context per request, then effort, then turns, then model',
     '8 Sep: one owner sent 67% of input at 375k per request'),
    ('Luna at low, medium or high per task',
     'Luna medium by default, set on every spawn with <code>-c model_reasoning_effort=medium</code>. High only on evidence or for Oracle streaming. Never xhigh',
     'Today 8 of 8 lanes ran xhigh (inherited from <code>luna-max</code>); the medium override was verified in the rollout'),
    ('One Jev call: complexity, confidence, with 0.70 / 0.85 cutoffs',
     'Rules and the diff decide first (risky paths come from <code>git diff</code>). Jev only breaks ties; if it says uncertain, take the lower lane',
     'Live <code>route</code> test: 0.75 vs 0.5, yet it returned uncertain with no pick'),
    ('A "hard budget layer the model can never override"',
     'The caps stay, but V2 says plainly that no code enforces them yet. The brain counts cycles and stops at a cap',
     'No cap code found in <code>bin/</code>; a prompt cannot be a hard limit'),
    ('Nightly: rewrite the thresholds and ship them',
     'Weekly, at the window reset: the 3 costliest tasks, each change backed by a regression case, landed through the agent-stack owner',
     'The Jev skill itself says its thresholds are not calibrated'),
    ('A cost report compared with a "single-model baseline"',
     'The cost table uses real readers: <code>usage-window.mjs</code> for Codex and the new <code>claude-usage.mjs</code> for Opus. Every number is labelled measured or estimated',
     'claude-usage: 56 raw usage lines, 23 real responses (a naive sum over-counts about 2.4x)'),
]

rows = ''.join(f'<tr><td>{a}</td><td>{b}</td><td class="dim">{c}</td></tr>' for a, b, c in CHANGES)
ch_changes = f'<div style="overflow-x:auto"><table><thead><tr><th>V1 said</th><th>V2 does</th><th>Receipt</th></tr></thead><tbody>{rows}</tbody></table></div>'
ch_prompt = f'<p>File: <code>siso-harness-lab/docs/prompts/cost-orchestrator.v2.md</code> ({len(v2.split())} words). V1 is kept beside it as <code>cost-orchestrator.v1.md</code>.</p><pre style="white-space:pre-wrap">{html.escape(v2)}</pre>'
ch_left = ('<ul>'
           '<li><strong>Kill switch in code.</strong> Nothing stops a lane at its cap yet. V2 has the brain count and stop at the cap, and says so in the report.</li>'
           '<li><strong>DeepSeek token numbers.</strong> Neither reader covers omp yet; V2 says to write "not measured".</li>'
           '<li><strong>Lanes running now</strong> were not touched. They keep xhigh until they finish; new spawns get medium from the fixed recipe.</li>'
           '</ul>')

data = {
    'meta': {'title': 'Cost orchestrator V2', 'description': 'V1 to V2 of the cost-orchestrator prompt: what changed, why, with receipts.',
             'stream': 'research', 'crumb': [{'label': 'Agent stack'}, {'label': 'prompts'}, {'label': 'cost-orchestrator v2'}],
             'actions': [], 'source': 'siso-harness-lab/docs/prompts · measured 28 Sep 2026'},
    'heading': {'breadcrumb': [{'label': 'siso-harness-lab'}, {'label': 'docs/prompts'}, {'label': 'cost-orchestrator.v2.md'}],
                'kicker': 'prompt <span class="sep">·</span> V1 → V2',
                'title': 'Cost orchestrator, V2',
                'subtitle': 'Same idea as V1, rebuilt on what your stack actually measures. The biggest lever is context and effort, not model choice.',
                'badges': [{'label': 'prompt · agent stack', 'tone': 'research', 'dot': True}],
                'status': {'kicker': 'State', 'value': 'Written and checked', 'note': 'Every command and path in V2 exists on this Mac; the Jev modes and effort override were run live.',
                           'facts': [{'k': 'file', 'v': '<code>docs/prompts/cost-orchestrator.v2.md</code>'},
                                     {'k': 'new tool', 'v': '<code>scripts/claude-usage.mjs</code>'},
                                     {'k': 'recipe fix', 'v': 'herdr spawn line now passes medium'}]},
                'metrics': [{'value': '8 / 8', 'label': 'Luna lanes today at xhigh', 'tone': 'research', 'href': '#changes'},
                            {'value': '24k', 'label': 'tokens to boot a lane for a one-word answer', 'tone': 'research', 'href': '#changes'},
                            {'value': '0.5–0.9 s', 'label': 'real Jev latency, not 81 ms', 'tone': 'research', 'href': '#changes'}],
                'jump': [{'label': 'What changed', 'href': '#changes'}, {'label': 'V2 prompt', 'href': '#prompt'}, {'label': 'Not solved yet', 'href': '#left'}]},
    'sections': {'abstract': {'n': '00', 'title': 'In one line', 'sub': ''},
                 'evidence': {'n': '04', 'title': 'Evidence', 'sub': 'what was run'},
                 'related': {'n': '05', 'title': 'Related'}, 'agent': {'n': '06', 'title': 'Agent entry'}},
    'abstract': {'lede': 'V1 was a good skeleton aimed at the wrong lever. V2 keeps its structure and its final check, fixes four claims that were wrong for your setup, and goes after where the tokens actually go: context size and reasoning effort.',
                 'callout': '<strong>Biggest live win:</strong> every Luna lane spawned today ran at xhigh because the spawn recipe used <code>luna-max</code>. The recipe now passes <code>-c model_reasoning_effort=medium</code>, which matches your "medium everywhere except Oracle streaming" rule.',
                 'facts': [{'k': 'kept from V1', 'v': 'deterministic checks first, compact evidence, max 3 cycles per lane, max 1 Sol escalation, WHERE DID I OVERSPEND?'},
                           {'k': 'length', 'v': f'V1 838 words, V2 {len(v2.split())} words (the extra is real commands)'}]},
    'contents': {'from': 'chapters'},
    'chapters': [{'id': 'changes', 'n': '01', 'title': 'What changed, and the receipt for each', 'html': ch_changes},
                 {'id': 'prompt', 'n': '02', 'title': 'The V2 prompt', 'html': ch_prompt},
                 {'id': 'left', 'n': '03', 'title': 'Not solved yet', 'html': ch_left}],
    'evidence': {'facts': [
        {'claim': 'Jev latency 940 / 494 / 506 ms, $0.000018 per call', 'receipt': '<code>jev.py verify</code> ×3', 'at': '28 Sep'},
        {'claim': '8 of 8 Luna rollouts from 28 Sep have turn_context effort xhigh; max context 244,762 of 258,400', 'receipt': 'rollout scan of ~/.codex/sessions/2026/09/28', 'at': '28 Sep'},
        {'claim': '<code>-c model_reasoning_effort=medium</code> overrides luna-max; <code>gpt-6-sol</code> answers at high', 'receipt': 'two <code>codex exec</code> calls, turn_context read back: luna medium, sol high; 24,087 and 24,266 tokens', 'at': '28 Sep'},
        {'claim': 'claude-usage.mjs dedupes by message id: 56 usage lines → 23 responses', 'receipt': 'independent python count; bad input exits 2', 'at': '28 Sep'},
        {'claim': 'Every command and path named in V2 exists', 'receipt': '<code>command -v</code> and <code>test -e</code> on each; <code>harness.py route/progress --dry-run</code> exit 0', 'at': '28 Sep'}],
        'proposals': [{'claim': 'A kill-switch wrapper that stops a herdr lane at its cap', 'why': 'not built; needs your yes'}],
        'limits': [{'claim': 'No saving is claimed. V2 has not been run on a real task yet.'}],
        'version': {'label': 'working tree', 'href': '#', 'at': '28 Sep 2026'}},
    'related': [],
}
(HERE / 'data.json').write_text(json.dumps(data, indent=1))
subprocess.run([str(SHELL / 'bin/compose'), 'U7', str(HERE / 'data.json'), '--base', 'https://siso-shell.pages.dev', '--out', str(HERE / 'page.html')], check=True)
print(HERE / 'page.html')
