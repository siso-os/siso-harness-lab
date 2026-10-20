# plugin-marketplaces: slice notes (2026-10-14)

Rows: `../rows/plugin-marketplaces.jsonl` (22 rows). Target was 30+; this run reached 22 rows backed by a fetch, a gh api call, or a read of a redirect target. Tool-call budget (about 40) was the limit.

## Strongest finds
1. **claude-plugins-official**: 315 manifest entries, 37.8k stars, default-registered in Claude Code, auto-update on, partner tier in /external_plugins (row 001).
2. **Dify Marketplace**: the only fetched listing with a partner-verified tier (38 plugins "Verified by a Dify partner") alongside official and community entries (row 011).
3. **Microsoft 365 Copilot Agent Store**: explicit "centralized, curated" store with publisher tiers (Microsoft, trusted partners, customers), 70+ agents at launch (row 018).

## Trust models seen (for the comparison)
- Anthropic official: inclusion at Anthropic's discretion; "Anthropic verified" badge on claude.com/plugins (13 of 24 visible).
- Anthropic community: automated scan plus approval, mirrored read-only (claude-plugins-community). Auto-update off.
- Claude connectors: Verified vs Community labels; verification is "not a security audit" (per doc).
- Dify: partner-verified label; official author tag.
- n8n, Make, Relevance AI, Lindy: no per-template verification; trust is creator name, clone count or rating, or company-level credentials.
- Salesforce AgentExchange: security-review claim on some listings (secondary source only).

## Gaps and unfetched leads
- **Zapier templates**: zapier.com/apps/templates returned 404. No count found.
- **Langflow**: no marketplace or store found; langflow-ai/langflow is an engine repo (155,634 stars, MIT).
- **Flowise marketplace**: mintlify.com URL 308-redirects to mintlify.wiki; not followed. Search says community chatflows and tool templates exist; not counted.
- **AWS Marketplace AI agents and tools**: guessed URL returned 404. The July 2025 AgentCore marketplace category is from search snippets only.
- **Google Cloud Agent Garden / Agent Marketplace**: blog URL guess returned 404. No counts.
- **claudecodemarketplace.com**: DNS failure (ENOTFOUND). Not found.
- **claude-plugins.dev**: search returned nothing about it.
- **claudepluginhub.com**, **VibeIndex** (vibeindex.ai/marketplaces/...), **claudemarket.ai/connectors** (1,625 connectors, per search title): seen in search results only, not fetched, so no rows.
- **Make template count**: page shows 9 cards with no total; the 7,500 figure is from the help page snippet.
- **GPT Store**: no live count; figures are from 2024 OpenAI and a secondary tracker.
- **Gemini Gems**: no public Gems gallery found. Gemini app extensions expansion (Aug 2026) is from a Japanese blog snippet only.
- **OpenAI launch blog**: 403. The Apps SDK docs page now describes Plugins; the exact review and privacy rules are on subpages not read.
- **Salesforce main site**: 403 on the body; only the title was read.
- **Copilot Studio**: pricing from search snippet; admin control claims from a secondary source only.

## Method notes
- Counts from gh api are dated 2026-10-14. Star counts and pushed dates come from the same call.
- Where a page showed a number, I used that. Where I tallied (Dify ~159), the tally is mine.
- Several search-only URLs were left out of rows so every row has a URL I actually opened, read through gh, or followed through a redirect.
- Scope: MCP-only registries and skills-only sites are left out, as the brief requires. The Claude connectors and Gemini CLI rows are kept because they are plugin or app stores with an install UI, not pure MCP indexes.
