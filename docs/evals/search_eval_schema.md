# Search Eval Schema

Search eval files are human-authored YAML files used by
`scripts/evaluate_search.py`.

These files are seed quality checks, not final product benchmarks. They are
intended to catch obviously poor retrieval before LLM answer generation is
built on top.

## Shape

```yaml
name: cambridge_fixture_seed
description: Human-authored seed eval for fixture-backed search sanity checks.
collection: cam-cs-tripos
default_top_k: 5

cases:
  - id: binary-search-tree-practice
    query: practice questions about binary search trees and lookup complexity
    filters:
      paper: 1
    expected:
      any_chunk_ids:
        - cam-2025-p1-q1
      any_topics:
        - Algorithms
      top_k: 5
    notes: Should retrieve questions involving search trees or algorithmic lookup.
```

## Required Fields

- `name`: eval set name.
- `cases`: list of eval cases.
- `cases[].id`: stable case ID.
- `cases[].query`: user-style search query.
- `cases[].expected`: expected retrieval behavior.

Each case must provide at least one of:

- `expected.any_chunk_ids`
- `expected.any_topics`

## Optional Fields

- `description`
- `collection`
- `default_top_k`
- `cases[].filters`
- `cases[].expected.top_k`
- `cases[].notes`

Supported filters are:

- `year`
- `paper`
- `topic`
- `question`
- `question_number`
- `marks_min`
- `has_code`
- `has_figure`
- `has_table`

`question` is the preferred human-facing spelling. It is normalized to
`question_number` before running search. Do not provide both in the same case.

## Pass Criteria

A case passes if any expected chunk ID or expected topic appears within `top_k`
returned results.
