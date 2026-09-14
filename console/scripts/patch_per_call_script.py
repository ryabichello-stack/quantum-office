#!/usr/bin/env python3
"""Patch AVA engine for per-call outbound script/greeting via channel vars."""
from __future__ import annotations

from pathlib import Path

ENGINE = Path("/root/ava/src/engine.py")
MODELS = Path("/root/ava/src/core/models.py")


def patch_models() -> None:
    text = MODELS.read_text(encoding="utf-8")
    if "outbound_call_script" in text:
        print("models already patched")
        return
    old = "    outbound_custom_vars: Dict[str, Any] = field(default_factory=dict)"
    if old not in text:
        raise SystemExit("models needle missing")
    text = text.replace(
        old,
        old
        + "\n    outbound_call_script: Optional[str] = None"
        + "\n    outbound_call_greeting: Optional[str] = None",
        1,
    )
    MODELS.write_text(text, encoding="utf-8")
    print("models patched")


def patch_engine() -> None:
    text = ENGINE.read_text(encoding="utf-8")
    if "outbound_call_script" in text and "AAVA_CALL_SCRIPT_FILE" in text:
        print("engine already patched")
        return

    needle = """                    if isinstance(resp, dict):
                        raw = (resp.get("value") or "").strip()
                        if raw:
                            try:
                                data = json.loads(raw)
                                if isinstance(data, dict):
                                    session.outbound_custom_vars = data
                            except Exception:
                                pass
                    # Improve call history readability: store outbound phone as caller_name too."""
    insert = """                    if isinstance(resp, dict):
                        raw = (resp.get("value") or "").strip()
                        if raw:
                            try:
                                data = json.loads(raw)
                                if isinstance(data, dict):
                                    session.outbound_custom_vars = data
                            except Exception:
                                pass
                    # Per-call script/greeting (Console one-shot) — overrides YAML for THIS call only.
                    try:
                        script_val = ""
                        greet_val = ""
                        script_file = ""
                        for var_name, bucket in (
                            ("AAVA_CALL_SCRIPT_FILE", "file"),
                            ("AAVA_CALL_SCRIPT", "script"),
                            ("AAVA_CALL_GREETING", "greeting"),
                        ):
                            resp2 = await self.ari_client.send_command(
                                "GET",
                                f"channels/{caller_channel_id}/variable",
                                params={"variable": var_name},
                                tolerate_statuses=[404],
                            )
                            if isinstance(resp2, dict):
                                value = (resp2.get("value") or "").strip()
                                if not value:
                                    continue
                                if bucket == "file":
                                    script_file = value
                                elif bucket == "script":
                                    script_val = value
                                else:
                                    greet_val = value
                        if script_file:
                            try:
                                from pathlib import Path as _P
                                fp = _P(script_file)
                                if fp.is_file():
                                    payload = json.loads(fp.read_text(encoding="utf-8"))
                                    if isinstance(payload, dict):
                                        if not script_val:
                                            script_val = str(
                                                payload.get("script") or payload.get("prompt") or ""
                                            ).strip()
                                        if not greet_val:
                                            greet_val = str(payload.get("greeting") or "").strip()
                            except Exception:
                                logger.debug(
                                    "Failed to read AAVA_CALL_SCRIPT_FILE",
                                    call_id=caller_channel_id,
                                    exc_info=True,
                                )
                        cv = getattr(session, "outbound_custom_vars", None) or {}
                        if isinstance(cv, dict):
                            if not script_val:
                                script_val = str(
                                    cv.get("__script__") or cv.get("__prompt__") or ""
                                ).strip()
                            if not greet_val:
                                greet_val = str(cv.get("__greeting__") or "").strip()
                        if script_val:
                            session.outbound_call_script = script_val
                        if greet_val:
                            session.outbound_call_greeting = greet_val
                        if script_val or greet_val:
                            logger.info(
                                "Per-call outbound script loaded",
                                call_id=caller_channel_id,
                                script_chars=len(script_val or ""),
                                greeting_chars=len(greet_val or ""),
                                via_file=bool(script_file),
                            )
                    except Exception:
                        logger.debug(
                            "Failed to load per-call outbound script",
                            call_id=caller_channel_id,
                            exc_info=True,
                        )
                    # Improve call history readability: store outbound phone as caller_name too."""
    if needle not in text:
        raise SystemExit("engine load needle missing")
    text = text.replace(needle, insert, 1)

    old = """                        if greeting_to_apply:
                            session.provider_overrides["greeting"] = greeting_to_apply
                            logger.info(
                                "Stored context greeting for provider session",
                                call_id=session.call_id,
                                context=transport.context,
                                greeting_preview=(
                                    (greeting_to_apply[:50] + "...")
                                    if len(greeting_to_apply) > 50
                                    else greeting_to_apply
                                ),
                            )
                        if context_config.prompt:
                            prompt_to_apply = context_config.prompt
                            # Apply template substitution for caller context variables
                            prompt_to_apply = self._apply_prompt_template_substitution(prompt_to_apply, session)
                            if getattr(session, "is_outbound", False) and getattr(session, "outbound_custom_vars", None):
                                prompt_to_apply = self._append_outbound_custom_vars_to_prompt(
                                    prompt_to_apply,
                                    getattr(session, "outbound_custom_vars", {}) or {},
                                )
                            session.provider_overrides["prompt"] = prompt_to_apply
                            logger.info(
                                "Stored context prompt for provider session",
                                call_id=session.call_id,
                                context=transport.context,
                                prompt_length=len(prompt_to_apply or ""),
                            )"""
    new = """                        # Per-call Console script wins over YAML context for this call only.
                        per_call_greeting = (getattr(session, "outbound_call_greeting", None) or "").strip()
                        per_call_script = (getattr(session, "outbound_call_script", None) or "").strip()
                        if per_call_greeting:
                            greeting_to_apply = per_call_greeting
                        if greeting_to_apply:
                            session.provider_overrides["greeting"] = greeting_to_apply
                            logger.info(
                                "Stored context greeting for provider session",
                                call_id=session.call_id,
                                context=transport.context,
                                per_call=bool(per_call_greeting),
                                greeting_preview=(
                                    (greeting_to_apply[:50] + "...")
                                    if len(greeting_to_apply) > 50
                                    else greeting_to_apply
                                ),
                            )
                        prompt_to_apply = None
                        if per_call_script:
                            prompt_to_apply = per_call_script
                        elif context_config.prompt:
                            prompt_to_apply = context_config.prompt
                        if prompt_to_apply:
                            prompt_to_apply = self._apply_prompt_template_substitution(prompt_to_apply, session)
                            if (
                                getattr(session, "is_outbound", False)
                                and getattr(session, "outbound_custom_vars", None)
                                and not per_call_script
                            ):
                                prompt_to_apply = self._append_outbound_custom_vars_to_prompt(
                                    prompt_to_apply,
                                    getattr(session, "outbound_custom_vars", {}) or {},
                                )
                            session.provider_overrides["prompt"] = prompt_to_apply
                            logger.info(
                                "Stored context prompt for provider session",
                                call_id=session.call_id,
                                context=transport.context,
                                per_call=bool(per_call_script),
                                prompt_length=len(prompt_to_apply or ""),
                            )"""
    if old not in text:
        raise SystemExit("engine apply needle missing")
    text = text.replace(old, new, 1)
    ENGINE.write_text(text, encoding="utf-8")
    print("engine patched")


if __name__ == "__main__":
    patch_models()
    patch_engine()
