# DELNO — DECISION LOG

Canonical summary is in `00_MASTER_SPEC.md` section 40.

Append decisions that materially affect architecture, scope, monetization, security, integrations, roadmap, UX or operations.

Template:

## DEC-XXX — Title
Date:
Status: Accepted / Superseded / Rejected

### Context
...

### Decision
...

### Consequences
...


## 2026-10-09 — Main site correctness
Fixed six header/footer links to use mainPath without doubled slashes. Lead submit handler retains the form before await, preserves server validation messages, and only shows success after reset. Regression checks reproduce the prior success-path failure and verify success, validation, and network failures. Visual/browser checks remain pending.

## 2026-10-09 — Article indexing and pricing review
Blog index, individual articles and help use their own metadata and canonical URLs; the obsolete `/v3` entry is removed from the sitemap. Proposed replacement tariffs remain unpublished until actual unit costs and customer response are measured. Marketing copy must describe verified product behavior.

## DEC-2026-10-10 — Traffic and sales before product
Date: 2026-10-10
Status: Accepted

### Context
The owner explicitly set the order: attract traffic, validate demand and willingness to pay, sell pilots, and confirm unit economics before building or presenting a real demo or expanding the product.

### Decision
The public site prioritizes search landing pages, useful articles and tools, and lead capture for pilot discussions. Standalone demo sections and demo calls to action are removed. The floating assistant remains available as explicitly requested. No new tariff is published as a settled offer until costs and buyer response are measured. Content must distinguish a request for booking from a confirmed calendar booking.

### Consequences
Measure organic visits, scenario interest, form opens, form starts, qualified leads, pilot sales, and actual delivery costs. Product and demo work follow those signals.
