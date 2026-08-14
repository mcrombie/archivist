# Archivist, Measured: What 37 Unseen Questions Revealed

*The citations held together. Retrieval was incomplete. The evaluator broke. And the problem users could feel immediately—latency—led to a measurable redesign.*

My last post introduced the Archivist project ([link to previous post]). I said the next update would be less about what Archivist could display than what it could prove after a detailed evaluation.

Since then, I have spent a good deal of time building and running that evaluation. It turns out that evaluating a retrieval-augmented generation system rigorously may be harder than building the first working version of the system itself.

This is the big, boring part: quality assurance. I now understand why this is where enthusiasm for RAG often dies. [Manish Prasad's explanation of why teams skip RAG evaluation](https://medium.com/@manisuec/how-to-evaluate-a-rag-system-and-why-most-teams-dont-2abb9eec2f5f) captures the problem well. Retrieval and generation can each fail in different ways, and a polished answer can conceal both.

The first problem was not the model. It was the test.

## Writing an evaluation I could not tune against

Initially, I tested Archivist with ten questions. That set exposed real defects, but it gradually became part of the development process. Once I had inspected those results and changed Archivist in response to them, the questions could no longer tell me how the system would perform on something it had not already encountered. They had become a development set.

To see what I was missing, I froze the current version of Archivist and created a new set of 37 questions. Thirty-three could be answered from the manuscript. Four could not.

The questions included focused questions about people and events, analytical and conceptual questions, broad questions spanning large portions of the book, questions with questionable premises, and out-of-corpus questions for which the correct behavior was to decline. I deliberately kept some questions compound, vague, or partially mistaken. Real users do not rewrite their questions into the form an application would prefer to answer.

For each question, I reviewed the claims a good answer should contain and the manuscript locations that could support them. Some of those fields grew out of earlier annotation work, but nothing counted merely because another model proposed it: I checked the accepted labels against the manuscript I wrote.

That took considerably more effort than I expected. It also forced me to decide what I meant by a good answer before I saw the model's prose.

I drew a firm line before running the test. Every reported result would either be mechanical—did a citation resolve, did a chunk appear in retrieval, did a response pass its schema—or measured against source locations I had verified.

No automatic judge verdict would count as answer correctness until the judge had been calibrated against my labels. It also had to use a different model from the answer generator and satisfy the project's independence rules.

Until then, the semantic fields would remain empty. That is why this post can tell you whether a citation resolved, but not yet how often the cited passage actually entailed the claim beside it.

The first use of these 37 questions was genuinely held out for the frozen version. Once I inspected those results and continued development, the questions stopped being pristine. Later runs use the same *fixed benchmark*, but I do not call those later runs held out.

## What the first run found

The frozen retrieval diagnostic and the frozen answer-quality baseline were separate measurements of the same version. In each, the labels and rules were fixed before the questions ran. No failed answer was quietly replaced with a better rerun.

The clearest pattern was that Archivist usually found *something* relevant, but rarely found *everything* the answer needed.

### Retrieval on the 33 answerable questions

| Metric | Dense retrieval | Hybrid retrieval |
| --- | ---: | ---: |
| Recall@5 | 24.71% | 25.97% |
| Hit@5 | 90.91% | 93.94% |
| Context recall | 31.96% | 33.74% |
| Essential-claim evidence coverage | 44.98% | 47.22% |

Dense retrieval searches by meaning, allowing a question and a manuscript passage to use different words while remaining semantically similar. Hybrid retrieval combines that semantic search with literal word-and-phrase search and merges the rankings.

Hit@5 asks a modest question: did at least one relevant passage appear among the first five results? Hybrid retrieval did that for 93.94% of the answerable questions.

Recall@5 asks a harder one: what share of *all* expected manuscript locations appeared in those five results? Hybrid retrieval found only 25.97%.

That contrast is more revealing than either number alone. Archivist was very likely to find one useful passage, yet it often missed most of the other evidence that a complete answer required.

Hybrid retrieval was only slightly better overall, and the effect was inconsistent. Focused biographical questions improved by 6.49 percentage points and adversarial-premise questions by 12.50 points, while conceptual questions became 8.40 points worse. Across the 33 answerable questions, hybrid retrieval improved results for 11, left 13 unchanged, and worsened nine.

That made hybrid retrieval worth keeping, but not worth treating as a universal cure.

### A measurement mistake I nearly published

I initially described these coverage figures as though 100% were an attainable result. That was misleading.

The gold labels often identify more relevant manuscript locations than the retrieval policy is permitted to return. A five-result list cannot contain twelve or thirteen distinct expected locations. When I calculated the maximum allowed by result count alone for each question, the macro ceiling was 49.08% at five results—not 100%. Hybrid Recall@5 therefore reached about 52.9% of that cardinality-only ceiling.

That is only a result-count bound; filtering and diversity rules can make the true attainable ceiling lower still. The correction does not rescue the system. It changes the diagnosis from “25.97% out of a possible 100%” to “about half of what this retrieval depth could contain.”

That is a flaw in my metric design rather than a defense of Archivist. A coverage figure whose maximum is unstated invites everyone, including its author, to misread it.

The more important finding survived the correction: Archivist omitted substantial labeled evidence at every measured stage. My gold labels and my retrieval budget disagreed about how much evidence a complete answer needed. Resolving that disagreement required more than tuning the retriever.

## The answers passed more tests than the evaluator did

The frozen answer run produced another set of results:

| Frozen answer-run result | Observed value |
| --- | ---: |
| Answers that passed generation and release checks | 35/37 |
| Citation references that resolved | 251/251 |
| Expected question-location pairs in final answer sources | 75/428 (17.5%) |
| Decomposition-instrument technical failures | 27/37 |

“Thirty-five completed answers” is a delivery result, not an accuracy score. It means those answers passed the system's structural and release checks. It does not mean that every answer was complete or correct.

Likewise, 251 of 251 citation references resolving is a useful but narrow success. It proves that every rendered source number pointed to a source entry that existed in that answer. It does not prove that the source supported the neighboring claim. Citation resolvability is mechanical integrity, not semantic faithfulness.

The 75 of 428 gold-location result was measured over the final source sets attached to answers. It is a micro aggregate, whereas Recall@5 is a macro average of per-question recalls, so the two percentages should not be treated as interchangeable. They nevertheless support the same broad diagnosis: the system commonly found useful evidence while omitting much of the evidence I had labeled as relevant.

Then the evaluator failed.

To score answer-level properties, I first needed to decompose each response into checkable claims. The decomposition instrument returned technically invalid results for 27 of the 37 answers. Twenty-six failures came from exact-span mismatches and one from an incomplete response. These were failures of the measuring tool, not evidence that Archivist had answered badly.

Only ten decomposition records survived validation, and only eight represented substantive released answers. That was far too little coverage to turn the semantic results into an honest accuracy percentage.

This may have been the most useful outcome of the exercise. Building an evaluation pipeline does not make its measurements trustworthy. Evaluation models, schemas, and validators have their own assumptions and failure modes.

The evaluator also has to be evaluated.

## The problem users could feel

I separately ran the 33 answerable questions against the public application as a warm, sequential production workload. Each request started a fresh conversation, used Essential mode, contained no prior history, and was attempted once without a retry or replacement. Two readiness checks ran before the cohort, and cold starts were not part of the measurement.

| Warm production cohort | Observed value |
| --- | ---: |
| Structurally valid responses | 29/33 (87.9%) |
| Fail-closed generation-contract rejections | 4/33 (12.1%) |
| Attempts with complete instrumentation | 33/33 |
| Server-duration median | 54.4 seconds |
| Server-duration p95 | 113.8 seconds |
| Estimated API cost | $4.91 |

The four rejected responses contained invalid or incomplete evidence-contract payloads. Archivist withheld them instead of displaying claims whose evidence relationships failed local validation.

All 33 attempts still produced complete timing, usage, cost, identity, and outcome records. That observability mattered because it let me distinguish a bad answer contract from a missing measurement.

The latency result was harder to excuse. The 54.4-second median is the complete server-side endpoint duration for this observed production cohort—not browser-to-screen latency and not a service-level guarantee. With only 29 successful responses, the 113.8-second p95 is effectively the second-slowest observation, so I treat it as a description of this run rather than a stable estimate of the tail.

Even with those qualifications, a roughly 54-second median was much too slow for a chat application.

The production cohort's $4.91 cost is an instrumented estimate of provider usage, not a claim about an invoice line item.

## What the first evaluation actually established

The first evaluation did not give me the neat answer-quality score I had hoped to publish. It left me with a well-measured prototype: mechanically sound citation links, a strong chance of finding at least one relevant passage, mediocre evidence completeness, an unreliable semantic evaluator, and response times that were unacceptable for conversation.

Latency was also the failure users could feel immediately.

Those were the results when I first drafted this post.

Before publishing it, I changed the system.

## Redesigning the model boundary

My first explanation for the latency was too simple: I thought I was merely sending the API too much information. I did experiment with compacting the request, but I never completed the paid comparison needed to prove that smaller schemas caused a particular speedup.

The change I can defend is architectural.

The application now assembles and validates a bounded manuscript-evidence dossier locally. The model receives that dossier and the instructions for the selected perspective, then performs one narrower task: author the response. It no longer has to serialize several mutually constrained evidence-relationship ledgers while writing the prose.

Personal questions such as “How are you?” now take a separate conversational route. Those replies need character voice and a question that leads back into discussion of the manuscript; they do not need an irrelevant manuscript retrieval operation pretending to answer a factual question.

The current version also stops treating every historical question as though it needs the same length. Ordinary questions target a focused response, while broad synthesis questions retain room for a longer answer. These are writing targets rather than hard minimums.

That redesign produced measurements on two distinct routes. I am keeping them separate rather than combining them into one flattering percentage.

## A fast route for actual conversation

The character-conversation route produced the cleanest latency number so far.

I tested 12 no-retry social turns across Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist. All 12 generated successfully, and all 12 ended with a valid question leading the user back toward the manuscript. There were no fallbacks.

Median latency was **3.59 seconds**, with observed results ranging from 2.74 to 4.17 seconds. The 12 turns cost an estimated $0.067 in total, or about $0.0055 per turn.

That is a narrow but defensible result: in-character social responses across four modes, 12 of 12 generated, at a 3.59-second median with no retries or fallbacks. It is not the latency of a manuscript-grounded RAG answer, and I will not present it as though it were.

## Grounded answers are still slower

I later reran the same 37 questions against the redesigned authoring path. By then the benchmark was no longer pristine or held out; it was a reused, locked benchmark. Every question was still attempted once, with no retries.

The run produced 34 authored answers and three delivered evidence fallbacks. Across all 37 authoring attempts, median authoring-boundary latency was 19.3 seconds and p95 was 30.3 seconds. For the 34 generated answers alone, the median was 18.9 seconds and p95 was 27.4 seconds.

That boundary includes the model call, structured parsing, and local answer validation. It does not represent browser end-to-end latency.

Citation mechanics remained clean: all 371 rendered source references resolved locally, with no malformed or out-of-range references. Again, that does not establish entailment.

The larger engineering gain was in the evaluator. After redesigning the decomposition instrument, valid outcomes rose from 10 of 37 in the original run to 35 of 37. Technical failures fell from 27 to two—a 92.6% reduction across the two versioned cohorts.

That is not an answer-quality improvement. It is an evaluation-instrument reliability improvement. It means the next semantic analysis can cover nearly the whole cohort instead of drawing conclusions from a small surviving fraction.

The current adaptive path has also passed a three-question local smoke test: three authored responses, no retries or fallbacks, and a 22.0-second median wall time. That sample is useful as a mechanical check, not as a p95, a quality result, or a production benchmark.

For the same reason, I do not claim a formal percentage reduction from the earlier 54.4-second production median. The old number measured a warm public server cohort, the 19.3-second result measured an authoring boundary, and the 3.59-second result belongs to a separate social route. Comparing them as though they were one controlled experiment would undo the care that made the evaluation useful in the first place.

## Faster is not finished

Archivist's conversational route is now fast enough to feel like a chat rather than a test of patience: 12 of 12 generated replies at a 3.59-second median, with no retries or fallbacks. Grounded manuscript answers remain slower, at roughly 19–22 seconds across two differently scoped measurements.

I still cannot honestly reduce Archivist's answer quality to one accuracy percentage. The semantic judge needs calibration. Evidence completeness remains the central retrieval problem. The current version still needs a full fixed-benchmark run under one consistent timing boundary, followed by a public production measurement of the deployed system.

That is what the evaluation changed for me. It did not certify the project as finished. It replaced impressions with specific failures, specific measurements, and a much clearer order of work.

The citations held together. The retriever often found something useful but not enough. The evaluator failed, then became substantially more reliable. And the conversational experience now has a latency number I can point to.

Faster is not finished, but the conversational route is finally usable.
