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
`$7.00` authorization. H002 and H003 each reached the provider boundary once but produced no
response or ledger event. Both remain sealed technical failures and neither is ever retried or
replaced. The immutable H002 continuation stays byte-for-byte unchanged. A committed recovery
declaration and append-only continuation entry bind each later zero-event item's intent, outcome,
exact reconstructed provider request, projection, prior continuation hash, and new descendant
recovery commit. Reconciliation is an explicit offline command after each failure; an unreserved
zero-event outcome stops before any later call.

H002 reserves `$0.399575000`; H003's exact offline projection reserves `$0.398156250` (22,297
serialized request bytes plus the fixed 32,768-token upper-bound overhead, 55,065 input-token upper
bound, and 1,800 maximum output tokens). Their cumulative `$0.797731250` reserve lowers the dynamic
tracked ceiling to `$6.202268750`. A future ambiguity requires another committed declaration and
no-overwrite chain entry; cumulative reserve plus recorded spend must stay within `$7.00`. Each
provider boundary has no SDK retry. Private questions, answers, dossiers, rubrics, and response metadata remain below
`runtime/evaluations/retrieval-authored-v3-professional-2026-08-13`.

## Commands

```powershell
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py preflight
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py dev-decompose --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py freeze
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py reconcile-ambiguity
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py generate --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py decompose --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py rubric --authorize-openai --max-total-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_persona_evaluation.py prepare
.venv\Scripts\python.exe scripts\run_persona_evaluation.py run --authorize-live-persona-evaluation --max-cost-usd 7.00
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py report
```

Run `reconcile-ambiguity` again after any later exact zero-event stop, from the newly committed
recovery harness, before resuming `generate`. The command discovers the first unreconciled item and
never accepts or retries an arbitrary failure.

The final report distinguishes local retrieval time from the authored-response boundary, reports
generated successes and Essential fallbacks separately, and includes retrieval coverage, citation
syntax/resolvability, citation completeness over valid decompositions, mechanical cited-chunk/gold
location overlap, exploratory gold-claim coverage, every per-item ambiguity reserve, cumulative
reserve, dynamic effective ceiling, recorded-plus-reserved worst-case accounting, and operation
counts.
