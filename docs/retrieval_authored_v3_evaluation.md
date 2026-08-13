# Retrieval-authored v3 evaluation

This is the terminal historical timeout-diagnostic cohort for the committed
`retrieval-authored-v3` Professional reader. It reuses the unchanged 37-question locked benchmark
after the earlier V26 evaluation, so it is a reused locked benchmark—not a pristine blind holdout
and not a formal before/after claim. Do not resume it or use it as evidence about current
`retrieval-authored-v4`.

The product under test is commit `4e9d6ed01a7ed1d92f2124aefc07c3259675f1ad`. The separately
committed harness identity is recorded in the private cohort manifest. Frozen V26 answers,
decompositions, ledgers, gold annotations, and production artifacts are read-only.

## Original fixed sequence

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

The owner stopped this run after H014 decomposition. It is therefore retained as a timeout-
diagnostic cohort, not resumed as a quality cohort. Generation completed with 37 once-only
attempts: 30 authored answers and seven Essential fallbacks. Decomposition ended after 14
attempts; rubric and persona scoring never started. Tracked spend was `$1.591521500`. H014
reconciliation and `close-diagnostic` performed zero provider operations, did not retry H014, and
wrote an answer-free partial summary plus immutable closure artifact. The closure permanently
blocks all later paid phases, freezes, and ambiguity reconciliations for this run root.
The separate legacy persona runner shares that v3 root and ledger; it now detects the closure
artifact and fails before provider-client construction. The v4 adapter's isolated social phase is
the only current evaluator for Professional, Princess, Baron, and Red Realist conversation.

All paid phases share one ignored `usage.sqlite3`, one request ID, and the owner's cumulative
`$7.00` authorization. Generation turns H002, H003, H021, H025, H026, H027, and H031, followed by
H001's, H012's, H013's, and H014's held-out decomposition turns, each reached the provider boundary once but produced no response
or ledger event. All remain sealed technical failures and none is ever retried or
replaced. The immutable H002 continuation stays byte-for-byte unchanged. A committed recovery
declaration and append-only continuation entry bind each later zero-event item's intent, outcome,
exact reconstructed provider request, projection, prior continuation hash, and new descendant
recovery commit. Reconciliation is an explicit offline command after each failure; an unreserved
zero-event outcome stops before any later call.

H002 reserves `$0.399575000`; H003's exact offline projection reserves `$0.398156250` (22,297
serialized request bytes plus the fixed 32,768-token upper-bound overhead, 55,065 input-token upper
bound, and 1,800 maximum output tokens). H021's exact offline projection reserves `$0.392612500`
(21,410 serialized request bytes, 54,178 input-token upper bound, and 1,800 maximum output tokens).
H025's exact offline projection reserves `$0.405556250` (23,481 serialized request bytes, 56,249
input-token upper bound, and 1,800 maximum output tokens). H026's projection reserves `$0.405881250`
(23,533 serialized request bytes, 56,301 input-token upper bound, and 1,800 maximum output tokens).
H027's projection reserves `$0.390450000` (21,064 serialized request bytes, 53,832 input-token upper
bound, and 1,800 maximum output tokens). H031's projection reserves `$0.406400000` (23,616 serialized
request bytes, 56,384 input-token upper bound, and 1,800 maximum output tokens). H001's Terra
decomposition projection reserves `$0.175984375` (4,347 serialized request bytes, 37,115 input-token
upper bound, and 4,000 maximum output tokens). H012's decomposition projection reserves
`$0.180178125` (5,689 serialized request bytes, 38,457 input-token upper bound, and 4,000 maximum
output tokens). H013's decomposition projection reserves `$0.179390625` (5,437 serialized request
bytes, 38,205 input-token upper bound, and 4,000 maximum output tokens). H014's decomposition
projection reserves `$0.176209375` (4,419 serialized request bytes, 37,187 input-token upper bound,
and 4,000 maximum output tokens). Their cumulative `$3.510393750` reserve lowers the dynamic
tracked ceiling to `$3.489606250`.
Before diagnostic closure, a future ambiguity requires another committed declaration and
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

For the stopped diagnostic run, the terminal provider-free sequence replaces all unfinished paid
commands:

```powershell
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py reconcile-ambiguity
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py close-diagnostic
.venv\Scripts\python.exe scripts\run_retrieval_authored_v3_evaluation.py report
```

Run the reconciliation only from the clean committed harness containing the exact H014 declaration.
Verify that it seals `H014:decomposition`; then run `close-diagnostic`. After closure, the v3 run is
terminal and must not be used as the root for the replacement evaluation.
`close-diagnostic` may run from a clean descendant of the reconciled H014 tail so a narrowly scoped
closure correction can be committed without fabricating another ambiguity. This descendant allowance
exists only for terminal closure: paid phases retain exact continuation binding, reconciliation keeps
its separate append-only contract, and an unrelated or non-descendant harness is rejected. The
closure records the exact closing commit. Once closed, `report` validates and reads the sealed
diagnostic artifacts directly, without reopening the evaluation.

Run `reconcile-ambiguity` again after an exact zero-event stop in generation, decomposition, or
rubric, from the newly committed recovery harness, before resuming that phase. The command discovers
the first unreconciled provider turn and never accepts or retries an arbitrary failure.

The complete report would distinguish local retrieval time from the authored-response boundary, reports
generated successes and Essential fallbacks separately, and includes retrieval coverage, citation
syntax/resolvability, citation completeness over valid decompositions, mechanical cited-chunk/gold
location overlap, exploratory gold-claim coverage, every phase/operation ambiguity reserve, cumulative
reserve, dynamic effective ceiling, recorded-plus-reserved worst-case accounting, and operation
counts.

The diagnostic partial report exposes the completed generation/retrieval/citation/latency metrics,
the available schema-valid decomposition citation completeness, and recorded-plus-reserved cost. It
explicitly reports gold-claim coverage and social behavior as not run; it contains no questions,
answers, manuscript excerpts, or provider response metadata.
