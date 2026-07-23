#!/usr/bin/env bash
# Import selected office-tool markdown into vault (with frontmatter).
# Excludes Polyhub / VPN / Mango deep dumps by allowlist only.
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
  # strip existing frontmatter if any
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

wrap /opt/ava-outreach/README.md outreach-readme "AVA Outreach — README"
wrap /opt/ava-outreach/docs/ARCHITECTURE.md outreach-architecture "AVA Outreach — architecture"
wrap /opt/ava-outreach/docs/CURRENT_STATE.md outreach-current-state "Quantum Outreach — текущее состояние"
wrap /opt/ava-conference/README.md conference-readme "Conference — README"
wrap /opt/ava-files/README.md files-readme "Files — README"
wrap /opt/ava-text-bot/README.md text-bot-readme "Text-bot — README"
wrap /opt/ava-calendar/README.md calendar-readme "Calendar — README"
wrap /opt/quantum-console/README.md quantum-console-readme "Quantum Console — README"
wrap /opt/ava-knowledge/README.md knowledge-readme "Knowledge — README"
wrap /root/ava/docs/AVA_QUANTUM_LABS_SYSTEM.md ava-quantum-labs-system "Quantum Labs AVA — паспорт системы"
wrap /root/ava/docs/SYSTEM_OVERVIEW.ru.md ava-system-overview-ru "Quantum Labs AVA — обзор системы"
wrap /root/ava/docs/Google-calendar-tool.md ava-google-calendar-tool "Google calendar tool notes"
wrap /root/ava/AGENTS.md ava-agents-md "AVA AGENTS.md (Quantum)"
wrap /root/ava/docs/TELEPHONY_TOOLS_SURFACE_AUDIT.md ava-telephony-tools-audit "Telephony tools surface audit"

echo "done → $DEST_ROOT"
find "$DEST_ROOT" -type f -name '*.md' | sort
