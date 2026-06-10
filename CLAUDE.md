# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                  # install deps (incl. dev group)
uv run alembic upgrade head              # create/migrate data/app.db
uv run uvicorn app.main:app --reload --port 8000

uv run pytest                            # full unit + integration suite (~30s, slow tests deselected)
uv run pytest -m slow                    # also run the ~11k-line full-corpus ingestion test
uv run pytest tests/unit/test_dates.py   # single file
uv run pytest tests/unit/test_dates.py::test_normalize_date_iso_string  # single test
uv run ruff check .
```

There is a single Alembic migration (`alembic/versions/0001_initial_schema.py`).
If you change a model in `app/models/`, edit that migration directly (don't add
a second one) unless the user asks for proper migration history.

## Architecture

This is a FastAPI + SQLAlchemy 2.0 + SQLite service that ingests noisy JSONL
"climate policy document" metadata and exposes a query/stats API. The full
design rationale lives in `docs/architecture_plan.md` and the two ADRs
(`docs/adr/0001-staged-db-as-queue-pipeline.md`,
`docs/adr/0002-duplicate-detection-grouping.md`); `CONTEXT.md` is the domain
glossary (Ingestion Run, Raw Record, Document, Duplicate Group, Canonical
Document, Quality Score, Unknown sentinel, etc.) — read it before using these
terms in code or commit messages.

### Staged "DB as queue" pipeline (the core thing to understand)

`POST /ingestions` does the minimum synchronously (hash + stage the upload,
insert an `ingestion_runs` row with `status='queued'`), then schedules
`app.services.ingestion_service.run_pipeline(run_id)` as a FastAPI
`BackgroundTask`. There is **no external queue** — nullable DB columns/status
fields double as queue markers, and each "worker" in `app/processing/` is a
`process_batch(db, batch_size) -> (processed, remaining)` that pulls one batch
from its queue:

| Stage | Worker | Queue condition | On completion sets |
|---|---|---|---|
| 0 | `raw_load_worker.process_run()` | staged `.jsonl`, line by line | `raw_documents` rows (`status='pending'`) or `ingestion_errors` |
| 1 | `normalize_worker` | `raw_documents.status='pending'` | inserts `documents` row, `status='normalized'` |
| 2 | `duplicates_worker` | `documents.duplicate_group_id IS NULL AND is_canonical IS NULL` | `duplicate_group_id`/`is_canonical`/`duplicate_confidence` |
| 3 | `scoring_worker` | `documents.quality_score IS NULL` | `quality_score` |

`run_pipeline()`: runs stage 0 if `run.status == 'queued'`, then `_drain()`s
stages 1-3 (loops `process_batch()` until `remaining == 0`), then sets
`run.status = 'completed'` (or `'failed'` + `error_message` on exception).

Stages 1-3 operate on **global** queues, not scoped to one run — the
`POST /processing/{normalize,duplicates,scoring}` endpoints can drive them
independently of any ingestion.

**Concurrency**: `ingestion_service._pipeline_lock` (a process-wide
`threading.Lock`) serializes all `run_pipeline()` calls, because the
DB-as-queue design has no row-level locking — concurrent background tasks
would race on the same global queue rows. Don't remove this lock without
replacing the queue-claiming strategy.

**Startup** (`app/main.py` lifespan): `resume_pending_runs()` re-launches any
non-terminal run, then `drain_all_queues()` mops up global leftovers. Both are
no-ops when nothing is pending.

**Idempotency**: `POST /ingestions` SHA-256-hashes the upload; if a
`completed` run already has that hash, it's rejected with `409` unless
`?force=true`.

### Layout

- `app/models/` — SQLAlchemy models. `documents` has no `ingestion_run_id`;
  trace provenance via `documents.raw_document_id → raw_documents.ingestion_run_id`.
  `authors`/`organizations` each have a shared `"Unknown"` sentinel row
  (`normalized_name="__unknown__"`, see `app/models/sentinels.py`).
- `app/ingestion/normalizers/` — one pure module per field group (`text`,
  `dates`, `identity`, `tags`, `language`, `status`, `document_type`,
  `numbers`, `booleans`, `links`). Each normalizer takes a raw value and
  returns `(value, raw_or_None, warning_or_None)` and never raises; warnings
  accumulate into `documents.normalization_warnings` (JSON list).
- `app/processing/` — the 4 stage workers described above.
- `app/services/ingestion_service.py` — pipeline orchestration
  (`run_pipeline`, `_drain`, `resume_pending_runs`, `drain_all_queues`,
  `create_run`, `build_run_detail`). `app/services/document_service.py` and
  `stats_service.py` back the `/documents` and `/stats` routers.
- `app/api/routers/` — `ingestions`, `processing`, `documents`, `stats`.
  `GET /ingestions/{id}` and `GET /documents` use two different pagination
  shapes: `OffsetPage[T]` (`items/total/limit/offset`) vs `Page[T]`
  (`items/total/page/page_size`) — see `app/schemas/common.py`.
- `app/logging_config.py` — per-run log files at
  `logs/ingestion_run_{run_id}.log` (via `run_log_handler(run_id)`, attached/
  detached around `_run_pipeline_locked`), in addition to stdout.

### Duplicate detection & quality score

Two documents are duplicates iff they share `normalized_title` AND (same
non-Unknown `author_id` OR same non-null `source_name`); connected components
within a title cohort form a group, canonical = earliest `published_at` →
most-complete → lowest `id` (ADR 0002). `quality_score` (0-100) is a weighted
sum of citation percentile, relevance, recency decay, and completeness flags —
weights are hardcoded constants in `scoring_worker.py`. The `"many"`/`"high"`
string sentinels for `citation_count`/`relevance_score` are read live from
`raw_documents.raw_data` during scoring (the `documents` columns themselves
stay `NULL` for these).

## Testing notes

- `tests/conftest.py`: `client` and `db_session` fixtures share one
  `tmp_path`-backed SQLite engine per test (seeded with the Unknown
  author/org sentinels), with `get_db` and `ingestion_service.SessionLocal`
  both overridden to the same `sessionmaker`. `settings.upload_dir` and
  `settings.log_dir` are monkeypatched into `tmp_path` — tests never touch
  `data/` or `logs/`.
- `TestClient` runs `BackgroundTasks` synchronously as part of the request, so
  `client.post("/ingestions", ...)` blocks until the *entire* pipeline
  (stages 0-3) has completed — no polling needed in tests.
- `tests/factories.py` has helpers for building raw JSONL records.
- `tests/integration/test_full_corpus.py` (marked `slow`) ingests all of
  `input_docs/documents_*.jsonl` and asserts the headline numbers documented
  in `docs/stats_examples.md` (10,555 documents, 41 distinct titles, 48
  duplicate groups, 8,066 total duplicates).
