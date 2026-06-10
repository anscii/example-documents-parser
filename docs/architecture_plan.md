# Document Intake and Review Service — Implementation Plan

## Context

Greenfield take-home project (`nitka_documents_parser`, not yet a git repo). Contains the task spec (`Nitka Task_ Document Intake and Review Service.md`) and 5 JSONL files (~11,000 records total) under `input_docs/` with deliberately noisy "climate policy document" metadata, plus `input_docs/__MACOSX/` (macOS junk, irrelevant once ingestion is upload-based).

Build a backend that ingests JSONL document data into a relational DB with a normalized schema (documents, authors, organizations, tags, ingestion runs/errors), exposes a REST API (`POST /ingestions`, `GET /documents`, `GET /documents/{id}`, `GET /stats`), and implements 3 extra processing steps (duplicate detection, scoring/ranking, document classification). Deliverables: README (run instructions, architecture, assumptions, future improvements), DB schema/migrations, sample execution log, curl examples, stats examples.

This plan was refined via a `grill-with-docs` session covering edge cases found by re-profiling `source_name`, `region`, `tags`, and title variants, plus two ADRs and a domain glossary. Per §0, the canonical copies of this plan, the ADRs, and the glossary are persisted inside the project repo under `docs/` and `CONTEXT.md` (not just `~/.claude/plans/`).

### Confirmed data profile (verified against all 11,000 lines of input_docs/*.jsonl)

- 11,000 lines → **114** are `[]` (skip, `not_object`), **331** are `{"broken": true}` (skip, `broken_stub`) → **10,555** valid records. **222** are `{}` (valid, all-null `documents` row, NOT skipped).
- `external_id`: sentinels `"duplicate-id"` (844), `""` (188), `null` (400) → "no external id" (`raw_external_id = NULL`); not unique, not an identity key.
- **41 non-null titles** (case/whitespace-insensitive), each repeated ~176–386 times; **2,186 records have null title** (singletons). Title-grouping normalization confirmed against the actual 41 titles: only 2 pairs differ by case alone (`"Climate Policy in Southern Europe"` / `"climate policy in southern europe"`, `"URBAN DEVELOPMENT STRATEGIES"` / `"Urban Development Strategies"`), no whitespace-only variants exist.
- `status`: str (mixed casing incl. PUBLISHED/Draft/unknown/""), int (0–5), bool, null.
- `document_type`: only casing variant `REPORT`/`report`; canonical `{report, working_paper, policy_brief, journal_article, news_article, press_release, dataset}`, else → `unknown`.
- `language`: full set = `{sv, pt, de, en, fr, pl, it, nl, es}` (ISO-2), `english`→`en`, `xx`/`""`/`null`→`unknown`.
- `tags`: list[str] (incl. **`[null]`**, 355 records — a single-element list containing JSON `null`) / CSV `"water,energy"` / semicolon `"energy; renewables"` / dict `{"topic":"climate"}` (319 records, always single-key) / int `123` (328 records) / null (327 records). 37 distinct list/CSV tag tokens once junk is excluded.
- `citation_count`: int / null / str `"many"` (314, only non-numeric) → null+warning, but see §4 for scoring treatment.
- `relevance_score`: float (0–1) / int / null / str `"high"` (225, only non-numeric) → null+warning, but see §4 for scoring treatment.
- `word_count`/`page_count`: int / null / numeric strings.
- `published_at`/`updated_at`: ISO date / `YYYYMMDD` int / `""` / `"invalid-date"` / null / malformed (`"2023-13-45"`).
- `author_name`/`organization_name`: string / int (coerce to str) / `null`/`""`/whitespace/`"N/A"`/`"Unknown Author"` (→ shared "Unknown" sentinel row).
- `source_name`: 9 real values (`Feed A`/`B`/`C`/`D`, `Bloomberg Green`, `Carbon Brief`, `ClimateHome`, `Reuters Environment`, `E&E News`, `EurActiv`) + 3 "no source" sentinels: `""` (794), `null` (785), and **`"unknown"`** (749, lowercase exact) → all three normalize to `NULL` (no `source_name_raw` column; see §2/§3).
- `region`: 13 real values (`Global`, `Latin America`, `Southeast Asia`, `Europe`, `East Asia`, `South Asia`, `EU`, `Southern Europe`, `North America`, `Middle East`, `Western Europe`, `Oceania`, `Sub-Saharan Africa`) + `""` (687) + `null` (672) → both sentinels normalize to `NULL`. No case/whitespace variants among the 13 real values.
- `abstract`/`body`: only `str` or `null` — no other types observed.
- `open_access`/`peer_reviewed`: bool / int 0-1 / `"yes"/"no"/"true"/"false"` / null → nullable bool.
- `version`: int / `"1.0"` / `"draft"` / `""` / null → raw string, no strict typing.
- `url`/`doi`: real values / `"not-a-url"`/`"http://"`/`"not-a-doi"`/`""`/null → raw + `_valid` bool flag.

