# Document Intake and Review Service

A backend service that ingests noisy JSONL document metadata into a relational
database, normalizes it, and exposes a REST API for querying documents and
corpus-wide statistics. Built with **Python 3.12 + FastAPI + SQLAlchemy 2.0 +
Alembic + SQLite**.

In addition to the required ingestion/list/detail/stats endpoints, the service
implements all three optional processing steps:

- **Duplicate detection** — groups documents into duplicate clusters and picks a
  canonical representative ([ADR 0002](docs/adr/0002-duplicate-detection-grouping.md)).
- **Quality scoring** — computes a 0-100 `quality_score` per document (§ below).
- **Document classification** — normalizes `document_type` into 7 canonical
  categories (or `unknown`).

See [`CONTEXT.md`](CONTEXT.md) for the project's domain glossary (Ingestion Run,
Raw Record, Document, Duplicate Group, Canonical Document, Quality Score, etc.) —
the rest of this README assumes those terms.

## Quick start

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Ingest a file (returns immediately with `status: "queued"`; processing happens
in the background):

```bash
curl -s -F "file=@input_docs/documents_1.jsonl" http://localhost:8000/ingestions
# {"id":1,"status":"queued","source_file":"documents_1.jsonl","file_hash":"..."}

curl -s http://localhost:8000/ingestions/1
# poll until "status": "completed"
```

Repeat for each `input_docs/documents_*.jsonl` file (one `POST` per file — see
[`docs/execution_log_sample.md`](docs/execution_log_sample.md) for a full
captured run across all 5 files). Re-posting an already-completed file without
`?force=true` returns `409`.

Many more examples (every endpoint, every filter, the upload/idempotency flow)
are in [`docs/api_examples.md`](docs/api_examples.md), and a real `/stats`
response is in [`docs/stats_examples.md`](docs/stats_examples.md).

### Tests and linting

```bash
uv run pytest          # full unit + integration suite (fast, ~30s)
uv run pytest -m slow   # also run the full ~11k-line corpus ingestion test
uv run ruff check .
```

## Architecture

### Staged pipeline ("DB as queue")

`POST /ingestions` does the minimum work synchronously — read the upload,
SHA-256 hash it, stage it under `data/uploads/`, insert an `ingestion_runs` row
— then schedules the rest as a FastAPI `BackgroundTask`. All parsing and
processing happens in 4 stages, each implemented as a `process_batch()`
"worker" pulling from a queue defined by nullable DB columns
(see [ADR 0001](docs/adr/0001-staged-db-as-queue-pipeline.md)):

| Stage | Worker | Reads | Writes |
|---|---|---|---|
| 0 | `raw_load_worker` | staged `.jsonl` file, line by line | `raw_documents` (`status='pending'`) or `ingestion_errors` |
| 1 | `normalize_worker` | `raw_documents` where `status='pending'` | `documents` row (1:1) + upserts `authors`/`organizations`/`tags`; sets `status='normalized'` |
| 2 | `duplicates_worker` | `documents` where `duplicate_group_id IS NULL AND is_canonical IS NULL` | `duplicate_group_id`, `is_canonical`, `duplicate_confidence` |
| 3 | `scoring_worker` | `documents` where `quality_score IS NULL` | `quality_score` |

`app/services/ingestion_service.run_pipeline(run_id)` runs stage 0 (if the run
is still `queued`) then drains stages 1-3 to completion (`_drain()` loops
`process_batch()` until the global queue is empty), and marks the run
`completed` (or `failed`, recording `error_message`).

Because stages 1-3 operate on **global** queues (not scoped to one run), the
`/processing/{normalize,duplicates,scoring}` endpoints can also be called
manually to drive one batch at a time.

### Concurrency, resume, and idempotency

- A process-wide lock (`ingestion_service._pipeline_lock`) serializes
  `run_pipeline()` calls, since the DB-as-queue design has no row-level locking
  — concurrent background tasks for different runs would otherwise race on the
  same global queue rows (`UNIQUE constraint` errors on `authors`/`documents`).
- On startup, `resume_pending_runs()` re-launches any run not in a terminal
  state, and `drain_all_queues()` mops up any global leftovers from a prior
  unclean shutdown. Both are safe no-ops when nothing is pending.
- `POST /ingestions` computes a SHA-256 of the uploaded file; if a `completed`
  run already has that hash, the request is rejected with `409` unless
  `?force=true` is passed.

### Logging

Each ingestion run gets its own log file at `logs/ingestion_run_{run_id}.log`
(in addition to stdout). `INFO` marks stage start/end and batch progress,
`WARNING` mirrors per-document `normalization_warnings`, and `ERROR` mirrors
rows written to `ingestion_errors`. See
[`docs/execution_log_sample.md`](docs/execution_log_sample.md) for a full
example.

## Database schema

