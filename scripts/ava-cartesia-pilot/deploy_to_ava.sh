#!/usr/bin/env bash
# Deploy Cartesia TTS pilot into /root/ava WITHOUT changing Mango default path.
# Preserves ai-agent.local.yaml formatting (surgical inserts only).
set -euo pipefail

AVA_ROOT="${AVA_ROOT:-/root/ava}"
PILOT_SRC="${PILOT_SRC:-$(cd "$(dirname "$0")" && pwd)}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$AVA_ROOT/backups/cartesia-pilot-$STAMP"
mkdir -p "$BACKUP" "$AVA_ROOT/config/snippets"

echo "== backup =="
cp -a "$AVA_ROOT/src/config.py" "$BACKUP/"
cp -a "$AVA_ROOT/src/config/__init__.py" "$BACKUP/"
cp -a "$AVA_ROOT/src/pipelines/orchestrator.py" "$BACKUP/"
cp -a "$AVA_ROOT/config/ai-agent.local.yaml" "$BACKUP/"
cp -a /etc/asterisk/extensions.conf "$BACKUP/"
[[ -f "$AVA_ROOT/src/pipelines/cartesia.py" ]] && cp -a "$AVA_ROOT/src/pipelines/cartesia.py" "$BACKUP/" || true
echo "backup at $BACKUP"

echo "== copy adapter =="
cp -a "$PILOT_SRC/cartesia.py" "$AVA_ROOT/src/pipelines/cartesia.py"
cp -a "$PILOT_SRC/local.yaml.snippet" "$AVA_ROOT/config/snippets/cartesia-pilot.yaml"

echo "== patch config.py =="
python3 - <<'PY'
from pathlib import Path
path = Path("/root/ava/src/config.py")
text = path.read_text()
if "class CartesiaProviderConfig" in text:
    print("CartesiaProviderConfig already present")
else:
    idx = text.find("class CambAiProviderConfig")
    if idx < 0:
        raise SystemExit("CambAiProviderConfig not found")
    rest = text[idx:]
    next_class = rest.find("\nclass ", 10)
    if next_class < 0:
        raise SystemExit("cannot find end of CambAiProviderConfig")
    abs_pos = idx + next_class
    block = '''

class CartesiaProviderConfig(BaseModel):
    """Cartesia Sonic TTS + Ink Whisper STT (pipeline pilot).

    API: TTS websocket/bytes, STT /stt/websocket (ink-whisper).
    """
    enabled: bool = Field(default=True)
    api_key: Optional[str] = None
    voice_id: str = Field(default="f786b574-daa5-4673-aa0c-cbe3e8534c02")
    model_id: str = Field(default="sonic-3")
    language: str = Field(default="ru")
    base_url: str = Field(default="https://api.cartesia.ai")
    api_version: str = Field(default="2026-08-14")
    pcm_sample_rate: int = Field(default=16000)
    tts_transport: str = Field(default="websocket")
    stt_model: str = Field(default="ink-whisper")
    stt_max_silence_secs: float = Field(default=0.55)
    stt_min_volume: float = Field(default=0.02)
    farewell_hangup_delay_sec: Optional[float] = None

'''
    path.write_text(text[:abs_pos] + block + text[abs_pos:])
    print("inserted CartesiaProviderConfig")

# Re-export from config package
init = Path("/root/ava/src/config/__init__.py")
it = init.read_text()
if "CartesiaProviderConfig" not in it:
    it = it.replace(
        "CambAiProviderConfig = _parent_config.CambAiProviderConfig\n",
        "CambAiProviderConfig = _parent_config.CambAiProviderConfig\n"
        "CartesiaProviderConfig = _parent_config.CartesiaProviderConfig\n",
        1,
    )
    it = it.replace(
        "'CambAiProviderConfig',\n",
        "'CambAiProviderConfig',\n    'CartesiaProviderConfig',\n",
        1,
    )
    init.write_text(it)
    print("config/__init__.py re-export added")
else:
    print("config/__init__.py already exports Cartesia")
PY

echo "== patch orchestrator.py =="
python3 - <<'PY'
from pathlib import Path
path = Path("/root/ava/src/pipelines/orchestrator.py")
text = path.read_text()

if "from .cartesia import CartesiaTTSAdapter" not in text:
    if "from .cambai import CambAiTTSAdapter" not in text:
        raise SystemExit("cambai import missing")
    text = text.replace(
        "from .cambai import CambAiTTSAdapter\n",
        "from .cambai import CambAiTTSAdapter\nfrom .cartesia import CartesiaTTSAdapter\n",
        1,
    )

