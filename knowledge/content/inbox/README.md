# Knowledge drop zone

Put **new** Markdown/text knowledge files here (or in `topics/`).

Rules:
- Do **not** copy `quantum_labs.md` here — it is ingested via FAQ pipeline.
- Do not put archives/duplicates of content already in the main corpus.
- Ingest picks up new/changed files automatically (timer); unchanged hashes are skipped.
- Duplicate content (same body hash as an existing doc) is not indexed twice.

After adding a file on prod under `/opt/ava-knowledge/content/inbox/`:

```bash
PYTHONPATH=/opt/ava-knowledge /opt/ava-knowledge/venv/bin/python -m brain_platform ingest --sources files --file-limit 2000
PYTHONPATH=/opt/ava-knowledge /opt/ava-knowledge/venv/bin/python -m brain_platform embed-backfill --limit 400
```
