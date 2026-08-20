#!/usr/bin/env python3
"""Allow openai_realtime provider aliases (e.g. openai_realtime_outbound)."""
from pathlib import Path

p = Path("/root/ava/src/engine.py")
text = p.read_text(encoding="utf-8")
needle = '                elif name == "openai_realtime":'
if 'type") or "").strip().lower() == "openai_realtime"' in text:
    print("already patched")
    raise SystemExit(0)
if needle not in text:
    raise SystemExit("needle not found")
replacement = '''                elif name == "openai_realtime" or (
                    isinstance(provider_config_data, dict)
                    and str(provider_config_data.get("type") or "").strip().lower() == "openai_realtime"
                ):
                    # Profile aliases (openai_realtime_outbound) share implementation via type.'''
# Replace only the elif line; keep the body.
text2 = text.replace(needle, replacement, 1)
# Soften the success log that hardcodes openai_realtime name
old_log = '''                    logger.info(
                        "Provider 'openai_realtime' loaded successfully",
                        audio_gating_enabled=self.audio_gating_manager is not None
                    )'''
new_log = '''                    logger.info(
                        "Provider loaded successfully",
                        provider=name,
                        provider_type="openai_realtime",
                        audio_gating_enabled=self.audio_gating_manager is not None
                    )'''
if old_log in text2:
    text2 = text2.replace(old_log, new_log, 1)
else:
    print("warn: success log pattern not found (elif still patched)")
p.write_text(text2, encoding="utf-8")
print("patched", p)
