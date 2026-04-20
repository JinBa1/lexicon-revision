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
      - field: paper
        op: eq
        value: 1
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

`cases[].filters` is a schema-driven `FilterCondition` list. Use any metadata
field exposed by the target collection schema; the tooling preserves authored
conditions in order and does not hard-code field names.

Each filter entry has:

- `field`: collection metadata field key
- `op`: `eq`, `gte`, or `lte`
- `value`: string, integer, or boolean scalar

Repeat the same field when you need ranges or compound constraints.

Canonical example:

```yaml
cases:
  - id: algorithms-year-filter
    query: binary search trees
    filters:
      - field: year
        op: eq
        value: 2024
      - field: has_code
        op: eq
        value: false
    expected:
      any_chunk_ids:
        - cam-2024-p2-q5
      top_k: 5
```

## Pass Criteria

A case passes if any expected chunk ID or expected topic appears within `top_k`
returned results.