Defined in `app/models/` and created by the single Alembic migration
[`alembic/versions/0001_initial_schema.py`](alembic/versions/0001_initial_schema.py).

```
ingestion_runs ──< ingestion_errors
       │
       └──< raw_documents ──1:1── documents >── author_id ──> authors
                                       │ \── organization_id ──> organizations
                                       └──< document_tags >── tags
```

- **`ingestion_runs`**: one row per `POST /ingestions` (source file, hash,
  staged path, status, `total_lines`/`raw_loaded_count`/`skipped_count`).
- **`ingestion_errors`**: one row per hard-skipped line (`invalid_json` /
  `not_object` / `broken_stub`), with the truncated raw line and detail.
- **`raw_documents`**: one row per structurally-valid input line (verbatim
  `raw_data` JSON), `status` = `pending` → `normalized` (the stage-1 queue
  marker).
- **`documents`**: one row per `raw_documents` row (~10,555 for the full
  corpus) — normalized fields, `*_raw` companions for lossy conversions
  (dates, status, language, booleans, document_type), `url_valid`/`doi_valid`
  flags, and the stage-2/3 result columns `duplicate_group_id` /
  `is_canonical` / `duplicate_confidence` / `quality_score` (all nullable —
  `NULL` = pending). `normalization_warnings` is a JSON list of human-readable
  notes.
- **`authors`** / **`organizations`**: deduplicated by `normalized_name`, each
  seeded with a shared `"Unknown"` sentinel row (`normalized_name="__unknown__"`)
  for missing/junk names.
- **`tags`** / **`document_tags`**: many-to-many, tag names lowercase/trimmed.

`documents` has no `ingestion_run_id` — trace provenance via
`documents.raw_document_id → raw_documents.ingestion_run_id`.

## API

| Endpoint | Description |
|---|---|
| `POST /ingestions?force=` | Upload one `.jsonl` file (`multipart/form-data`, field `file`); `409` if already ingested unless `force=true` |
| `GET /ingestions?limit=&offset=` | Paginated run history, newest first |
| `GET /ingestions/{id}` | Run detail: counts, per-stage pending counts, sample errors |
| `POST /processing/{normalize,duplicates,scoring}?batch_size=` | Manually drive one batch of a stage; `{processed, remaining}` |
| `GET /documents` | Paginated, filterable document list (see below) |
| `GET /documents/{id}` | Document detail incl. author/organization/tags/`duplicate_group` |
| `GET /stats` | Corpus-wide aggregate statistics |

`GET /documents` filters: `published_after`/`published_before` (date),
`tag`, `organization`, `status`, `document_type`, `language`, `region`,
`q` (substring search over title/abstract/body), `canonical_only` (default
`false`), `min_quality_score`, `sort_by` (`id`/`published_at`/`quality_score`/
`created_at`), `sort_dir` (`asc`/`desc`), plus `page`/`page_size` pagination.

Full curl examples for every endpoint and filter are in
[`docs/api_examples.md`](docs/api_examples.md).

## Processing steps

### Duplicate detection (stage 2)

Two documents are duplicates iff they share a `normalized_title` AND (the same
non-Unknown author **or** the same non-empty `source_name`). Connected
components within each title cohort form Duplicate Groups; the Canonical
Document is the earliest-published, then most-complete, then lowest-`id`
member. `duplicate_confidence` (0.5-1.0) starts at `0.5` for the title match
and adds `+0.25` each for a shared author / shared source, plus `+0.1` each
for organization / language / region agreement with another group member.
Rationale and alternatives considered are in
[ADR 0002](docs/adr/0002-duplicate-detection-grouping.md).

### Quality scoring (stage 3)

`quality_score` (0-100, 2dp) is a weighted sum:

| Component | Weight | Notes |
|---|---|---|
| Citation percentile | 25 | Percentile rank of `citation_count` among all non-null values; `"many"` (unparseable string) is treated as the 90th percentile |
| Relevance | 20 | `relevance_score` (0-1); `"high"` (unparseable string) is treated as `0.9`; otherwise `0` |
| Recency | 20 | Exponential decay, `exp(-age_years / 5)`; future-dated → max bonus |
| Peer reviewed | 15 | `+15` if `peer_reviewed is True` |
| Open access | 10 | `+10` if `open_access is True` |
| Has word count | 5 | `+5` if `word_count` is truthy |
| Has page count | 5 | `+5` if `page_count` is truthy |

`documents.citation_count`/`relevance_score` themselves stay `NULL` for
"many"/"high" — only the score computation substitutes a stand-in, read live
from `raw_documents.raw_data`.

### Document classification (stage 1)

`document_type` is matched case-insensitively against 7 canonical values
(`report`, `working_paper`, `policy_brief`, `journal_article`, `news_article`,
`press_release`, `dataset`); anything else (including `null`) becomes
`unknown`, with the original value preserved in `document_type_raw`.

## Assumptions