### Architecture decisions (locked in across brainstorming + review rounds)

- **Stack**: Python 3.12 + `uv` + FastAPI + SQLAlchemy 2.0 + Alembic + SQLite (`data/app.db`, gitignored) + pytest.
- **`documents`**: ONE ROW PER VALID INGESTED RECORD (~10,555 rows from a full demo run of all 5 files), not collapsed.
- **`/stats`** = document-corpus statistics only. Ingestion run status/history is separate (`GET /ingestions`, `GET /ingestions/{run_id}`).
- All 3 processing steps required: duplicate detection, quality scoring, document_type classification.
- **No CLI ingestion trigger** — `POST /ingestions` is the only entry point, and the app is never hardcoded to a local `input_docs` path.
- **`POST /ingestions` accepts exactly ONE uploaded `.jsonl` file** (`multipart/form-data`, field `file`). The demo run = 5 separate POST calls, one per `documents_N.jsonl`.
- **Fully async pipeline, including "stage 0"**: `POST /ingestions` does the absolute minimum synchronously — read the upload, hash it, write it to a staging dir, insert an `ingestion_runs` row — then returns immediately. ALL parsing/normalization/processing happens in a background task (`BackgroundTasks`), driven by 4 "workers" each named `*_worker.py`:
  - `raw_load_worker` (stage 0): reads the staged file line-by-line, classifies each line (`invalid_json`/`not_object`/`broken_stub` → `ingestion_errors`; else → `raw_documents` row, `status='pending'`). Updates `ingestion_runs.total_lines/raw_loaded_count/skipped_count`, sets `status='processing'`.
  - `normalize_worker` (stage 1): `raw_documents.status='pending'` → normalizes all fields incl. document_type classification (per-record), upserts author/org/tags, inserts `documents` row (dedup/score fields NULL), sets `raw_documents.status='normalized'` + `normalized_at=now()`.
  - `duplicates_worker` (stage 2): `documents` where `duplicate_group_id IS NULL AND is_canonical IS NULL` → groups by **title + (author OR source)** (see §2/§3, ADR 0002).
  - `scoring_worker` (stage 3): `documents` where `quality_score IS NULL` → computes `quality_score`.
  - The nullable result columns on `documents`/`status` on `raw_documents` ARE the queue markers (ADR 0001).
- **Idempotency / re-ingestion guard**: `POST /ingestions?force=false` (default). Compute SHA-256 of the uploaded file content; if a `completed` `ingestion_runs` row already has that `file_hash` and `force` is not `true`, reject with 409 (referencing the existing run id). `force=true` bypasses the check (debug re-ingestion).
- **Single-file simplification**: `source_file` and `file_hash`/`staged_path` live on `ingestion_runs` (not duplicated per `raw_documents` row).
- **`documents` has no `ingestion_run_id`** — reachable via `documents.raw_document_id → raw_documents.ingestion_run_id`.
- **Timestamps**: `raw_documents.normalized_at` (set when promoted to a `documents` row) + `documents.created_at` (set at insert) together capture "when normalization happened".
- **Startup resume**: on FastAPI startup, find any `ingestion_runs` with `status NOT IN ('completed','failed')` and re-launch their background processing (each worker is idempotent/queue-driven — `status='queued'` → still need stage 0; `status='processing'` → stage 0 done, just resume draining stages 1-3). Additionally, always run a "drain queues" pass at startup to mop up any global leftovers from a prior unclean shutdown.

---

## 0. Documentation Artifacts (grill-with-docs deliverables)

To be written to the project repo once this plan is approved (in addition to the build-order code):

- **`CONTEXT.md`** (project root) — domain glossary, single-context repo. Terms (each with a 1-2 sentence definition + "avoid" aliases):
  - **Ingestion Run**: one `POST /ingestions` upload + its full background processing lifecycle (stages 0-3) for one `.jsonl` file. *Avoid*: job, task, import.
  - **Raw Record**: a structurally-valid JSON object from an ingestion run's source file, stored verbatim in `raw_documents.raw_data`, before normalization.
  - **Document**: a normalized record in `documents`, derived 1:1 from a Raw Record (stage 1). *Avoid*: "record" alone (ambiguous with Raw Record).
  - **Duplicate Group**: a set of Documents sharing a normalized title and connected via shared author or source_name (stage 2 connected component).
  - **Canonical Document**: the single representative Document within a Duplicate Group (earliest publish date → most complete → lowest id). Singletons are always canonical.
  - **Quality Score**: a derived 0-100 score per Document (stage 3) combining citation percentile, relevance, recency, and completeness signals.
  - **Unknown (sentinel)**: a shared placeholder `authors`/`organizations` row (`normalized_name="__unknown__"`) used when the source author/organization name is missing or junk.
  - **Normalization Warning**: a non-fatal note on a Document when a raw field's value couldn't be cleanly interpreted (e.g., `citation_count: "many"`).
  - **Ingestion Error**: a raw line that couldn't be processed at all (invalid JSON / not an object / `{"broken": true}`) — never becomes a Raw Record.
  - Include a short example dialogue demonstrating Raw Record → Document → Duplicate Group/Canonical Document → Quality Score flow.

