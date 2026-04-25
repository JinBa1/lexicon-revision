# Retrieval Abstention Thresholds

## Current MVP Policy

The MVP uses collection-scoped final-score thresholds to avoid returning the
least-bad top-k result when a query is outside the collection.

For the Cambridge fixture, the calibrated value is collection DB state:

```text
collection=cam-cs-tripos-fixture
RERANK_ENABLED=true
RERANK_PROVIDER=voyage
RERANK_MODEL=rerank-2.5-lite
collections.retrieval_rerank_min_score=0.498
collections.retrieval_vector_min_score=NULL
```

This value was calibrated against
`docs/evals/calibration_runs/voyage-rerank-20260425T200235Z/`:

- positive Cambridge fixture eval passed: 12/12
- weakest matched positive Voyage rerank score: `0.542969`
- strongest negative-query top score: `0.453125`
- midpoint candidate: `0.498`

## How The Threshold Works

`PgSearchService` always retrieves vector candidates first. If rerank is
requested and a reranker is configured, it reranks those candidates and treats
the reranker score as the final score.

The service then applies the collection threshold for the score source that was
actually used:

- `collections.retrieval_rerank_min_score` when rerank actually ran
- `collections.retrieval_vector_min_score` when rerank did not run
- no threshold when the relevant collection column is `NULL`

Results are kept only when:

```text
score >= configured_min_score
```

When the relevant collection column is `NULL`, all retrieved results are kept.
If a configured threshold removes all results, `/search` returns an empty
result list. `/study` uses the same search service, so thresholded empty
retrieval follows the existing `insufficient_evidence` path.

## Limitations

The threshold is a temporary MVP guardrail, not the final retrieval-quality
system.

The calibrated `0.498` value is specific to:

- Voyage `rerank-2.5-lite`
- the current chunking/indexing shape
- the Cambridge fixture calibration set
- the negative query set in the calibration run

Do not treat `0.498` as a universal semantic boundary. A different reranker,
embedding model, chunking strategy, or materially different corpus can shift
the useful cutoff.

The threshold cannot fix candidate-generation failures. If vector retrieval
does not include a relevant chunk in the candidate pool, reranking and
thresholding cannot recover it.

## New Collections

Do not require full calibration before every new collection. The operational
default for a new collection is no abstention threshold: leave both
`collections.retrieval_vector_min_score` and
`collections.retrieval_rerank_min_score` as `NULL` until that collection has
been calibrated. After calibration, update only that collection row.

Do a quick smoke check for important curated collections before enabling a
threshold.

A quick smoke check should include:

- 3-5 known-good positive queries, if available
- 3-5 obvious negative queries
- at least one nearby-but-out-of-collection query when the subject has close
  neighboring topics

For high-value shared corpora, use a larger calibration set:

- 10-20 positive queries across topics and years
- 10-20 negative queries spanning unrelated, adjacent-domain, and nonsense
  prompts

## Calibration Command

Run from a normal network-enabled shell:

```bash
RUN_DIR="docs/evals/calibration_runs/voyage-rerank-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"

set -a; source .env; set +a
export RERANK_ENABLED=true
export RERANK_PROVIDER=voyage
export RERANK_MODEL=rerank-2.5-lite

python scripts/calibrate_retrieval_threshold.py \
  docs/evals/cambridge_fixture_v1.yaml \
  --rerank \
  --expect-rerank-model-id rerank-2.5-lite \
  --output-dir "$RUN_DIR" \
  2>&1 | tee "$RUN_DIR/run.log"
```

The runner writes:

- `calibration_raw.json` for full score data; this file is ignored and not
  tracked
- `summary.md` for the positive/negative score gap and suggested threshold
- `run.log` when invoked with `tee` as shown above

After choosing a threshold, apply it to the calibrated collection row. Do not
move it into global runtime environment.

## Post-MVP Direction

Replace this single-threshold guardrail with a broader retrieval-quality
program: negative-query evals, hybrid sparse+dense retrieval, query-level score
features, relative score gaps, collection-level monitoring, and learned or
statistical abstention policies.
