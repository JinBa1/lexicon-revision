# Retrieval Threshold Calibration Notes - 2026-04-25

## Purpose

Calibrate the MVP retrieval abstention thresholds for the Cambridge fixture,
with emphasis on the deployed Voyage reranker path. The goal is to preserve
known-good retrieval while suppressing out-of-collection nearest-neighbor
matches.

## Runtime Under Test

- Positive eval: `docs/evals/cambridge_fixture_v1.yaml`
- Collection: `cam-cs-tripos-fixture`
- Reranker target: Voyage `rerank-2.5-lite`
- Threshold under calibration: `RETRIEVAL_RERANK_MIN_SCORE`
- Calibration rule: keep results with `score >= threshold`

## Negative Query Set

The negative set intentionally spans unrelated everyday topics, non-CS
technical topics, nearby-but-out-of-fixture CS topics, and nonsensical queries.

1. `renaissance oil painting glazing techniques`
2. `Italian personal income tax filing deadline`
3. `heart valve replacement recovery timeline`
4. `Shakespeare sonnet meter analysis`
5. `NBA playoff bracket seeding rules`
6. `sourdough starter hydration troubleshooting`
7. `quantum chromodynamics Feynman diagrams`
8. `CRISPR Cas9 off target gene editing`
9. `lithium ion battery cathode degradation`
10. `finite element mesh refinement for bridges`
11. `Kubernetes ingress controller TLS termination`
12. `Rust borrow checker lifetime elision`
13. `compiler register allocation graph coloring`
14. `distributed consensus Byzantine fault tolerance`
15. `GPU shader texture sampling anisotropy`
16. `cryptocurrency proof of stake slashing`
17. `large language model RLHF reward hacking`
18. `homomorphic encryption bootstrapping circuits`
19. `florbnicate zargle tensor marmalade`
20. `ZXQ-17 blue banana protocol`

## Planned Request Count

- Positive fixture eval: 12 rerank requests.
- Negative queries: 20 rerank requests.
- Optional follow-up spot checks: up to 5 rerank requests.
- Expected total: about 32-37 Voyage rerank requests.

## Observations

- 2026-04-25T19:39:57Z: Started calibration attempt from Codex sandbox.
- Positive eval command attempted:
  `RERANK_ENABLED=true RERANK_PROVIDER=voyage RERANK_MODEL=rerank-2.5-lite conda run -n rag-exam python scripts/evaluate_search.py docs/evals/cambridge_fixture_v1.yaml --rerank --format json --output /tmp/rag_exam_voyage_positive_raw.json`
- Result: blocked by sandbox network/DNS before calibration data collection.
  The failure occurred while resolving the configured Neon Postgres host
  `ep-divine-snow-ab7bzpui-pooler.eu-west-2.aws.neon.tech`, before query
  embedding or reranking.
- Expected Voyage requests sent by this failed attempt: 0. The search path
  loads the collection schema before embedding or reranking, and the database
  connection failed at that schema lookup step.
- No positive or negative score distributions were collected in this sandbox.
- 2026-04-25T19:42:04Z: Retried the positive eval from the same sandbox with
  output path `/tmp/rag_exam_voyage_positive_raw_retry.json`.
- Retry result: same blocker. DNS resolution for the configured Neon Postgres
  host failed before collection schema lookup completed.
- Expected Voyage requests sent by the retry: 0.
- User-run calibration at
  `docs/evals/calibration_runs/voyage-rerank-20260425T195510Z/` completed, but
  it is not a Voyage rerank calibration. The generated summary reports
  rerank model `cross-encoder/ms-marco-MiniLM-L-6-v2`, so it used the local
  CrossEncoder default. Treat those scores as local-reranker observations only.
- Local-reranker observation from that run: positive eval passed 12/12, but
  no clean positive/negative score gap was found. Weakest matched positive
  score was `-10.0079`; strongest negative top score was `-9.2382`.
- User-run calibration at
  `docs/evals/calibration_runs/voyage-rerank-20260425T200235Z/` is the valid
  Voyage `rerank-2.5-lite` calibration run.
- Voyage observation from that run: positive eval passed 12/12, weakest
  matched positive score was `0.542969`, strongest negative top score was
  `0.453125`, and the midpoint candidate threshold was `0.498`.
- MVP Fly deployment pins `RETRIEVAL_RERANK_MIN_SCORE=0.498` for Voyage
  `rerank-2.5-lite`. This is a temporary MVP guardrail, not a universal score
  boundary.

## Calibration Procedure To Run Outside The Sandbox

### Packaged Runner

Run this from a normal shell with network access:

```bash
set -a; source .env; set +a
export RERANK_ENABLED=true
export RERANK_PROVIDER=voyage
export RERANK_MODEL=rerank-2.5-lite
conda run -n rag-exam python scripts/calibrate_retrieval_threshold.py \
  docs/evals/cambridge_fixture_v1.yaml \
  --rerank \
  --expect-rerank-model-id rerank-2.5-lite \
  --output-dir docs/evals/calibration_runs/voyage-rerank-2026-04-25
```

The runner disables existing retrieval thresholds while collecting raw scores,
then writes:

- `calibration_raw.json`: full positive and negative result payloads.
- `summary.md`: score gap, candidate threshold, and per-query observations.

### Manual Equivalent

1. Collect positive scores:

   ```bash
   set -a; source .env; set +a
   export RERANK_ENABLED=true
   export RERANK_PROVIDER=voyage
   export RERANK_MODEL=rerank-2.5-lite
   conda run -n rag-exam python scripts/evaluate_search.py \
     docs/evals/cambridge_fixture_v1.yaml \
     --rerank \
     --format json \
     --output /tmp/rag_exam_voyage_positive_raw.json
   ```

2. For each negative query above, run:

   ```bash
   set -a; source .env; set +a
   export RERANK_ENABLED=true
   export RERANK_PROVIDER=voyage
   export RERANK_MODEL=rerank-2.5-lite
   conda run -n rag-exam python scripts/inspect_search.py \
     "<negative query>" \
     --collection cam-cs-tripos-fixture \
     --limit 10 \
     --rerank \
     --format json
   ```

3. Choose a candidate `RETRIEVAL_RERANK_MIN_SCORE` that is:
   - lower than the weakest required matched positive result score;
   - higher than the strongest unacceptable negative result score;
   - rounded down with margin rather than set exactly at an observed score.

4. Verify the candidate:

   ```bash
   set -a; source .env; set +a
   export RETRIEVAL_RERANK_MIN_SCORE=<candidate>
   export RERANK_ENABLED=true
   export RERANK_PROVIDER=voyage
   export RERANK_MODEL=rerank-2.5-lite
   conda run -n rag-exam python scripts/evaluate_search.py \
     docs/evals/cambridge_fixture_v1.yaml \
     --rerank \
     --format text
   ```