- **`docs/adr/0001-staged-db-as-queue-pipeline.md`**:
  > *Context*: The task wants a "queue + workers" processing pipeline (raw-load → normalize → dedup → score), but adding Celery/Redis/RQ is heavy infrastructure for a 1-day SQLite-based take-home.
  > *Decision*: Use SQLite tables/columns as the queue. `raw_documents.status` (`pending`/`normalized`) and nullable result columns on `documents` (`duplicate_group_id`/`is_canonical`/`quality_score`) act as queue markers. Each "worker" is a `process_batch()` pulling `WHERE <marker> IS NULL`. `POST /ingestions` schedules `run_pipeline()` via FastAPI `BackgroundTasks`; a startup hook resumes incomplete runs and drains all queues.
  > *Why*: Demonstrates the queue/worker separation the task asks for, with zero extra infrastructure — at the cost of single-process-only execution (no row-locking across concurrent workers, no at-least-once delivery guarantees). A production version would swap in Celery/RQ + Postgres `SELECT ... FOR UPDATE SKIP LOCKED`.

- **`docs/adr/0002-duplicate-detection-grouping.md`**:
  > *Context*: This is a synthetic dataset — ~41 titles each repeat 176-386 times, with author/org/source/doi/url independently randomized within each title cohort, simulating "different sites republishing the same underlying document" (e.g., an EU climate report mirrored by multiple national government sites).
  > *Decision*: Two documents are duplicates iff they share a `normalized_title` AND (same non-Unknown `author_id` OR same non-empty `source_name`). Connected components within each title cohort form duplicate groups; canonical pick = earliest `published_at` → most-complete record → lowest `id`. Organization/language/region agreement only contribute to a `duplicate_confidence` score (0.5-1.0) — they don't create grouping edges by themselves.
  > *Why*: Title alone over-groups (376 unrelated-looking records under one title). Title+organization would under-group the "EU report mirrored by different national sites" scenario, since organization legitimately differs there. Author-or-source as the secondary signal balances precision/recall — and profiling found 0 shared DOIs and no near-identical body text across the corpus, so there's no stronger content-based signal available.
  > *Consequences*: Two records sharing a title but with completely disjoint author+source (and disjoint org/language/region) are treated as coincidentally-same-titled distinct documents, NOT duplicates — a deliberate false-negative tradeoff, documented in the README as an assumption.

- **`docs/architecture_plan.md`** — the canonical project-local copy of this plan (Build Order §8 step 1 should copy/adapt this file into the repo early, then keep it as a static historical record — no need to keep it in sync with code afterwards).

---

## 1. Project Structure

```
nitka_documents_parser/
├── pyproject.toml
├── .gitignore              # data/, .venv/, __pycache__, *.db, logs/
├── README.md
├── CONTEXT.md               # domain glossary (see §0)
├── alembic.ini
├── data/
│   ├── .gitkeep            # sqlite db lives here (gitignored)
│   └── uploads/.gitkeep    # staged uploaded files (gitignored)
├── logs/.gitkeep
├── docs/
│   ├── architecture_plan.md
│   ├── adr/{0001-staged-db-as-queue-pipeline.md,0002-duplicate-detection-grouping.md}
│   └── {execution_log_sample.md,api_examples.md,stats_examples.md}
├── alembic/{env.py, versions/0001_initial_schema.py}
├── app/
│   ├── main.py              # FastAPI app factory + startup resume hook
│   ├── config.py            # pydantic-settings: db url, log dir, upload dir, default batch size
│   ├── db/{base.py,session.py}   # session.py: get_db() (request-scoped) + SessionLocal (background tasks)
│   ├── models/{author.py,organization.py,tag.py,raw_document.py,document.py,ingestion.py}
│   ├── schemas/{document.py,ingestion.py,processing.py,stats.py,common.py}
│   ├── ingestion/
│   │   ├── file_io.py            # save upload to staging dir, sha256 hashing, line iteration over staged file
│   │   ├── record_validator.py   # stage-0 skip logic ([], {"broken":true}, invalid JSON)
│   │   └── normalizers/
│   │       ├── text.py | dates.py | identity.py | tags.py | language.py
│   │       ├── status.py | document_type.py | numbers.py | booleans.py | links.py
│   ├── processing/
│   │   ├── raw_load_worker.py    # stage 0: staged file -> raw_documents + ingestion_errors
│   │   ├── normalize_worker.py   # stage 1: raw_documents -> documents
│   │   ├── duplicates_worker.py  # stage 2: title+(author|source) grouping, canonical pick, confidence
│   │   └── scoring_worker.py     # stage 3: quality_score
│   ├── services/
│   │   ├── ingestion_service.py  # orchestration: run_pipeline(run_id) chaining all 4 workers + logging
│   │   ├── document_service.py   # list/detail/filter queries
│   │   └── stats_service.py
│   └── api/
│       ├── deps.py
│       └── routers/{ingestions.py,processing.py,documents.py,stats.py}
└── tests/
    ├── conftest.py
    ├── unit/  (one module per normalizer + duplicates_worker + scoring_worker + record_validator)
    ├── integration/ (staged pipeline + API tests against small fixture JSONL files)
    └── fixtures/sample_input/*.jsonl
```

