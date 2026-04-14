# Cambridge Fixture V1 Search Eval Report

## Summary

`cambridge_fixture_v1` passed all authored retrieval cases against the
`cam-cs-tripos-fixture` Chroma collection.

The fixture covers Cambridge CS Tripos 2023-2025, Papers 1-3, using
`data/eval_fixtures/cambridge_2023_2025_p1_p3/`. The indexed collection
contains 87 question-level chunks, 329 sub-question chunks, and 416 total
Chroma documents.

## Results

| Mode | Cases | Passed | Hit@1 | Hit@3 | Hit@5 | Hit@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No rerank | 12 | 12 | 12 | 12 | 12 | 12 |
| Rerank | 12 | 12 | 10 | 12 | 12 | 12 |

The no-rerank run matched an expected chunk or topic at rank 1 for every case.
The rerank spot check still passed every case within its configured `top_k`;
two cases moved below rank 1 but remained within the passing window.

## Case Coverage

- Broad topic recall: dynamic programming/algorithms, discrete mathematics.
- Concept recall: virtual memory paging, relational algebra joins and schemas,
  conditional probability for geometric waiting times.
- Technique recall: induction proofs, recursive functions and pattern matching.
- Metadata filters: 2024 algorithms by year, Paper 2 discrete mathematics by
  paper.
- Pinpoint retrieval: 2025 Paper 3 Databases and Graphics questions.
- Surface feature filtering: OOP code-bearing chunks via `has_code`.

## Notes

- `surface-code-oop` is included because inspected OOP chunks with
  `has_code=true` contain visible Java code-like text.
- `concept-relational-normalisation` was replaced with
  `concept-relational-algebra` because normalisation was not visibly present in
  inspected fixture text.
- The machine-readable no-rerank report is
  `reports/search_eval/cambridge_fixture_v1.json`.
