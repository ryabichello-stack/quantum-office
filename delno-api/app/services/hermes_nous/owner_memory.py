"""Tenant/user-scoped curated memory for Owner Hermes.

Only short validated facts and summaries are retained. Raw prompts, tool
responses, credentials and document contents are not copied to this store.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.hermes_memory import HermesMemory, HermesMemoryBlock, HermesMemoryState
from app.models.hermes_owner_turn import HermesOwnerTurn

KINDS = {"company_fact", "preference", "decision", "rejected_option", "project", "goal", "open_task", "result"}
_KIND_TRANSITIONS = {
    ("decision", "rejected_option"), ("rejected_option", "decision"),
    ("open_task", "result"), ("result", "open_task"),
}
_KEY = re.compile(r"^[a-z][a-z0-9_.-]{2,119}$")
_SECRET = re.compile(
    r"(?i)(?:\b(?:password|пароль|api[_-]?key|secret|token|токен)\b\s*[:=]\s*\S+"
    r"|\bBearer\s+\S+|\bdmcp_[A-Za-z0-9_-]+|\bsk-[A-Za-z0-9_-]{16,}"
    r"|\b\d{8,12}:[A-Za-z0-9_-]{30,})"
)
_WORD = re.compile(r"[\w-]{3,}", re.UNICODE)
_INJECTION = re.compile(
    r"(?i)(ignore (?:all |previous )?instructions|system prompt|developer message|"
    r"игнорируй (?:все |предыдущие )?инструкции|системн\w* (?:промпт|команд)|"
    r"выполни команду|отключи проверк|выдай (?:ключ|токен)|<\/?(?:system|developer)>)"
)
_NO_STORE = re.compile(r"(?i)\b(?:не запоминай|не сохраняй|забудь это|не заноси в память|do not remember|don't remember)\b")
_PII = re.compile(r"(?i)(?:[\w.+-]+@[\w.-]+\.[a-z]{2,}|\+?\d[\d\s()\-]{9,}\d)")
_REQUEST = re.compile(
    r"(?i)^\s*(?:продолжим|напомни|расскажи|скажи|покажи|проверь|найди|"
    r"какое|какой|какая|что|как|когда|где|почему|вызови|создай|сделай|"
    r"remind|tell|show|check|find|what|how|when|where|why)\b"
)
_IMPERATIVE = re.compile(r"(?i)\b(?:напомни|расскажи|скажи|покажи|проверь|найди|вызови|создай|сделай|remind|tell|show|check|find)\b")


def owner_memory_enabled(db: Session, ctx: TenantContext) -> bool:
    if (os.environ.get("DELNO_OWNER_MEMORY_ENABLED") or "").strip().lower() not in ("1", "true", "yes"):
        return False
    return bool(db.scalar(select(FeatureFlag.enabled).where(
        FeatureFlag.tenant_id == ctx.tenant_id,
        FeatureFlag.flag_key == "hermes_owner_memory",
    )))


def _scope(ctx: TenantContext):
    return (HermesMemory.tenant_id == ctx.tenant_id, HermesMemory.user_id == ctx.user_id)


def _safe(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or "\n" in text or _SECRET.search(text) or _INJECTION.search(text) or _PII.search(text):
        return ""
    for word in text.split():
        if len(word) >= 28 and sum(c.isdigit() for c in word) >= 3 and any(c.isupper() for c in word):
            return ""
    return text


def memory_epoch(db: Session, ctx: TenantContext) -> int:
    if ctx.user_id is None:
        return 0
    row = db.scalar(select(HermesMemoryState).where(
        HermesMemoryState.tenant_id == ctx.tenant_id,
        HermesMemoryState.user_id == ctx.user_id,
    ))
    return row.epoch if row else 0


def _rotate_epoch(db: Session, ctx: TenantContext) -> None:
    row = db.scalar(select(HermesMemoryState).where(
        HermesMemoryState.tenant_id == ctx.tenant_id,
        HermesMemoryState.user_id == ctx.user_id,
    ).with_for_update())
    if row is None:
        db.add(HermesMemoryState(tenant_id=ctx.tenant_id, user_id=ctx.user_id, epoch=1))
    else:
        row.epoch += 1


def _block_hash(key: str) -> str:
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()


def owner_context(db: Session, ctx: TenantContext, query: str) -> str:
    """Bounded, relevant recall; memory text never changes grants or instructions."""
    if ctx.user_id is None:
        return ""
    memories = list(db.scalars(select(HermesMemory).where(*_scope(ctx)).limit(1000)).all())
    words = set(_WORD.findall(query.lower()))
    priority = {"decision": 5, "goal": 4, "open_task": 4, "project": 3, "rejected_option": 3}

    def score(item: HermesMemory) -> tuple[int, str]:
        content = f"{item.memory_key} {item.value}".lower()
        hits = sum(1 for word in words if word in content)
        return (hits * 10 + priority.get(item.kind, 0), str(item.updated_at or ""))

    selected = sorted(memories, key=score, reverse=True)[:16]
    summaries = list(db.scalars(select(HermesOwnerTurn).where(
        HermesOwnerTurn.tenant_id == ctx.tenant_id,
        HermesOwnerTurn.user_id == ctx.user_id,
    ).order_by(HermesOwnerTurn.created_at.desc()).limit(6)).all())
    payload = {
        "facts": [{"kind": m.kind, "key": m.memory_key, "value": m.value} for m in selected],
        "recent": [s.summary for s in reversed(summaries)],
    }
    while len(json.dumps(payload, ensure_ascii=False)) > 6000:
        if payload["recent"]:
            payload["recent"].pop(0)
        elif payload["facts"]:
            payload["facts"].pop()
        else:
            break
    return json.dumps(payload, ensure_ascii=False) if payload["facts"] or payload["recent"] else ""


def _extract(message: str, reply: str, existing_keys: list[str]) -> dict[str, Any] | None:
    from app.services.model_provider import get_model_provider
    from app.services.tenant_vault import looks_like_credential_paste

    if ("?" in message or _REQUEST.search(message) or _IMPERATIVE.search(message) or
            _INJECTION.search(message) or _SECRET.search(message) or
            looks_like_credential_paste(message) or _NO_STORE.search(message)):
        return None
    prompt = (
        "Извлеки только явно сказанные пользователем устойчивые факты и решения. "
        "Если сообщение только вопрос, просьба или команда без нового факта — верни пустые memories и summary. "
        "Не выводи факт из формулировки вопроса и не заменяй решение предположением. "
        "Сделай краткую безопасную тему разговора только по словам пользователя. "
        "Не сохраняй пароли, токены, ключи, платёжные реквизиты и личные данные клиентов. "
        "Если пользователь просит не запоминать — верни пустые memories и summary. "
        "Верни строго JSON: {\"summary\": короткая тема или пусто, \"memories\": "
        "[{\"key\": английский устойчивый ключ вида sales.channel, \"kind\": один из "
        + ", ".join(sorted(KINDS)) + ", \"value\": короткий факт по-русски}]}. "
        "Каждый key может встретиться только один раз. Если в одном сообщении есть несколько "
        "уточнений одного решения, объедини их в одно value, не теряя основной выбор. "
        "Создавай устойчивый key из смысла самого сообщения: sales.channel для основного "
        "канала продаж, sales.cold_calls для холодных звонков, writing.headline_phrase "
        "для любимой фразы заголовка. Не привязывай новый предмет к ключу другой темы."
    )
    result = get_model_provider().chat_completion(
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": message[:2000]}],
        max_tokens=450,
    )
    if not result.get("ok"):
        return None
    content = str((((result.get("data") or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        return None


def remember_owner_turn(
    db: Session, ctx: TenantContext, *, session_id: str, run_id: str,
    request_text: str, response_text: str,
) -> bool:
    if ctx.user_id is None or not session_id.startswith(f"{ctx.tenant_slug}:") or not run_id:
        return False
    if db.scalar(select(HermesOwnerTurn.id).where(
        HermesOwnerTurn.tenant_id == ctx.tenant_id, HermesOwnerTurn.run_id == run_id,
    )):
        return False
    existing = list(db.scalars(select(HermesMemory).where(*_scope(ctx))).all())
    extracted = _extract(request_text, response_text, [m.memory_key for m in existing])
    if extracted is None:
        return False
    summary = _safe(extracted.get("summary"), 400)
    candidates = extracted.get("memories") if isinstance(extracted.get("memories"), list) else []
    blocks = set(db.scalars(select(HermesMemoryBlock.key_hash).where(
        HermesMemoryBlock.tenant_id == ctx.tenant_id,
        HermesMemoryBlock.user_id == ctx.user_id,
    )).all())
    current = {m.memory_key: m for m in existing}
    changed = False
    superseded = False
    grouped: dict[str, tuple[str, str]] = {}
    for candidate in candidates[:8]:
        if not isinstance(candidate, dict):
            continue
        key = str(candidate.get("key") or "").strip().lower()
        kind = str(candidate.get("kind") or "")
        value = _safe(candidate.get("value"), 350)
        if not _KEY.fullmatch(key) or kind not in KINDS or not value or _block_hash(key) in blocks:
            continue
        if key in grouped:
            old_kind, old_value = grouped[key]
            if value not in old_value:
                combined = _safe(old_value.rstrip(". ") + "; " + value, 350)
                if combined:
                    grouped[key] = (old_kind, combined)
        else:
            grouped[key] = (kind, value)
    for key, (kind, value) in grouped.items():
        row = current.get(key)
        if row is None:
            row = HermesMemory(tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                               memory_key=key, kind=kind, value=value, history=[], source_run_id=run_id)
            db.add(row)
            current[key] = row
            changed = True
        elif row.kind != kind and (row.kind, kind) not in _KIND_TRANSITIONS:
            # A different semantic type under the same key is usually model
            # key reuse, not a legitimate correction. Keep the existing fact.
            continue
        elif row.value != value:
            row.history = [*(row.history or [])[-9:], {"kind": row.kind, "value": row.value}]
            row.kind, row.value, row.source_run_id = kind, value, run_id
            changed = True
            superseded = True
    if superseded:
        db.execute(delete(HermesOwnerTurn).where(
            HermesOwnerTurn.tenant_id == ctx.tenant_id,
            HermesOwnerTurn.user_id == ctx.user_id,
        ))
        _rotate_epoch(db, ctx)
    if summary:
        db.add(HermesOwnerTurn(tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                               session_id=session_id[:200], run_id=run_id[:120], summary=summary))
    if changed or summary:
        db.commit()
    return changed or bool(summary)


def list_owner_turns(db: Session, ctx: TenantContext, *, limit: int = 30) -> list[HermesOwnerTurn]:
    if ctx.user_id is None:
        return []
    return list(db.scalars(select(HermesOwnerTurn).where(
        HermesOwnerTurn.tenant_id == ctx.tenant_id,
        HermesOwnerTurn.user_id == ctx.user_id,
    ).order_by(HermesOwnerTurn.created_at.desc()).limit(min(max(limit, 1), 50))).all())


def list_memories(db: Session, ctx: TenantContext) -> list[HermesMemory]:
    if ctx.user_id is None:
        return []
    return list(db.scalars(select(HermesMemory).where(*_scope(ctx)).order_by(HermesMemory.updated_at.desc())).all())


def delete_memory(db: Session, ctx: TenantContext, memory_id: uuid.UUID) -> bool:
    row = db.scalar(select(HermesMemory).where(*_scope(ctx), HermesMemory.id == memory_id))
    if row is None:
        return False
    db.delete(row)
    db.execute(delete(HermesOwnerTurn).where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
                                                   HermesOwnerTurn.user_id == ctx.user_id))
    _rotate_epoch(db, ctx)
    db.commit()
    return True


def edit_memory(db: Session, ctx: TenantContext, memory_id: uuid.UUID, value: str) -> bool:
    row = db.scalar(select(HermesMemory).where(*_scope(ctx), HermesMemory.id == memory_id))
    safe = _safe(value, 350)
    if row is None or not safe:
        return False
    row.history = [*(row.history or [])[-9:], {"kind": row.kind, "value": row.value}]
    row.value = safe
    db.execute(delete(HermesOwnerTurn).where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
                                                   HermesOwnerTurn.user_id == ctx.user_id))
    _rotate_epoch(db, ctx)
    db.commit()
    return True


def block_memory_key(db: Session, ctx: TenantContext, key: str) -> bool:
    key = key.strip().lower()
    if ctx.user_id is None or not _KEY.fullmatch(key):
        return False
    hashed = _block_hash(key)
    if not db.scalar(select(HermesMemoryBlock.id).where(
        HermesMemoryBlock.tenant_id == ctx.tenant_id,
        HermesMemoryBlock.user_id == ctx.user_id,
        HermesMemoryBlock.key_hash == hashed,
    )):
        db.add(HermesMemoryBlock(tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                                 memory_key=key, key_hash=hashed))
    db.execute(delete(HermesMemory).where(*_scope(ctx), HermesMemory.memory_key == key))
    db.execute(delete(HermesOwnerTurn).where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
                                                   HermesOwnerTurn.user_id == ctx.user_id))
    _rotate_epoch(db, ctx)
    db.commit()
    return True


def list_memory_blocks(db: Session, ctx: TenantContext) -> list[str]:
    if ctx.user_id is None:
        return []
    return list(db.scalars(select(HermesMemoryBlock.memory_key).where(
        HermesMemoryBlock.tenant_id == ctx.tenant_id,
        HermesMemoryBlock.user_id == ctx.user_id,
    )).all())


def unblock_memory_key(db: Session, ctx: TenantContext, key: str) -> bool:
    if ctx.user_id is None or not _KEY.fullmatch(key):
        return False
    count = db.execute(delete(HermesMemoryBlock).where(
        HermesMemoryBlock.tenant_id == ctx.tenant_id,
        HermesMemoryBlock.user_id == ctx.user_id,
        HermesMemoryBlock.key_hash == _block_hash(key),
    )).rowcount or 0
    db.commit()
    return bool(count)


def clear_owner_turns(db: Session, ctx: TenantContext) -> int:
    if ctx.user_id is None:
        return 0
    count = db.execute(delete(HermesMemory).where(*_scope(ctx))).rowcount or 0
    db.execute(delete(HermesOwnerTurn).where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
                                                   HermesOwnerTurn.user_id == ctx.user_id))
    _rotate_epoch(db, ctx)
    db.commit()
    return int(count)