`pyproject.toml` deps: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `pydantic`, `pydantic-settings`, `python-dateutil`, `python-multipart`. Dev: `pytest`, `pytest-cov`, `httpx`, `ruff`. Use `uv init`, `uv add ...`, `uv run ...`.

---

## 2. Database Schema (SQLAlchemy models, single Alembic migration `0001_initial_schema.py`)

**`authors`** / **`organizations`**: `id`, `name`, `normalized_name` (unique-indexed dedup key), `created_at`. Each seeded with one `"Unknown"` sentinel row (`normalized_name="__unknown__"`) via migration data step. Junk values (`null`/`""`/whitespace/`"N/A"`/`"Unknown Author"`) → Unknown sentinel; ints coerce to string and are treated as real names.

**`tags`**: `id`, `name` (unique, lowercase/trimmed). **`document_tags`**: association table (`document_id`, `tag_id`, `ondelete="CASCADE"`).

**`ingestion_runs`**: `id`, `source_file` (str), `file_hash` (str, indexed), `staged_path` (str), `started_at`, `finished_at`, `status` (`queued`|`processing`|`completed`|`failed`, indexed), `total_lines`, `raw_loaded_count`, `skipped_count`, `error_message`.

**`ingestion_errors`**: `id`, `run_id` FK, `line_number`, `raw_line` (truncated 2000 chars), `error_category` (`invalid_json`|`not_object`|`broken_stub`), `error_detail`. Only the ~445 hard-skips per file go here.

**`raw_documents`** (stage-1 queue): `id`, `ingestion_run_id` FK (indexed), `line_number`, `raw_data` (JSON — structurally-valid parsed record, incl. `{}`), `status` (`pending`|`normalized`, indexed), `created_at`, `normalized_at` (nullable).

**`documents`** (~10,555 rows after a full demo):
- Provenance: `id`, `raw_document_id` FK (unique, indexed), `raw_external_id` (nullable, indexed, NOT unique).
- Text: `title`, `normalized_title` (lower/trim/collapse-whitespace, indexed), `abstract`, `body`.
- Dates: `published_at` (Date, indexed) + `published_at_raw`, `updated_at` + `updated_at_raw`.
- Relations: `source_name` (nullable str — `""`/`null`/`"unknown"` case-insensitive all normalize to `NULL`; no `source_name_raw` column), `author_id` FK, `organization_id` FK.
- Taxonomy: `language`+`language_raw`, `status` (indexed)+`status_raw`, `document_type` (indexed)+`document_type_raw`, `region` (indexed, nullable — `""`/`null` → `NULL`, the 13 real values pass through unchanged).
- Links: `url`+`url_valid`, `doi`+`doi_valid`.
- Metrics: `citation_count`, `word_count`, `page_count` (int, nullable), `relevance_score` (float, nullable), `version` (raw string). No `citation_count_raw`/`relevance_score_raw` columns — `scoring_worker` reads the original raw values from `raw_documents.raw_data` when needed (see §3 stage 3, §4).
- Booleans: `open_access`+`open_access_raw`, `peer_reviewed`+`peer_reviewed_raw`.
- **Queue markers**: `duplicate_group_id` (nullable int, indexed), `is_canonical` (nullable bool), `duplicate_confidence` (nullable float) — all-NULL = pending stage 2; `quality_score` (nullable float, indexed) — NULL = pending stage 3.
- `normalization_warnings` (JSON list[str], nullable), `created_at`.
- Relationships: `author`, `organization`, `tags`, `raw_document`.
- Indexes: composite `(normalized_title, duplicate_group_id)`, composite `(status, document_type)`. Free-text search via `LIKE` on title/abstract/body.

---

## 3. Staged Pipeline ("DB as queue", 4 workers, all run in background)

### `POST /ingestions` (sync part — fast)

`app/api/routers/ingestions.py` + `ingestion_service.create_run(db, file: UploadFile, force: bool)`:
1. `content = await file.read()`; `file_hash = sha256(content).hexdigest()`.
2. If not `force`: look up `ingestion_runs` where `file_hash==X AND status=='completed'` → if found, raise `409` with the existing run id.
3. Insert `ingestion_runs(source_file=file.filename, file_hash=X, status='queued')` → get `id`.
4. Write `content` to `data/uploads/{id}.jsonl`, set `staged_path`, commit.
5. `background_tasks.add_task(run_pipeline, run_id=id)`.
6. Return `IngestionRunSummary(id, status='queued', source_file, file_hash)`.

