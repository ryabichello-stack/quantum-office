# Skill: office onboarding — deep KB with the owner

When the owner is new or setup is incomplete:

1. Call readiness (`hermes.setup_status` / office connectors). Lead with facts, not guesses.
2. If KB empty / not ok — **co-build** the knowledge base:
   - Ask for the company website URL (do not invent one).
   - Run `office.build_kb_draft` (deep crawl + open-web enrichment). Prefer this over shallow `office.import_website`.
   - After the draft: ask whether they also have **Telegram**, **Instagram**, **VK**, **MAX**, a price list, or a short «who we are / for whom / offer» text. If they send links — call `office.build_kb_draft` again with those URLs (or `web.research` then merge via draft).
   - Call out gaps (hours, pricing, audience, USP, geo) and ask short clarifying questions.
   - Show the draft; wait for owner edits / confirm before treating KB as ready.
3. Propose next connector by `hermes_ops.next_steps` (phone → script → Telegram/MAX → …).
4. Open credential forms via tools — never store raw passwords in memory.
5. When KB + ≥1 connector live: congratulate and offer first conduct task.

Always show a short checklist of remaining steps in the reply.
Speak Russian. Always visible: *what you are doing now* and *what you need from the person*.
