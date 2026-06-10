# Document Intake and Review Service

A backend service that ingests noisy JSONL document metadata into a relational database, normalizes it, and exposes a REST API for querying documents and corpus-wide statistics.

## Language

**Ingestion Run**:
One `POST /ingestions` upload and its full background processing lifecycle (raw-load, normalize, dedup, score) for a single `.jsonl` file.
_Avoid_: job, task, import.

**Raw Record**:
A structurally-valid JSON object read from an Ingestion Run's source file, stored verbatim in `raw_documents.raw_data` before any normalization.
_Avoid_: raw document (use "Raw Record" to distinguish from "Document").

**Document**:
A normalized record in the `documents` table, derived 1:1 from a Raw Record during the normalize stage.
_Avoid_: record (ambiguous with Raw Record).

**Duplicate Group**:
A set of Documents that share a normalized title and are connected by a shared author or shared `source_name` (a connected component computed during the dedup stage).

**Canonical Document**:
The single representative Document within a Duplicate Group, chosen by earliest publish date, then completeness, then lowest id. A Document with no Duplicate Group is always canonical.

**Quality Score**:
A derived 0-100 score computed for each Document during the scoring stage, combining citation percentile, relevance, recency, and metadata completeness.

**Unknown (sentinel)**:
A shared placeholder row in `authors` or `organizations` (`normalized_name="__unknown__"`) used when the source author or organization name is missing or junk (null, empty, "N/A", "Unknown Author", etc.).

**Normalization Warning**:
A non-fatal note attached to a Document when one of its raw field values could not be cleanly interpreted (e.g. `citation_count: "many"`).

**Ingestion Error**:
A raw line from an Ingestion Run's source file that could not be processed at all (invalid JSON, not a JSON object, or the `{"broken": true}` stub). Never becomes a Raw Record.

## Example dialogue

> **Dev**: The dashboard shows 10,555 Documents but the source files only have ~10,333 "real-looking" records — what gives?
>
> **Domain expert**: Right — 222 of the source lines were empty objects (`{}`). Those are still valid Raw Records, so each becomes a Document with every field null. They're not Ingestion Errors; those are reserved for lines that couldn't even be parsed as a JSON object — `[]`, `{"broken": true}`, or invalid JSON.
>
> **Dev**: Why does `/documents/42` show a `duplicate_group` but `is_canonical: false`?
>
> **Domain expert**: Document 42 shares its normalized title and author with at least one other Document — together they form a Duplicate Group. The Canonical Document in that group is whichever one was published earliest (or most complete, if publish dates tie). Document 42 just wasn't picked.
>
> **Dev**: Some documents have `quality_score: null` right after I upload a file — is that a bug?
>
> **Domain expert**: No — that's normal mid-pipeline. By the time an Ingestion Run reaches `status: completed`, every Document from that run has been through the scoring stage and has a non-null Quality Score.