### `app/services/ingestion_service.run_pipeline(run_id)` (background, owns its `SessionLocal()`)

```python
run = get_run(db, run_id)
if run.status == 'queued':
    raw_load_worker.process_run(db, run)   # stage 0: staged file -> raw_documents + ingestion_errors; status='processing'
drain(normalize_worker)    # loop process_batch() until remaining==0
drain(duplicates_worker)
drain(scoring_worker)
run.status = 'completed'; run.finished_at = now()
```
Each `drain(worker)` = `while True: processed, remaining = worker.process_batch(db, BATCH_SIZE); log; if remaining == 0: break`. On any unhandled exception, set `run.status='failed'`, `error_message=str(e)`, log, re-raise (logged, not re-raised across the background-task boundary).

### Stage 0 — `processing/raw_load_worker.py`

`process_run(db, run)`: stream `run.staged_path` line-by-line via `ingestion/file_io.iter_staged_lines(path)`. Per line, `record_validator.classify(line)`: (1) `json.loads` fails → `ingestion_errors(invalid_json)`; (2) not a dict (`[]`) → `not_object`; (3) `parsed == {"broken": True}` → `broken_stub`; (4) else (incl. `{}`) → `raw_documents(status='pending', raw_data=parsed, line_number=...)`. Update `run.total_lines/raw_loaded_count/skipped_count`, `status='processing'`, commit.

### Stage 1 — `processing/normalize_worker.py`

`process_batch(db, batch_size) -> (processed, remaining)`: `SELECT * FROM raw_documents WHERE status='pending' ORDER BY id LIMIT batch_size`. Per row: run all normalizer modules over `raw_data` (each returns `(value, raw_or_None, warning_or_None)`, never raises), classify `document_type`, `upsert_author`/`upsert_organization`/`upsert_tags` (in-memory `{normalized_key: id}` caches), insert `documents` row (`raw_document_id` FK; dedup/score fields NULL), set `raw_documents.status='normalized', normalized_at=now()`. Commit. `remaining = count(raw_documents.status='pending')`.

**Normalizer modules** (one per field-group):
- `text.py`: `normalize_text()` (title/abstract/body/region — non-str→None+warning, `""`→None) + `normalize_title_for_grouping(title) = re.sub(r'\s+', ' ', title.strip()).lower()` (lowercase + strip + collapse internal whitespace).
- `dates.py`: `normalize_date()` — ISO str, `YYYYMMDD` int, `""`, `"invalid-date"`, malformed (`"2023-13-45"`), null → `(date|None, raw_str, warning|None)` via `date.fromisoformat` then `dateutil.parser` fallback.
- `identity.py`: `normalize_external_id()` (`"duplicate-id"`/`""`/null→None, int→str); `normalize_person_or_org_name()` (null/`""`/whitespace/`"n/a"`/`"unknown author"`→None→Unknown sentinel; int→str; else trimmed); `normalize_source_name()` (`null`/`""`/`"unknown"` case-insensitive → `None`; int→str; else trimmed — no `_raw` retained, since the raw value is recoverable from `raw_documents.raw_data`).
- `tags.py`: `normalize_tags()` — list→[str], filtering out `null`/non-string elements first (e.g. `[null]`→`[]`, `["energy", null]`→`["energy"]`) with a warning logged whenever an element was filtered; CSV/semicolon string→split; dict→`list(values())`; int/other→`[]`+warning; null→`[]`. Deduped, lowercase, sorted.
- `language.py`: `ISO2={sv,pt,de,en,fr,pl,it,nl,es}`, `FULL_NAME={"english":"en"}`, `xx`/`""`/null→`"unknown"`.
- `status.py`: canonical `{draft,published,archived,unknown}`. str case-insensitive match on the 4 names (else `unknown`); `bool True→published, False→draft`; `int 0→draft,1→published,2→archived,3/4/5→unknown`; `null→unknown`. `status_raw=repr(original)`.
- `document_type.py`: case-insensitive match against 7 canonical types, else `unknown`; `document_type_raw`=original.
- `numbers.py`: `coerce_int()`/`coerce_float()` — numeric strings coerce; `"many"`/`"high"`/other non-numeric→`None`+warning (note: the "many"/"high" sentinels are still recoverable later from `raw_documents.raw_data` for scoring — see stage 3). `normalize_version()`→`str(value)` or `None`.
- `booleans.py`: `coerce_nullable_bool()` — bool passthrough; int 0/1; `"yes"/"no"/"true"/"false"` case-insensitive; else `None`.
- `links.py`: `normalize_url()`/`normalize_doi()` — raw trimmed (`""→None`), `_valid` via `urllib.parse` (scheme+netloc) / DOI regex `^10\.\d{4,9}/\S+$`.

### Stage 2 — `processing/duplicates_worker.py` — **grouping key = title + (author OR source)** (ADR 0002)