if "CartesiaProviderConfig" not in text:
    # Prefer inserting into the existing config import list next to CambAi
    if "CambAiProviderConfig," in text:
        text = text.replace("CambAiProviderConfig,", "CambAiProviderConfig,\n    CartesiaProviderConfig,", 1)
    elif "CambAiProviderConfig" in text:
        text = text.replace("CambAiProviderConfig", "CambAiProviderConfig, CartesiaProviderConfig", 1)
    else:
        raise SystemExit("Cannot locate CambAiProviderConfig import")

if "_cartesia_provider_config" not in text:
    needle = "self._cambai_provider_config: Optional[CambAiProviderConfig] = self._hydrate_cambai_config()\n"
    if needle not in text:
        raise SystemExit("cambai hydrate assign not found")
    text = text.replace(
        needle,
        needle
        + "        self._cartesia_provider_config: Optional[CartesiaProviderConfig] = self._hydrate_cartesia_config()\n",
        1,
    )

if 'register_factory("cartesia_tts"' not in text:
    # Insert after cambai registration block
    start = text.find("if self._cambai_provider_config:")
    if start < 0:
        raise SystemExit("cambai register block missing")
    # next sibling if at same indent
    nxt = text.find("\n        if self._", start + 5)
    if nxt < 0:
        raise SystemExit("cannot find end of cambai register")
    snip = '''
        if self._cartesia_provider_config:
            tts_factory = self._make_cartesia_tts_factory(self._cartesia_provider_config)
            stt_factory = self._make_cartesia_stt_factory(self._cartesia_provider_config)
            self.register_factory("cartesia_tts", tts_factory)
            self.register_factory("cartesia_stt", stt_factory)
            logger.info(
                "Registered Cartesia TTS/STT pipeline adapters",
                tts_factory="cartesia_tts",
                stt_factory="cartesia_stt",
                voice_id=self._cartesia_provider_config.voice_id,
                model_id=self._cartesia_provider_config.model_id,
            )
'''
    text = text[:nxt] + "\n" + snip + text[nxt:]

if "def _hydrate_cartesia_config" not in text or "def _make_cartesia_tts_factory" not in text or "def _make_cartesia_stt_factory" not in text:
    insert_at = text.find("def _hydrate_cambai_config")
    if insert_at < 0:
        # fallback: after cambai factory
        insert_at = text.find("def _make_cambai_tts_factory")
        if insert_at < 0:
            raise SystemExit("no insertion point for cartesia hydrate")
        insert_at = text.find("\n    def ", insert_at + 10)
    factory = '''
    def _make_cartesia_tts_factory(
        self,
        provider_config: CartesiaProviderConfig,
    ) -> ComponentFactory:
        config_payload = provider_config.model_dump()

        def factory(component_key: str, options):
            return CartesiaTTSAdapter(
                component_key,
                self.config,
                CartesiaProviderConfig(**config_payload),
                options,
            )

        return factory

    def _make_cartesia_stt_factory(
        self,
        provider_config: CartesiaProviderConfig,
    ) -> ComponentFactory:
        config_payload = provider_config.model_dump()

        def factory(component_key: str, options):
            return CartesiaSTTAdapter(
                component_key,
                self.config,
                CartesiaProviderConfig(**config_payload),
                options,
            )

        return factory

    def _hydrate_cartesia_config(self):
        import os
        from typing import Optional
        providers = getattr(self.config, "providers", {}) or {}
        raw_config = providers.get("cartesia") or providers.get("cartesia_tts")
        if not raw_config:
            api_key = os.getenv("CARTESIA_API_KEY")
            if api_key:
                return CartesiaProviderConfig(api_key=api_key)
            return None
        if isinstance(raw_config, CartesiaProviderConfig):
            config = raw_config
        elif isinstance(raw_config, dict):
            try:
                fields = set(CartesiaProviderConfig.model_fields.keys())
                filtered = {
                    k: v
                    for k, v in raw_config.items()
                    if k in fields and not (isinstance(v, str) and v == "")
                }
                config = CartesiaProviderConfig(**filtered)
            except Exception as exc:
                logger.warning(
                    "Failed to hydrate Cartesia provider config for pipelines",
                    error=str(exc),
                )
                return None
        else:
            return None
        if not config.api_key:
            env_key = os.getenv("CARTESIA_API_KEY")
            if not env_key:
                logger.warning("Cartesia requires CARTESIA_API_KEY; skipping")
                return None
            config = CartesiaProviderConfig(**{**config.model_dump(), "api_key": env_key})
        return config

'''
    text = text[:insert_at] + factory + text[insert_at:]

path.write_text(text)
print("orchestrator ok")
# syntax check
import ast
ast.parse(path.read_text())
print("orchestrator syntax ok")
PY

