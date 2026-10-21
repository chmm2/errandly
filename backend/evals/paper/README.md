# Paper experiments

Everything in Section VI of `docs/paper/ieee/main.tex` comes from the scripts in
this folder. They import the production modules (`app.modules.*`, `app.workers.*`)
unchanged. Only storage is replaced:

- database sessions are swapped for small fake sessions that hand back prepared
  rows, the same trick `tests/test_policy_excess.py` already uses;
- graph queries run against a **separate, throwaway Neo4j**, never the dev graph.
  `neo.assert_throwaway()` refuses to run unless `NEO4J_URL` contains `paper`,
  because the experiments delete every node between trials.

The decision logic, constants and Cypher are the deployed ones. If a constant or a
query changes, rerun the scripts and the numbers move with it, which is the point.

## Setup (once)

```bash
docker compose up -d db redis mongo
docker run -d --name errandly-paper-neo4j --network project_1_default \
  -e NEO4J_AUTH=neo4j/errandly-dev -e NEO4J_server_memory_heap_max__size=1G \
  neo4j:5.26-community
```

The collusion runs are long, so the paper's numbers were produced with up to five
such instances (`errandly-paper-neo4j`, `-2` to `-5`) running parts in parallel.
Each process needs its own instance, because a trial wipes the graph.

Run any experiment in a one-off backend container (from the repository root). The
results folder is `paper-artifacts/results` at the repository root, outside the
`backend` mount, so mount it into the container at `/paper-artifacts`:

```bash
docker compose run --rm --no-deps -T \
  -v "$(pwd)/paper-artifacts:/paper-artifacts" \
  -e PAPER_GIT_COMMIT=$(git rev-parse --short HEAD) \
  -e NEO4J_URL=bolt://errandly-paper-neo4j:7687 -e REDIS_URL=redis://redis:6379/1 \
  -e LLM_PROVIDER= -e ANTHROPIC_API_KEY= \
  backend python -m evals.paper.exp2_collusion main routine,busy
```

Results land in `paper-artifacts/results/*.json` with the commit given in
`PAPER_GIT_COMMIT`, the Python version, the CPU, core count and memory the
container saw, and a timestamp. `export_datasets.py` writes the CSV datasets to
`paper-artifacts/datasets/`; see `paper-artifacts/README.md`. Then draw the figures
on the host (PDFs for the paper, PNG copies into `paper-artifacts/figures/`):

```bash
python docs/paper/ieee/figures/make_figures.py
```

## Which script produces what

| Script | Paper | What it measures | Seeds | Neo4j |
|---|---|---|---|---|
| `exp1_closure.py` | Table V | closure vs clustering coefficient on canonical shapes, scored by the production `REFRESH_METRICS` Cypher | deterministic | yes |
| `exp2_collusion.py main <regimes>` | Tables IV, VI; Fig. 7 | ten detectors in five behavioural regimes on a 1,200-student campus; run as `main routine,busy` and `main favours,coordinated,hard` | 30 | yes |
| `exp2_collusion.py sweeps <part>` | Figs. 8, 9 | `explore` (exploration rate), `weight_favours` (trust weight, honest favours), `intensity_adaptive` (farming intensity, adaptive coordinated rings) | 10 | yes |
| `exp3_reference.py` | Tables VII, VIII; Fig. 10 | seven reference estimators under four attacker strategies; money paid and days to first flag | 30 | no |
| `exp4_store.py` | Table IX | shop-level pooling: honest dear shops, colluders at a cheap shop, cold start | deterministic | no |
| `exp5_farming.py` | Fig. 11 | rating farming against `build_profile` and `farming_signals` | deterministic | no |
| `exp6_dispatch.py` | Table X | broadcast, staged (fixed and original scheduler) and one-at-a-time dispatch on the same semesters | 30 | no |
| `exp7_escrow.py` | Fig. 12 | escrow headroom: freeze rate vs money locked, under two price models | 30 (frontier 10) | no |
| `exp8_scale.py` | Table XI | SCC routine to 10^6 nodes; graph jobs and trust lookup to 10,000 students; acceptance-model fit; five repetitions each | 5 repetitions | yes |
| `exp9_normalize.py` | Sec. VI-E | item-name normalisation, and 61 adversarial names against the old and the deployed claim binding | deterministic | no |
| `../run_eval.py --repeats 5` | Sec. VI-H | the two language channels on the eleven synthetic cases (needs Ollama with `qwen2.5:7b`) | 5 repeats | no |

Run the timing experiment (`exp8`) alone, with nothing else on the machine, or its
numbers measure contention instead of the pipeline.

The test-suite figure comes from:

```bash
docker compose run --rm --no-deps -e NEO4J_URL=bolt://errandly-paper-neo4j:7687 \
  -e REDIS_URL=redis://redis:6379/1 -e LLM_PROVIDER= backend python -m pytest tests/ -q
```

## Detectors in `exp2`

- `structure_closure`, `structure_clustering`, `money_circulation`,
  `structure_and_money`: one kind of evidence each, at the production knees.
- `payment_cycles_any`: the ring search's leg rule and SCC search without the
  friendship requirement.
- `fraudar_payments`: FRAUDAR-style greedy peeling on the payment graph. Its own
  densest block is the whole marketplace on these graphs (recorded as
  `fraudar_block_size`), so it is scored as a ranking cut at the true number of
  ring members, an advantage no deployment would have.
- `lpa_money`: label-propagation communities on the friend graph ranked by the
  share of value that stays inside; also cut at the true number of ring members.
  `lpa_flagged_above_knee` records what the production knee would flag.
- `find_rings`: production `fraud.collusion.find_rings`.
- `find_rings_policy`: plus the policy test using the router's logged scores (the
  original rule).
- `find_rings_policy_fitted`: plus the policy test using
  `policy.fit_acceptance_model` on every round not posted by a ring suspect (the
  deployed rule).

## What these numbers are, and are not

- **Synthetic.** No student has used the platform yet. The campus is a stochastic
  block model and runner behaviour (willingness, response delay, friend affinity)
  is assumed. The sweeps exist because those assumptions matter.
- **Checked against production.** `campus.py` computes closure and circulation
  itself to drive dispatch; every trial compares both against the production
  Cypher on the final graph and stores the largest difference
  (`check_max_diff_*` in `exp2_*.json`). In every trial so far it is 0.
- **Not an accuracy result for the language model.** `run_eval.py` says so on
  every run: the eleven cases were written by us.
- **Seeded.** Every experiment is deterministic given its seed, except timings.
  Intervals are 95% t-based confidence intervals of the mean across seeds
  (`common.ci95`).