`process_batch(db, batch_size) -> (processed, remaining)`: `SELECT * FROM documents WHERE duplicate_group_id IS NULL AND is_canonical IS NULL ORDER BY id LIMIT batch_size`.
- Pending doc with blank/null `normalized_title` → `is_canonical=True`, `duplicate_group_id=NULL`, `duplicate_confidence=NULL` (singleton, done).
- Otherwise, collect the **distinct non-blank `normalized_title` values** present in this batch. For each such title `T`, fetch the **full title cohort** = `SELECT id, author_id, organization_id, source_name, language, region, duplicate_group_id, is_canonical FROM documents WHERE normalized_title = T` (global, not just this batch).
  - Build an undirected graph over the cohort: edge `i—j` iff (`author_id_i == author_id_j` AND both ≠ Unknown sentinel) **OR** (`source_name_i == source_name_j`, both non-NULL — `source_name` is already normalized so `""`/`"unknown"` never appear here). (Org/language/region agreement does NOT create an edge — title+author/source is the grouping key per ADR 0002; org/language/region only feed `duplicate_confidence`.)
  - Connected components = duplicate groups. Component size 1 → `is_canonical=True`, `duplicate_group_id=NULL`, `duplicate_confidence=NULL`. Component size >1 → `duplicate_group_id = MIN(id)` over the component (recompute/overwrite for ALL component members, including previously-processed ones whose component just grew/merged); recompute `is_canonical` via canonical-pick rule (below) across the component; recompute `duplicate_confidence` per member = `0.5` (title match, baseline) `+ 0.25` if it shares `author_id` with ≥1 other component member `+ 0.25` if it shares `source_name` with ≥1 other member `+ 0.1` each (cap total at `1.0`) for `organization_id`/`language`/`region` agreement with ≥1 other member.
- `processed = len(batch)`; `remaining = count(documents WHERE duplicate_group_id IS NULL AND is_canonical IS NULL)`.

**Canonical pick** within a component: (1) earliest non-null `published_at`; (2) tiebreak by completeness = count of non-null among `{abstract, body, doi, url, author_id≠Unknown, organization_id≠Unknown, region, citation_count, word_count, page_count}`; (3) final tiebreak lowest `id`.

### Stage 3 — `processing/scoring_worker.py`

`process_batch(db, batch_size) -> (processed, remaining)`:
- Pre-pass: `SELECT citation_count FROM documents WHERE citation_count IS NOT NULL ORDER BY citation_count` → sorted array `cc_sorted` for `bisect`-based percentile, plus `p90_value = cc_sorted[int(0.9 * (len(cc_sorted)-1))]` (90th-percentile citation count, used for the `"many"` sentinel — see §4).
- `SELECT documents.*, raw_documents.raw_data FROM documents JOIN raw_documents ON documents.raw_document_id = raw_documents.id WHERE documents.quality_score IS NULL ORDER BY documents.id LIMIT batch_size` (eager-load `raw_document` so the `"many"`/`"high"` sentinel checks below have access to the original raw value without extra columns on `documents`).
- Compute `quality_score` per §4, update. `remaining = count(quality_score IS NULL)`.

### Logging

Python `logging` → stdout + `logs/ingestion_run_{run_id}.log`. INFO for stage start/end + batch progress; WARNING mirrors `normalization_warnings`; ERROR mirrors `ingestion_errors`. Basis for `docs/execution_log_sample.md`.

### Startup resume (`app/main.py` lifespan)

