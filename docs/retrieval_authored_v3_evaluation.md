# Retrieval-authored v3 evaluation

This is a new descriptive cohort for the committed `retrieval-authored-v3` Professional reader.
It reuses the unchanged 37-question locked benchmark after the earlier V26 evaluation, so it is a
reused locked benchmark—not a pristine blind holdout and not a formal before/after claim.

The product under test is commit `4e9d6ed01a7ed1d92f2124aefc07c3259675f1ad`. The separately
committed harness identity is recorded in the private cohort manifest. Frozen V26 answers,
decompositions, ledgers, gold annotations, and production artifacts are read-only.

## Fixed sequence

1. Validate all locked inputs, the 481-chunk index, and all 37 cached
   `text-embedding-3-small` vectors offline.
2. Exercise the new exact-text-anchor decomposition instrument once on G001–G010. These archived
   development answers are instrument-development material, not v3 quality evidence.
3. Freeze the instrument only if all ten outcomes validate.
4. Generate one Professional answer for every H item with cached retrieval and exactly one
   no-retry `gpt-5.6-sol` authoring attempt. No query-embedding request is made.
5. Make one no-retry canonical `gpt-5.6-terra` decomposition attempt for every preserved answer.
6. Only after all 37 generation and decomposition outcomes are sealed, run the item-rubric judge.
   Its gold-claim results are explicitly exploratory and uncalibrated.
7. Run the separate four-item social suite documented in [persona_evaluation.md](persona_evaluation.md).
8. Produce a public-safe summary after every required outcome exists.

All paid phases share one ignored `usage.sqlite3`, one request ID, and the owner's cumulative
`$7.00` hard ceiling. Each provider boundary has no SDK retry. An item with ambiguous or unpriced
usage stops all later calls; it is never replayed or replaced. Private questions, answers, dossiers,
rubrics, and response metadata remain below
`runtime/evaluations/retrieval-authored-v3-professional-2026-08-13`.

## Commands

```powershell
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py preflight
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py dev-decompose --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py freeze
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py generate --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py decompose --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py rubric --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_persona_evaluation.py prepare
.venv\Scripts\python.exe scripts\run_persona_evaluation.py run --authorize-live-persona-evaluation --max-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py report
```

The final report distinguishes local retrieval time from the authored-response boundary, reports
generated successes and Essential fallbacks separately, and includes retrieval coverage, citation
syntax/resolvability, citation completeness over valid decompositions, mechanical cited-chunk/gold
location overlap, exploratory gold-claim coverage, exact recorded spend, and operation counts.
