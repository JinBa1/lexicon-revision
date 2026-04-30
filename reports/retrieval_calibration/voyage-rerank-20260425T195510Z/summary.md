# Retrieval Threshold Calibration Summary

- Name: `cambridge_fixture_v1_threshold_calibration`
- Collection: `cam-cs-tripos-fixture`
- Rerank: `True`
- Embedding model: `voyage-4-lite`
- Rerank model: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Positive eval passed: 12/12
- Negative queries: 20

## Score Gap

- Weakest matched positive score: `-10.0079`
- Strongest negative top score: `-9.2382`
- No clean positive/negative score gap was found.

## Positive Cases

- `broad-dynamic-programming` passed=True matched_rank=1 matched_score=-3.56696
- `broad-discrete-math` passed=True matched_rank=2 matched_score=-10.0079
- `concept-virtual-memory` passed=True matched_rank=1 matched_score=-1.43982
- `concept-relational-algebra` passed=True matched_rank=1 matched_score=4.09981
- `concept-conditional-probability` passed=True matched_rank=1 matched_score=3.12664
- `technique-induction-proofs` passed=True matched_rank=1 matched_score=2.68173
- `technique-recursion-pattern-matching` passed=True matched_rank=3 matched_score=-5.36295
- `scoped-algorithms-2024` passed=True matched_rank=1 matched_score=-4.99543
- `scoped-paper2-discrete-math` passed=True matched_rank=1 matched_score=-8.11093
- `pinpoint-databases-2025-p3` passed=True matched_rank=1 matched_score=-0.664305
- `pinpoint-graphics` passed=True matched_rank=1 matched_score=-1.57058
- `surface-code-oop` passed=True matched_rank=3 matched_score=-5.37799

## Negative Queries

- `renaissance oil painting glazing techniques` top_score=-11.0732
- `Italian personal income tax filing deadline` top_score=-11.1832
- `heart valve replacement recovery timeline` top_score=-11.2892
- `Shakespeare sonnet meter analysis` top_score=-10.4876
- `NBA playoff bracket seeding rules` top_score=-9.72334
- `sourdough starter hydration troubleshooting` top_score=-11.2659
- `quantum chromodynamics Feynman diagrams` top_score=-10.4242
- `CRISPR Cas9 off target gene editing` top_score=-11.3173
- `lithium ion battery cathode degradation` top_score=-11.1335
- `finite element mesh refinement for bridges` top_score=-9.81576
- `Kubernetes ingress controller TLS termination` top_score=-10.973
- `Rust borrow checker lifetime elision` top_score=-11.3352
- `compiler register allocation graph coloring` top_score=-9.2382
- `distributed consensus Byzantine fault tolerance` top_score=-11.0343
- `GPU shader texture sampling anisotropy` top_score=-9.53961
- `cryptocurrency proof of stake slashing` top_score=-11.1296
- `large language model RLHF reward hacking` top_score=-9.31635
- `homomorphic encryption bootstrapping circuits` top_score=-10.9575
- `florbnicate zargle tensor marmalade` top_score=-10.9405
- `ZXQ-17 blue banana protocol` top_score=-10.775
