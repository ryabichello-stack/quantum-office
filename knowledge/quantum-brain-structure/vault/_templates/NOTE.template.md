---
# Copy to vault/<area>/<slug>.md and replace placeholders.
# Required keys validated by scripts/validate_vault_frontmatter.py in office repo.
tenant_id: quantum-labs
visibility: company          # public only with publication.manual_approve: true
classification:
  level: internal            # public | internal | confidential | secret
  contains_personal_data: false
channels: [office-assistant] # assistant-safe for voice-office / text-secretary
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: vault#REPLACE_SLUG
shard: REPLACE_SLUG
---

# REPLACE_TITLE

Stub only — replace this body with real knowledge. Do not commit secrets, tokens, or PII dumps.
