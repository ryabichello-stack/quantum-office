#!/usr/bin/env bash
# Import selected office-tool markdown into vault (with frontmatter).
# Allowlist only — no Polyhub/VPN. Skip service READMEs (covered by tools/tool-*.md cards).
set -euo pipefail

DEST_ROOT="${1:-/opt/ava-knowledge/vault/quantum-brain/tools/imported}"
mkdir -p "$DEST_ROOT"

wrap() {
  local src="$1"
  local shard="$2"
  local title="$3"
  local out="$DEST_ROOT/${shard}.md"
  if [ ! -f "$src" ]; then
    echo "skip missing: $src"
    return 0
  fi
  local body
  body="$(python3 - "$src" <<'PY'
import pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
if text.startswith("---"):
    m = re.match(r"^---\s*\n.*?\n---\s*\n?(.*)$", text, flags=re.S)
    text = m.group(1) if m else text
print(text.strip())
PY
)"
  cat >"$out" <<EOF
---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: imported:${src}
shard: ${shard}
---

# ${title}

> Imported from \`${src}\` for Second Brain. Secrets must not be added here.

${body}
EOF
  echo "wrote $out ($(wc -c <"$out") bytes)"
}

# Deep / unique docs only (READMEs live as curated tools/tool-*.md — avoid duplicates)
wrap /opt/ava-outreach/docs/ARCHITECTURE.md outreach-architecture "AVA Outreach — architecture"
wrap /opt/ava-outreach/docs/CURRENT_STATE.md outreach-current-state "Quantum Outreach — текущее состояние"
wrap /root/ava/docs/AVA_QUANTUM_LABS_SYSTEM.md ava-quantum-labs-system "Quantum Labs AVA — паспорт системы"
wrap /root/ava/docs/SYSTEM_OVERVIEW.ru.md ava-system-overview-ru "Quantum Labs AVA — обзор системы"
wrap /root/ava/docs/Google-calendar-tool.md ava-google-calendar-tool "Google calendar tool notes"
wrap /root/ava/AGENTS.md ava-agents-md "AVA AGENTS.md (Quantum)"
wrap /root/ava/docs/TELEPHONY_TOOLS_SURFACE_AUDIT.md ava-telephony-tools-audit "Telephony tools surface audit"

# Remove previously imported README stubs if present
for stale in outreach-readme conference-readme files-readme text-bot-readme \
             calendar-readme quantum-console-readme knowledge-readme; do
  rm -f "$DEST_ROOT/${stale}.md"
done

echo "done → $DEST_ROOT"
find "$DEST_ROOT" -type f -name '*.md' | sort
