# `/stats` examples

Real `GET /stats` response captured after ingesting all five `input_docs/documents_*.jsonl`
files (10,333 documents total — see [`execution_log_sample.md`](./execution_log_sample.md)
for the run that produced this state).

```bash
curl -s http://localhost:8000/stats | python3 -m json.tool
```

```json
{
    "total_documents": 10333,
    "by_status": {
        "draft": 4046,
        "unknown": 3038,
        "published": 2204,
        "archived": 1045
    },
    "by_document_type": {
        "unknown": 2800,
        "report": 1972,
        "dataset": 985,
        "working_paper": 937,
        "journal_article": 922,
        "news_article": 913,
        "press_release": 903,
        "policy_brief": 901
    },
    "by_region": {
        "unknown": 1359,
        "Global": 754,
        "Latin America": 721,
        "Southeast Asia": 711,
        "Europe": 705,
        "East Asia": 704,
        "South Asia": 701,
        "EU": 697,
        "Southern Europe": 691,
        "North America": 687,
        "Middle East": 661,
        "Western Europe": 657,
        "Oceania": 656,
        "Sub-Saharan Africa": 629
    },
    "by_language": {
        "unknown": 2472,
        "en": 1608,
        "de": 809,
        "it": 807,
        "es": 800,
        "fr": 776,
        "sv": 771,
        "pt": 771,
        "nl": 764,
        "pl": 755
    },
    "top_tags": {
        "climate": 1702,
        "energy": 1621,
        "water": 1323,
        "policy": 1105,
        "urban": 970,
        "renewables": 662,
        "plastics": 384,
        "marine": 384,
        "ccs": 356,
        "carbon-capture": 356,
        "europe": 349,
        "groundwater": 345,
        "planning": 335,
        "heat": 335,
        "food-security": 335,
        "ecosystems": 335,
        "biodiversity": 335,
        "agriculture": 335,
        "infrastructure": 334,
        "green-bonds": 332,
        "finance": 332,
        "fossil-fuels": 328,
        "transport": 327,
        "ev": 327,
        "decarbonisation": 327,
        "oceans": 325,
        "acidification": 325,
        "resources": 320,
        "nuclear": 308,
        "low-carbon": 308,
        "hydrogen": 308,
        "fuel-cells": 308,
        "wildfire": 306,
        "land-management": 306,
        "methane": 293,
        "livestock": 293
    },
    "duplicate_stats": {
        "total_groups": 48,
        "total_duplicates": 8066,
        "avg_group_size": 168.04,
        "top_groups": [
            {
                "group_id": 8,
                "size": 374,
                "canonical_document_id": 674,
                "normalized_title": "urban development strategies"
            },
            {
                "group_id": 2,
                "size": 367,
                "canonical_document_id": 3272,
                "normalized_title": "climate policy in southern europe"
            },
            {
                "group_id": 1,
                "size": 206,
                "canonical_document_id": 8352,
                "normalized_title": "energy market trends 2023"
            },
            {
                "group_id": 30,
                "size": 204,
                "canonical_document_id": 6926,
                "normalized_title": "green finance instruments 2022"
            },
            {
                "group_id": 79,
                "size": 202,
                "canonical_document_id": 2629,
                "normalized_title": "solar power adoption barriers"
            },
            {
                "group_id": 13,
                "size": 201,
                "canonical_document_id": 8274,
                "normalized_title": "permafrost thaw: tipping points"
            },
            {
                "group_id": 33,
                "size": 201,
                "canonical_document_id": 5012,
                "normalized_title": "methane emissions from livestock"
            },
            {
                "group_id": 3,
                "size": 200,
                "canonical_document_id": 3556,
                "normalized_title": "urban heat island mitigation"
            },
            {
                "group_id": 63,
                "size": 200,
                "canonical_document_id": 2111,
                "normalized_title": "ai applications in climate modelling"
            },
            {
                "group_id": 66,
                "size": 199,
                "canonical_document_id": 7657,
                "normalized_title": "renewable energy transition in the eu"
            }
        ]
    },
    "quality_score_distribution": {
        "min": 0.0,
        "max": 100.0,
        "mean": 50.78,
        "median": 49.66,
        "p25": 39.01,
        "p75": 60.62,
        "histogram": [145, 168, 719, 1767, 2452, 2365, 1504, 596, 161, 456]
    }
}
```

## Notes on these numbers

- `by_region` has 14 entries: the 13 real region values from the source data plus `"unknown"`
  for documents whose `region` was `null`/`""` (sentinel collapse, see `CONTEXT.md`).
- `by_language` has 10 entries: the 9 ISO-2 codes present in the corpus plus `"unknown"` for
  `null`/`""`/`"xx"` values.
- `by_document_type` includes an `"unknown"` bucket for values that don't match one of the
  7 canonical document types (see `docs/adr/0002-duplicate-detection-grouping.md` for how
  `document_type` is classified).
- `duplicate_stats.total_groups` (48) is higher than the 41 distinct titles in the corpus
  because a handful of title cohorts split into more than one connected component — i.e.
  documents sharing a title but with no shared `author`/`source_name` linking them to the
  rest of the cohort form their own smaller duplicate group(s) (per ADR 0002's grouping rule).
- `quality_score_distribution.histogram` is 10 buckets of width 10 over `[0, 100]`; the
  buckets sum to `10333`, matching `total_documents` (every document has a `quality_score`
  once stage 3 has fully drained).