echo "== surgical local.yaml insert =="
python3 - <<'PY'
from pathlib import Path
local = Path("/root/ava/config/ai-agent.local.yaml")
text = local.read_text()
if "cartesia_pilot:" in text and "hybrid_cartesia:" in text:
    print("local yaml already contains cartesia pilot keys")
else:
    snippet = Path("/root/ava/config/snippets/cartesia-pilot.yaml").read_text()
    # Append as a second document is invalid for their loader; append keyed blocks
    # under top-level by adding at EOF with unique top-level keys that deep-merge
    # may NOT merge. So we inject into existing sections.

    def inject_under(section: str, block: str, content: str) -> str:
        # Find `section:\n` at beginning of line
        import re
        m = re.search(rf"(?m)^{re.escape(section)}:\s*$", content)
        if not m:
            # create section at EOF
            return content.rstrip() + f"\n\n{section}:\n{block}\n"
        # Insert immediately after the section header line
        pos = m.end()
        return content[:pos] + "\n" + block + content[pos:]

    # Extract blocks from snippet
    import re
    def extract(name: str) -> str:
        # naive: from `name:` until next top-level key in snippet
        sm = re.search(rf"(?ms)^{name}:\n(.*?)(?=^[a-zA-Z_]+:|\Z)", snippet)
        if not sm:
            raise SystemExit(f"snippet missing {name}")
        return sm.group(1)

    ctx = extract("contexts")
    prov = extract("providers")
    pipe = extract("pipelines")

    if "cartesia_pilot:" not in text:
        text = inject_under("contexts", ctx, text)
    if "cartesia_tts:" not in text:
        text = inject_under("providers", prov, text)
    if "hybrid_cartesia:" not in text:
        # pipelines may be absent in local — create if needed
        if re.search(r"(?m)^pipelines:\s*$", text):
            text = inject_under("pipelines", pipe, text)
        else:
            text = text.rstrip() + "\n\npipelines:\n" + pipe + "\n"
    local.write_text(text)
    print("local yaml surgically updated")

# validate YAML still loads
try:
    import yaml
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml
yaml.safe_load(local.read_text())
print("local yaml parses")
PY

echo "== dialplan =="
if grep -q "exten => cartesia" /etc/asterisk/extensions.conf; then
  echo "dialplan already has cartesia"
else
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/asterisk/extensions.conf")
text = p.read_text()
block = """
; Cartesia TTS voice pilot (does NOT change Mango default)
exten => cartesia,1,NoOp(Cartesia TTS pilot)
 same => n,Answer()
 same => n,Set(TIMEOUT(absolute)=600)
 same => n,Set(AI_CONTEXT=cartesia_pilot)
 same => n,Stasis(asterisk-ai-voice-agent)
 same => n,Hangup()
"""
i = text.find("[from-ai-agent]")
if i < 0:
    raise SystemExit("from-ai-agent missing")
j = text.find("; ---------------------------------------------------------------------------", i)
if j < 0:
    j = text.find("\n[", i + 20)
text = text[:j] + block + "\n" + text[j:]
p.write_text(text)
print("dialplan patched")
PY
fi

echo "== env =="
touch /root/ava/.env
grep -q '^CARTESIA_VOICE_ID=' /root/ava/.env || echo 'CARTESIA_VOICE_ID=f786b574-daa5-4673-aa0c-cbe3e8534c02' >> /root/ava/.env
grep -q '^CARTESIA_MODEL_ID=' /root/ava/.env || echo 'CARTESIA_MODEL_ID=sonic-3' >> /root/ava/.env
if grep -q '^CARTESIA_API_KEY=.\+' /root/ava/.env; then
  echo "CARTESIA_API_KEY is set"
  HAVE_KEY=1
else
  echo "CARTESIA_API_KEY missing — code installed, voice pilot inactive until key is added"
  HAVE_KEY=0
fi

echo "== syntax import check inside container network =="
# Quick host-side syntax
python3 -m py_compile /root/ava/src/pipelines/cartesia.py
python3 - <<'PY'
import ast
ast.parse(open("/root/ava/src/config.py").read())
ast.parse(open("/root/ava/src/pipelines/orchestrator.py").read())
print("py compile ok")
PY

asterisk -rx "dialplan reload" || true
docker restart ai_engine
sleep 5
docker ps --filter name=ai_engine --format '{{.Names}} {{.Status}}'
docker logs ai_engine --tail 40 2>&1 | grep -iE "cartesia|error|Registered|pipeline" | tail -20 || true
curl -sf http://127.0.0.1:15000/health >/dev/null && echo health_ok || echo health_fail
echo "DONE backup=$BACKUP have_key=$HAVE_KEY"