Every messy-data decision below was verified against the actual
`input_docs/*.jsonl` (11,000 lines, profile documented in
[`docs/architecture_plan.md`](docs/architecture_plan.md)):

- **`{}`** (empty object) is a *valid* record → an all-null `documents` row, not
  an `ingestion_errors` row. Only `[]` (`not_object`), `{"broken": true}`
  (`broken_stub`), and unparseable JSON (`invalid_json`) are hard-skipped.
- **`external_id`**: `"duplicate-id"` / `""` / `null` all mean "no external id"
  → `raw_external_id = NULL` (it is **not** unique and not used as an identity
  key — provenance is via `raw_document_id`).
- **`author_name`/`organization_name`**: `null` / `""` / whitespace / `"N/A"` /
  `"Unknown Author"` (case-insensitive) all map to a shared **Unknown**
  sentinel row; integers coerce to their string form and are treated as real
  names.
- **`source_name`**: `""`, `null`, and `"unknown"` (any case) all normalize to
  `NULL` — there's no `source_name_raw` column since the original is
  recoverable from `raw_documents.raw_data`.
- **`region`**: `""`/`null` → `NULL`; the 13 real region values pass through
  unchanged (no canonical-set validation, since the dataset profile showed no
  case/whitespace variants).
- **`tags`**: list (filtering out `null`/non-string elements, with a warning),
  CSV/semicolon-separated string, dict (`list(values())`), or `null` → `[]`;
  any other type → `[]` + warning. Deduped, lowercased, sorted.
- **`status`**: canonical `{draft, published, archived, unknown}`. String
  matches the 4 names case-insensitively (else `unknown` + warning); bool
  `True/False` → `published`/`draft`; int `0/1/2` → `draft/published/archived`,
  other ints/`null` → `unknown` (no warning — these are "valid" sentinel
  encodings in this dataset).
- **`language`**: 9 ISO-2 codes pass through; `"english"` → `en`; `"xx"` /
  `""` / `null` → `unknown`; anything else → `unknown` + warning.
- **`citation_count`/`relevance_score`**: the only non-numeric strings in the
  corpus are `"many"`/`"high"` — both normalize to `NULL` + warning, but feed
  a stand-in value into `quality_score` (see above) since they're meaningful
  signals, not garbage.
- **`url`/`doi`**: stored as-is plus a `_valid` boolean (scheme+netloc for
  URLs, a `^10\.\d{4,9}/\S+$` regex for DOIs); invalid/empty values are not
  rejected, just flagged.
- **Idempotency is per-file-hash, not per-record**: re-ingesting the same bytes
  without `force=true` is rejected; there's no cross-run, per-record dedup
  beyond the duplicate-detection stage.
- **`canonical_only=false` (default)** on `GET /documents` shows the full
  corpus, including known duplicates and documents still pending stage 2/3 —
  `canonical_only=true` excludes only documents *known* to be non-canonical
  (`is_canonical IS NOT FALSE`).

## What I'd improve with more time

- **Real message queue** (Celery/RQ + Redis) instead of `BackgroundTasks` +
  DB-as-queue, removing the need for `_pipeline_lock` and enabling true
  multi-worker/multi-process scaling (see ADR 0001).
- **Postgres** in place of SQLite for production: `SELECT ... FOR UPDATE SKIP
  LOCKED` for safe concurrent batch claiming, and native full-text search.
- **FTS5 / Postgres full-text search** instead of `LIKE '%...%'` for the `q`
  filter, which currently can't use an index.
- **Configurable scoring weights** (currently hardcoded constants in
  `scoring_worker.py`) via `app/config.py`, so the formula can be tuned without
  a code change.
- **Auth / rate-limiting** on `POST /ingestions` and the `/processing/*`
  manual-drive endpoints, which are unauthenticated.
- **Pagination cursor** for `GET /documents` instead of offset-based paging,
  for stable results under concurrent ingestion.
- **Re-running stage 2/3 incrementally** when new documents join an existing
  duplicate-group title cohort currently re-touches the whole cohort every
  batch (correct, but more I/O than strictly necessary at very large scale —
  see the batching note in `docs/execution_log_sample.md`).

## Project documentation

- [`CONTEXT.md`](CONTEXT.md) — domain glossary
- [`docs/architecture_plan.md`](docs/architecture_plan.md) — original design
  plan and verified data profile
- [`docs/adr/0001-staged-db-as-queue-pipeline.md`](docs/adr/0001-staged-db-as-queue-pipeline.md)
- [`docs/adr/0002-duplicate-detection-grouping.md`](docs/adr/0002-duplicate-detection-grouping.md)
- [`docs/api_examples.md`](docs/api_examples.md) — curl examples for every endpoint
- [`docs/execution_log_sample.md`](docs/execution_log_sample.md) — real run output
- [`docs/stats_examples.md`](docs/stats_examples.md) — real `/stats` response