On startup: `for run in ingestion_runs where status NOT IN ('completed','failed'): background_tasks-equivalent → run_pipeline(run.id)` (or just call synchronously at startup since it's typically fast/empty in dev). Then unconditionally run one `drain()` pass over normalize/duplicates/scoring to mop up any global leftovers. All workers are idempotent/queue-driven so this is safe to call even when nothing is pending (returns immediately).

---

## 4. `quality_score` Formula (0–100, in `processing/scoring_worker.py`)

```
# citation component: use citation_count if present; if citation_count is NULL but
# raw_data["citation_count"] == "many" (case-insensitive), treat as p90_value (~0.9 percentile)
citation_value_for_percentile =
    citation_count                                   if citation_count is not None
    else p90_value                                   if raw_data.get("citation_count") == "many" (ci)
    else None  -> contributes 0

# relevance component: use relevance_score if present; if NULL but
# raw_data["relevance_score"] == "high" (case-insensitive), treat as 0.9
relevance_value =
    relevance_score                                  if relevance_score is not None
    else 0.9                                         if raw_data.get("relevance_score") == "high" (ci)
    else 0

quality_score =
    25 * citation_percentile(citation_value_for_percentile)   # percentile rank among non-null citation_count values; None -> 0
  + 20 * relevance_value                                       # 0-1 scale
  + 20 * exp(-max(0, age_years) / 5)           # recency decay, half-life ~3.5y; future-dated -> age=0 -> max bonus
  + 15 * (1 if peer_reviewed is True else 0)
  + 10 * (1 if open_access is True else 0)
  + 5  * (1 if word_count else 0)
  + 5  * (1 if page_count else 0)
# clamp [0,100], round 2dp
```

Note: `documents.citation_count`/`relevance_score` themselves remain `NULL` for "many"/"high" records (they genuinely have no parseable numeric value) — only the `quality_score` *computation* substitutes the percentile/0.9 stand-in, sourced live from `raw_documents.raw_data`.

---

## 5. API Layer

- **`POST /ingestions?force=false`** (`multipart/form-data`, field `file`, single `.jsonl`) — see §3. Returns `IngestionRunSummary` (`id`, `status="queued"`, `source_file`, `file_hash`). `409` if already ingested (same hash, `status='completed'`) and `force` is false.
- **`GET /ingestions?limit=&offset=`** — paginated run history, newest first.
- **`GET /ingestions/{run_id}`** — run detail: `status`, `total_lines`, `raw_loaded_count`, `skipped_count`, per-run progress (`normalize_pending`, `dedup_pending`, `scoring_pending` — computed via `documents JOIN raw_documents WHERE raw_documents.ingestion_run_id=run_id AND ...`), `error_count`, `sample_errors` (first 20 `ingestion_errors`).
- **`POST /processing/normalize?batch_size=500`**, **`POST /processing/duplicates?batch_size=500`**, **`POST /processing/scoring?batch_size=500`** — manually drive one batch of a stage (global queues); return `{processed, remaining}`.
- **`GET /documents`** — pagination (`page` default `1`, `page_size` default `20`, max `100`) + filters: `published_after`/`published_before`, `tag`, `organization`, `status`, `document_type`, `language`, `region`, `q` (LIKE over title/abstract/body), `canonical_only` (default `false` — `is_canonical IS NOT FALSE`, i.e. true OR pending; when `false`, no filter is applied so the full corpus is shown), `min_quality_score`, `sort_by`∈{`id`(default),`published_at`,`quality_score`,`created_at`}, `sort_dir`∈{`asc`(default),`desc`}. Returns `Page[DocumentSummary]`.
- **`GET /documents/{id}`** — `DocumentDetail`: `author`, `organization`, `tags`, `duplicate_group` (`group_id`,`group_size`,`is_canonical`,`confidence`, possibly null if stage2 pending), `quality_score` (possibly null if stage3 pending), `document_type`/`_raw`, `normalization_warnings`. 404 if missing.
- **`GET /stats`** — `total_documents`, `by_status`, `by_document_type`, `by_region` (all 13 real values + `unknown`/null bucket, sorted by count desc — no top-N truncation given the small cardinality), `by_language`, `top_tags` (all ~36 distinct tags, sorted by count desc), `duplicate_stats` (`total_groups`,`total_duplicates`,`avg_group_size`,`top_groups`: top 10 largest groups, each `{group_id, size, canonical_document_id, normalized_title}`), `quality_score_distribution` (`min/max/mean/median/p25/p75` + 10 fixed-width histogram buckets of 10 points over `[0,100]`, non-null only).

`app/db/session.py`: engine + `SessionLocal` + `get_db()`; background tasks use `SessionLocal()` directly. `app/config.py`: `database_url="sqlite:///./data/app.db"`, `log_dir="logs"`, `upload_dir="data/uploads"`, `default_batch_size=500` — no input-path config.

---

## 6. Testing Strategy

- **Unit** (`tests/unit/`, no DB): table-driven tests per normalizer covering every messy-value category from the data profile, including the new edge cases — `source_name` `""`/`null`/`"unknown"`(any case)→`NULL`; `region` `""`/`null`→`NULL`; `tags: [null]`→`[]`+warning and `["energy", null]`→`["energy"]`+warning; `normalize_title_for_grouping` on the two case-variant title pairs. Also `record_validator` (`[]`/`{"broken":true}`/`{}`/malformed JSON); `duplicates_worker` (cohort graph: author-only edge, source-only edge, both, neither → singleton; component merge when a bridging doc arrives; canonical pick; confidence formula incl. cap at 1.0; Unknown-author/null-source never create edges); `scoring_worker` (each component incl. future-date clamping, plus the `"many"`→p90 and `"high"`→0.9 substitutions via a fake `raw_data`).
- **Integration** (`tests/integration/`): temp SQLite + Alembic-migrated schema + `TestClient` with `get_db` override; background tasks executed synchronously in tests (call `run_pipeline`/worker functions directly rather than relying on `BackgroundTasks` timing). `test_staged_pipeline.py` POSTs a ~20-50 line fixture `.jsonl` (covering every messy case incl. `source_name="unknown"`, `tags: [null]`, `region: ""` + a crafted title+author duplicate group + a crafted title+source duplicate group + a same-title-different-author/source non-duplicate pair), drives all stages to completion, asserts row counts/categories/dedup/score fields. `test_api_*.py` cover all routers incl. every `/documents` filter, pagination defaults, `canonical_only` default behavior, 404, `/stats` shape/sum-consistency, `POST /ingestions` 409-on-duplicate + `force=true` bypass.
- Optional `@pytest.mark.slow` test uploading each of the real `input_docs/*.jsonl` files and driving all stages, asserting headline numbers (10,555 normalized docs total, 41 title-based cohorts, etc.) — also useful for generating the execution log deliverable.

---

## 7. Deliverables

- **README.md**: overview; architecture (staged DB-as-queue pipeline, 4 background workers, startup resume, idempotency-by-hash — link to `docs/adr/0001-*`); how to run (`uv sync`, `uv run alembic upgrade head`, `uv run uvicorn app.main:app --reload`, then for each file: `curl -F "file=@input_docs/documents_1.jsonl" localhost:8000/ingestions`, poll `GET /ingestions/{id}` until `completed`); schema/ER overview; links to `CONTEXT.md`, `docs/adr/`, `docs/api_examples.md` / `docs/execution_log_sample.md` / `docs/stats_examples.md`; **assumptions** (every normalization/mapping decision incl. `source_name`/`region`/`tags` sentinel handling, dedup grouping = title+(author|source) with confidence formula — link `docs/adr/0002-*`, "Unknown" sentinel, scoring weights incl. "many"/"high" substitutions, global vs per-run queue semantics, idempotency-by-hash, `canonical_only` default); **what I'd improve** (FTS5 search, real message queue instead of BackgroundTasks, Postgres notes, configurable scoring weights, auth/rate-limiting).
- **`CONTEXT.md`**: domain glossary (see §0).
- **`docs/adr/0001-staged-db-as-queue-pipeline.md`**, **`docs/adr/0002-duplicate-detection-grouping.md`**: see §0.
- **`docs/architecture_plan.md`**: this plan.
- **`docs/execution_log_sample.md`**: real run output (per-file stage0 counts + skip categories, per-stage batch progress, final summary) from actual `POST /ingestions` calls for all 5 files.
- **`docs/api_examples.md`**: curl examples for every endpoint + filter + the multipart upload + the 409/force flow.
- **`docs/stats_examples.md`**: real `/stats` JSON from the real run.

---

## 8. Build Order (~1 day)

1. Setup: `uv init`, deps, skeleton, `.gitignore`, config/db base, write `CONTEXT.md` + `docs/adr/000{1,2}-*.md` + `docs/architecture_plan.md` (~45min)
2. Models + Alembic migration (incl. `raw_documents`, Unknown sentinel seeding); `alembic upgrade head` (~45min)
3. Normalizers + unit tests (~2h)
4. `raw_load_worker` + `POST /ingestions` (upload, hash/force, staging, background scheduling) (~1h)
5. `normalize_worker` (~1h)
6. `duplicates_worker` (title+author/source graph) (~1.25h)
7. `scoring_worker` (~45min)
8. `ingestion_service.run_pipeline` orchestration + `GET /ingestions`/`{id}` + `/processing/*` endpoints + startup resume (~45min)
9. `documents`/`stats` routers (~1h)
10. Real run: 5x curl upload, capture logs + stats (~30min)
11. Integration tests (~1h)
12. README + remaining docs + ruff polish (~45min)

---

## Verification

- `uv run pytest` — all unit + integration tests pass.
- `uv run alembic upgrade head` then `sqlite3 data/app.db .schema`.
- Start server, for `f in documents_1..5.jsonl: curl -F "file=@input_docs/$f" localhost:8000/ingestions`, poll `GET /ingestions/{id}` until `completed` for each. Then verify:
  - Sum of `raw_loaded_count` across the 5 runs = 10555; sum of `skipped_count` = 445.
  - Re-POSTing the same file without `force` → 409; with `force=true` → new run accepted.
  - `GET /stats` internally consistent (`sum(by_status.values()) == total_documents`, etc.); `by_region`/`top_tags` show all real values with no spurious `"unknown"` source/`"none"` tag entries.
  - `GET /documents` (default, no params) total count == `total_documents` (canonical_only defaults to false); filters/pagination sane; `GET /documents/{id}` for a duplicate-group member shows `duplicate_group`, `quality_score`, `document_type`.
  - `POST /processing/normalize|duplicates|scoring` return `processed=0, remaining=0` once drained.
- Capture into `docs/execution_log_sample.md` and `docs/stats_examples.md`.

### Critical files
- `CONTEXT.md`, `docs/adr/0001-staged-db-as-queue-pipeline.md`, `docs/adr/0002-duplicate-detection-grouping.md`, `docs/architecture_plan.md`
- `app/models/{document,raw_document,author,organization,tag,ingestion}.py`
- `app/ingestion/normalizers/*.py`, `app/ingestion/{file_io,record_validator}.py`
- `app/processing/{raw_load_worker,normalize_worker,duplicates_worker,scoring_worker}.py`
- `app/services/ingestion_service.py`
- `alembic/versions/0001_initial_schema.py`
- `app/api/routers/{ingestions,processing,documents,stats}.py`
