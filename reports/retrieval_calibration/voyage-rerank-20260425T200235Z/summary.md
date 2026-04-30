# Retrieval Threshold Calibration Summary

- Name: `cambridge_fixture_v1_threshold_calibration`
- Collection: `cam-cs-tripos-fixture`
- Rerank: `True`
- Embedding model: `voyage-4-lite`
- Rerank model: `rerank-2.5-lite`
- Positive eval passed: 12/12
- Negative queries: 20

## Score Gap

- Weakest matched positive score: `0.542969`
- Strongest negative top score: `0.453125`
- Suggested collection `retrieval_rerank_min_score`: `0.498`

## Positive Cases

- `broad-dynamic-programming` passed=True matched_rank=1 matched_score=0.570312
- `broad-discrete-math` passed=True matched_rank=1 matched_score=0.628906
- `concept-virtual-memory` passed=True matched_rank=1 matched_score=0.605469
- `concept-relational-algebra` passed=True matched_rank=1 matched_score=0.746094
- `concept-conditional-probability` passed=True matched_rank=1 matched_score=0.792969
- `technique-induction-proofs` passed=True matched_rank=1 matched_score=0.601562
- `technique-recursion-pattern-matching` passed=True matched_rank=1 matched_score=0.542969
- `scoped-algorithms-2024` passed=True matched_rank=1 matched_score=0.597656
- `scoped-paper2-discrete-math` passed=True matched_rank=1 matched_score=0.570312
- `pinpoint-databases-2025-p3` passed=True matched_rank=1 matched_score=0.617188
- `pinpoint-graphics` passed=True matched_rank=1 matched_score=0.617188
- `surface-code-oop` passed=True matched_rank=1 matched_score=0.5625

## Negative Queries

- `renaissance oil painting glazing techniques` top_score=0.320312
- `Italian personal income tax filing deadline` top_score=0.349609
- `heart valve replacement recovery timeline` top_score=0.439453
- `Shakespeare sonnet meter analysis` top_score=0.328125
- `NBA playoff bracket seeding rules` top_score=0.453125
- `sourdough starter hydration troubleshooting` top_score=0.285156
- `quantum chromodynamics Feynman diagrams` top_score=0.365234
- `CRISPR Cas9 off target gene editing` top_score=0.390625
- `lithium ion battery cathode degradation` top_score=0.333984
- `finite element mesh refinement for bridges` top_score=0.386719
- `Kubernetes ingress controller TLS termination` top_score=0.349609
- `Rust borrow checker lifetime elision` top_score=0.326172
- `compiler register allocation graph coloring` top_score=0.429688
- `distributed consensus Byzantine fault tolerance` top_score=0.378906
- `GPU shader texture sampling anisotropy` top_score=0.429688
- `cryptocurrency proof of stake slashing` top_score=0.318359
- `large language model RLHF reward hacking` top_score=0.330078
- `homomorphic encryption bootstrapping circuits` top_score=0.419922
- `florbnicate zargle tensor marmalade` top_score=0.287109
- `ZXQ-17 blue banana protocol` top_score=0.414062
