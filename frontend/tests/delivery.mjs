import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createServer } from "vite";

const server = await createServer({
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true }
});

const originalFetch = globalThis.fetch;

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    value(key) {
      return values.get(key);
    }
  };
}

function byteStream(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    }
  });
}

function responseForLines(lines, splitAt = []) {
  const bytes = new TextEncoder().encode(lines.join("\n") + "\n");
  const boundaries = [0, ...splitAt, bytes.length]
    .filter((value, index, values) => value >= 0 && value <= bytes.length && values.indexOf(value) === index)
    .sort((left, right) => left - right);
  const chunks = boundaries.slice(0, -1).map((start, index) => bytes.slice(start, boundaries[index + 1]));
  return new Response(byteStream(chunks), {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" }
  });
}

const canonicalResult = {
  answer: "A checked answer with café and a ship. [Source 1]",
  answer_status: "answered",
  archivist_mode: "professional",
  historiographical_lens: "evidence_first",
  voice: "plainspoken",
  worldview: "secular_humanist",
  sources: []
};

const requestArguments = [
  "current",
  "What happened?",
  5,
  {
    historiographicalLens: "evidence_first",
    voice: "plainspoken",
    worldview: "secular_humanist"
  },
  [],
  {
    conversationId: "conversation-test",
    turnId: "turn-test",
    archivistMode: "professional",
    publicDemo: false
  }
];

const oversizedHistory = [
  {
    question: `Old question ${"q".repeat(1_700)}`,
    answer: `Old answer ${"a".repeat(12_500)}`,
    archivist_mode: "essential"
  },
  {
    question: `Latest question ${"r".repeat(1_700)}`,
    answer: `Latest answer ${"b".repeat(12_500)}`,
    archivist_mode: "professional"
  }
];

try {
  const delivery = await server.ssrLoadModule("/src/delivery.ts");
  const api = await server.ssrLoadModule("/src/api.ts");

  assert.equal(api.answerPolicyLabel("retrieval-authored-v5"), "Retrieval-authored v5");
  assert.equal(api.answerPolicyLabel("retrieval-authored-v4"), "Retrieval-authored v4");
  assert.equal(api.answerPolicyLabel("retrieval-authored-v3"), "Retrieval-authored v3");
  assert.equal(api.answerPolicyLabel("retrieval-authored-v2"), "Retrieval-authored v2");
  assert.equal(api.answerPolicyLabel("retrieval-authored-v1"), "Retrieval-authored v1");
  assert.equal(api.answerPolicyLabel("application-compiled-v1"), "Application-compiled v1");
  assert.equal(api.answerPolicyLabel("evidence-planned-v26"), "Evidence-planned v26");
  assert.equal(api.answerPolicyLabel("future-policy"), "Answer policy · future-policy");
  assert.equal(api.answerPolicyLabel(null), null);

  const completeRequestBodies = [];
  const completeResult = {
    ...canonicalResult,
    answer_strategy_version: "retrieval-authored-v2"
  };
  globalThis.fetch = async (url, init) => {
    completeRequestBodies.push({ url, body: JSON.parse(init.body) });
    return new Response(JSON.stringify(completeResult), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  };
  const localComplete = await api.askQuestion(...requestArguments);
  assert.equal(
    Object.hasOwn(completeRequestBodies[0].body, "rag_policy_version"),
    false,
    "development complete-answer requests should not carry a retired RAG policy selector"
  );
  assert.equal(
    localComplete.answer_strategy_version,
    "retrieval-authored-v2",
    "the complete-answer client should preserve the policy identity reported by the server"
  );
  await api.askQuestion(
    ...requestArguments.slice(0, 5),
    {
      ...requestArguments[5],
      publicDemo: true
    }
  );
  assert.equal(
    Object.hasOwn(completeRequestBodies[1].body, "rag_policy_version"),
    false,
    "public complete-answer requests must never carry a developer RAG policy selector"
  );
  await api.askQuestion(
    ...requestArguments.slice(0, 4),
    oversizedHistory,
    requestArguments[5]
  );
  assert.deepEqual(
    completeRequestBodies[2].body.history,
    oversizedHistory,
    "development complete-answer requests should preserve their supplied history"
  );
  await api.askQuestion(
    ...requestArguments.slice(0, 4),
    oversizedHistory,
    {
      ...requestArguments[5],
      publicDemo: true
    }
  );
  assert.deepEqual(
    completeRequestBodies[3].body.history,
    [{
      ...oversizedHistory[1],
      question: oversizedHistory[1].question.slice(0, 1_500),
      answer: oversizedHistory[1].answer.slice(0, 1_000)
    }],
    "public complete-answer requests should send only a bounded latest turn"
  );

  const chatCss = readFileSync(new URL("../src/chat.css", import.meta.url), "utf8");
  const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const vibeControlSource = readFileSync(new URL("../src/VibeControl.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(
    appSource,
    /V27 compact|Experimental latency settings/,
    "the retired compact-latency experiment must not appear in the reader UI"
  );
  assert.match(appSource, /Essential returns compiled, cited evidence directly without a\s+prose-generation rewrite/);
  assert.match(appSource, /Lens, voice, and worldview are prose settings/);
  assert.match(
    appSource,
    /Choose a generated mode to use them/,
    "Essential's settings explanation should remain accurate as character modes are added"
  );
  assert.match(appSource, /Direct-evidence turns may also show locally checked manuscript\s+claims/);
  assert.match(
    appSource,
    /<strong>Settings<\/strong>/,
    "the composer disclosure should use the single visible title Settings"
  );
  assert.doesNotMatch(
    appSource,
    /<small>Reading options<\/small>/,
    "the retired Reading options title should not remain in the composer"
  );
  assert.match(
    appSource,
    /const activeModeLabel = customMode \? "Custom" : selectedMode\.label/,
    "active customized controls should identify the mode as Custom"
  );
  assert.match(
    appSource,
    /type ChatTurn = \{[\s\S]*?archivistMode: ArchivistModeId;[\s\S]*?appearance: VibeId;/,
    "each turn should retain the appearance selected when its request began"
  );
  assert.match(
    appSource,
    /const nextTurn: ChatTurn = \{[\s\S]*?archivistMode: archivistModeId,[\s\S]*?appearance,[\s\S]*?facets: \{ \.\.\.facets \}/,
    "new request snapshots should capture appearance alongside mode and facets"
  );
  assert.match(
    appSource,
    /archivistModeSummary\(\s*turn\.archivistMode,\s*turn\.facets,\s*turn\.appearance\s*\)/,
    "completed-turn badges should use the request's appearance snapshot"
  );
  assert.match(
    appSource,
    /whose character remains active/,
    "a Custom perspective should still disclose its underlying character influence"
  );
  assert.match(
    appSource,
    /className="chat-perspective-note"[\s\S]*?aria-live="polite"[\s\S]*?<strong>\{activeModeLabel\}<\/strong>[\s\S]*?<p>\{perspectiveCopy\}<\/p>/,
    "both composers should visibly disclose their current perspective"
  );
  assert.match(
    appSource,
    /aria-describedby=\{`\$\{perspectiveId\} \$\{groundingId\}`\}/,
    "the question field should expose perspective and grounding context to assistive technology"
  );
  assert.match(
    vibeControlSource,
    /const displayLabel = custom \? "Custom" : current\.shortLabel/,
    "the top-right control should show exactly Custom for an overridden preset"
  );
  assert.match(
    vibeControlSource,
    /aria-label=\{`Archivist mode: \$\{displayLabel\}\. Choose a mode\.`\}/,
    "the icon-only mobile mode control should retain an accessible name"
  );
  assert.match(
    appSource,
    /question:\s*questionForConversationHistory\(turn\)\.slice\(0, 4_000\)/,
    "conversation history should carry the server-resolved standalone question forward"
  );
  assert.match(
    appSource,
    /question:\s*questionForConversationHistory\(candidate\)\.slice\(0, 4_000\)/,
    "retry history should carry the server-resolved standalone question forward"
  );
  assert.match(
    appSource,
    /const fallbackNotice = authoredFallbackNotice\(turn\.answerStatus, turn\.archivistMode\)/,
    "completed turns should derive fallback disclosure from the server-reported answer status"
  );
  assert.match(
    appSource,
    /className="turn-fallback-notice"[\s\S]*?role="status"[\s\S]*?fallbackNotice\.message/,
    "a generated-mode fallback should be exposed as a visible nonfatal status above the answer"
  );
  assert.match(
    chatCss,
    /\.turn-fallback-notice\s*\{[^}]*display:\s*grid;[^}]*border:/s,
    "the fallback notice should have a visible theme-aware treatment"
  );
  assert.match(
    chatCss,
    /\.chat-perspective-note\s*\{[^}]*display:\s*grid;[^}]*border-left:/s,
    "the perspective disclosure should have a visible theme-aware treatment"
  );
  assert.match(
    chatCss,
    /\.chat-composer\.is-docked\s+\.chat-perspective-note\s*\{[^}]*grid-column:\s*1\s*\/\s*-1\s*;/s,
    "the docked perspective disclosure should span the input and control columns"
  );
  assert.match(
    chatCss,
    /\.chat-composer\.is-docked\s+\.chat-answer-settings-disclosure\s*>\s*\.chat-answer-settings-panel\s*\{[^}]*position:\s*fixed;[^}]*bottom:\s*calc\(var\(--chat-dock-height\)\s*\+\s*8px\)\s*;/s,
    "the docked settings panel should open above the complete perspective-aware composer"
  );
  assert.match(
    chatCss,
    /\.vibe-trigger\.is-custom\s*>\s*span\s*\{[^}]*display:\s*grid\s*;/s,
    "Custom should remain visible in the compact mobile mode control"
  );
  const settingsPanelRules = [
    ...chatCss.matchAll(
      /\.chat-answer-settings-disclosure\s*>\s*\.chat-answer-settings-panel\s*\{([^}]*)\}/g
    )
  ].map((match) => match[1]);
  const scrollableSettingsPanelRule = settingsPanelRules.find((rule) => /overflow-y:\s*auto\s*;/.test(rule)) ?? "";
  const landingSettingsPanelRule = chatCss.match(
    /\.chat-composer\.is-landing\s+\.chat-answer-settings-disclosure\s*>\s*\.chat-answer-settings-panel\s*\{([^}]*)\}/
  )?.[1] ?? "";
  assert.match(
    landingSettingsPanelRule,
    /position:\s*static\s*;/,
    "landing settings must expand in document flow so the page can scroll on short viewports"
  );
  assert.match(
    landingSettingsPanelRule,
    /max-height:\s*none\s*;/,
    "landing settings must not create a nested height limit"
  );
  assert.match(
    landingSettingsPanelRule,
    /overflow-y:\s*visible\s*;/,
    "landing settings must leave vertical scrolling to the document"
  );
  assert.match(
    scrollableSettingsPanelRule,
    /max-height:\s*min\(\s*680px,\s*calc\(100dvh\s*-\s*var\(--chat-dock-height,\s*84px\)\s*-\s*32px\s*-\s*env\(safe-area-inset-top\)\)\s*\)\s*;/,
    "the docked settings panel should remain bounded by the visual viewport and safe area"
  );
  assert.match(
    scrollableSettingsPanelRule,
    /overflow-y:\s*auto\s*;/,
    "the bounded settings panel must provide its own vertical scrolling"
  );

  const storedProgressive = memoryStorage({
    [delivery.RESPONSE_DELIVERY_STORAGE_KEY]: "progressive"
  });
  assert.equal(delivery.storedResponseDelivery(true, storedProgressive), "progressive");
  assert.equal(delivery.storedResponseDelivery(false, storedProgressive), "complete");
  assert.equal(
    delivery.storedResponseDelivery(true, memoryStorage({
      [delivery.RESPONSE_DELIVERY_STORAGE_KEY]: "unexpected"
    })),
    "complete"
  );
  const gatedStorage = memoryStorage();
  delivery.persistResponseDelivery("progressive", false, gatedStorage);
  assert.equal(gatedStorage.value(delivery.RESPONSE_DELIVERY_STORAGE_KEY), undefined);
  delivery.persistResponseDelivery("progressive", true, gatedStorage);
  assert.equal(gatedStorage.value(delivery.RESPONSE_DELIVERY_STORAGE_KEY), "progressive");
  assert.equal(delivery.progressiveElapsedSeconds(1_000, 13_450), 12);
  assert.equal(delivery.progressiveElapsedSeconds(13_450, 1_000), 0);
  assert.equal(delivery.progressiveElapsedSeconds(Number.NaN, 1_000), 0);
  assert.equal(delivery.formatProgressiveElapsed(0), "just started");
  assert.equal(delivery.formatProgressiveElapsed(12.9), "12s elapsed");
  assert.equal(delivery.formatProgressiveElapsed(65), "1m 05s elapsed");

  const unicodeLine = JSON.stringify({ message: "café 📚" }) + "\r\n";
  const unicodeBytes = new TextEncoder().encode(unicodeLine);
  const decoded = [];
  await delivery.readNdjson(
    byteStream([
      unicodeBytes.slice(0, 18),
      unicodeBytes.slice(18, 22),
      unicodeBytes.slice(22)
    ]),
    (value) => decoded.push(value)
  );
  assert.deepEqual(decoded, [{ message: "café 📚" }]);
  await assert.rejects(
    delivery.readNdjson(byteStream([new TextEncoder().encode("{bad json}\n")]), () => {}),
    /malformed progressive response frame/
  );
  let malformedCancelReason;
  const cancellableMalformedStream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("{bad json}\n"));
    },
    cancel(reason) {
      malformedCancelReason = reason;
    }
  });
  await assert.rejects(
    delivery.readNdjson(cancellableMalformedStream, () => {}),
    /malformed progressive response frame/
  );
  assert.match(String(malformedCancelReason), /malformed progressive response frame/);

  let successfulStreamCancelled = false;
  const successfulStream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"ok":true}\n'));
      controller.close();
    },
    cancel() {
      successfulStreamCancelled = true;
    }
  });
  await delivery.readNdjson(successfulStream, () => {});
  assert.equal(successfulStreamCancelled, false);
  const oversizedLine = "x".repeat(delivery.MAX_NDJSON_FRAME_CHARACTERS + 1);
  await assert.rejects(
    delivery.readNdjson(
      byteStream([new TextEncoder().encode(oversizedLine + "\n")]),
      () => {}
    ),
    /oversized progressive response frame/
  );
  await assert.rejects(
    delivery.readNdjson(
      byteStream([new TextEncoder().encode(oversizedLine)]),
      () => {}
    ),
    /oversized progressive response frame/
  );
  await assert.rejects(
    delivery.readNdjson(
      byteStream([new TextEncoder().encode("{}\n" + oversizedLine)]),
      () => {}
    ),
    /oversized progressive response frame/
  );

  const schema = "archivist.answer_stream/2";
  const checkedClaimOne = "A checked answer mentions café. [Source 1].";
  const checkedClaimTwo = "A second checked claim names a ship. [Source 2].";
  const framedResult = {
    ...canonicalResult,
    answer_strategy_version: "retrieval-authored-v2",
    answer: [
      "A subjective preface remains withheld while claims stream.",
      checkedClaimOne,
      checkedClaimTwo,
      "A subjective conclusion remains withheld until completion."
    ].join("\n\n")
  };
  const stages = [];
  const heartbeats = [];
  const checkedClaims = [];
  const claimCallbackOrder = [];
  let progressiveRequest;
  globalThis.fetch = async (url, init) => {
    progressiveRequest = { url, body: JSON.parse(init.body) };
    return responseForLines([
      JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Server text must not reach the UI." }),
      JSON.stringify({ schema, type: "heartbeat", sequence: 1 }),
      JSON.stringify({ schema, type: "stage", sequence: 2, stage: "generating_answer", message: "Another server-owned string." }),
      JSON.stringify({ schema, type: "checked_claim", sequence: 3, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
      JSON.stringify({ schema, type: "stage", sequence: 4, stage: "validating_answer", message: "Untrusted server copy." }),
      JSON.stringify({ schema, type: "checked_claim", sequence: 5, claim_index: 2, paragraph: 2, text: checkedClaimTwo }),
      JSON.stringify({ schema, type: "complete", sequence: 6, result: framedResult })
    ], [1, 7, 31, 88, 173]);
  };
  const completed = await api.askQuestionProgressively(...requestArguments.slice(0, 5), {
    ...requestArguments[5],
    onStage: (update) => stages.push(update),
    onHeartbeat: (update) => heartbeats.push(update),
    onCheckedClaim: async (claim) => {
      claimCallbackOrder.push(`start:${claim.claimIndex}`);
      await Promise.resolve();
      checkedClaims.push(claim);
      claimCallbackOrder.push(`end:${claim.claimIndex}`);
    }
  });
  assert.deepEqual(completed, framedResult);
  assert.equal(
    Object.hasOwn(progressiveRequest.body, "rag_policy_version"),
    false,
    "development progressive requests should not carry a retired RAG policy selector"
  );
  assert.equal(
    completed.answer_strategy_version,
    "retrieval-authored-v2",
    "a progressive completion should preserve the policy identity reported in its terminal result"
  );
  assert.deepEqual(checkedClaims, [
    { claimIndex: 1, paragraph: 1, text: checkedClaimOne },
    { claimIndex: 2, paragraph: 2, text: checkedClaimTwo }
  ]);
  assert.equal(api.progressiveCheckedClaimsText(checkedClaims), `${checkedClaimOne}\n\n${checkedClaimTwo}`);
  assert.deepEqual(stages, [
    { stage: "accepted", message: "Starting your request." },
    { stage: "generating_answer", message: "Drafting an answer from retrieved evidence." },
    {
      stage: "validating_answer",
      message: "Checking response structure and citation references."
    }
  ]);
  assert.deepEqual(heartbeats, [{ count: 1 }]);
  assert.deepEqual(claimCallbackOrder, ["start:1", "end:1", "start:2", "end:2"]);

  const compactedProgressiveRequests = [];
  globalThis.fetch = async (url, init) => {
    compactedProgressiveRequests.push({ url, body: JSON.parse(init.body) });
    const publicRequest = compactedProgressiveRequests.length === 2;
    const frames = [
      JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Accepted." }),
      JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
      JSON.stringify({ schema, type: "stage", sequence: 2, stage: "validating_answer", message: "Validating." })
    ];
    if (publicRequest) {
      frames.push(JSON.stringify({ schema, type: "stage", sequence: 3, stage: "checking_release", message: "Checking." }));
    }
    frames.push(JSON.stringify({
      schema,
      type: "complete",
      sequence: publicRequest ? 4 : 3,
      result: completeResult
    }));
    return responseForLines(frames);
  };
  await api.askQuestionProgressively(
    ...requestArguments.slice(0, 4),
    oversizedHistory,
    requestArguments[5]
  );
  await api.askQuestionProgressively(
    ...requestArguments.slice(0, 4),
    oversizedHistory,
    {
      ...requestArguments[5],
      publicDemo: true
    }
  );
  assert.deepEqual(
    compactedProgressiveRequests[0].body.history,
    oversizedHistory,
    "development progressive requests should preserve their supplied history"
  );
  assert.deepEqual(
    compactedProgressiveRequests[1].body.history,
    [{
      ...oversizedHistory[1],
      question: oversizedHistory[1].question.slice(0, 1_500),
      answer: oversizedHistory[1].answer.slice(0, 1_000)
    }],
    "public progressive requests should send only a bounded latest turn"
  );

  const zeroClaimAuthoredResult = {
    ...canonicalResult,
    answer_strategy_version: "retrieval-authored-v2",
    answer: "A substantive authored answer grounded in retrieved evidence. [Source 1]\n\nWhat part of this history would you like to explore next?"
  };
  let zeroClaimCallbackCount = 0;
  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "validating_answer", message: "Validated." }),
    JSON.stringify({ schema, type: "complete", sequence: 3, result: zeroClaimAuthoredResult })
  ]);
  assert.deepEqual(
    await api.askQuestionProgressively(...requestArguments.slice(0, 5), {
      ...requestArguments[5],
      onCheckedClaim: () => {
        zeroClaimCallbackCount += 1;
      }
    }),
    zeroClaimAuthoredResult,
    "an authored progressive response should complete without provisional checked-claim frames"
  );
  assert.equal(zeroClaimCallbackCount, 0);

  const reorderedGeneratedResult = {
    ...framedResult,
    answer: [
      "Editorial interpretation - the evidence can be read in another order.",
      checkedClaimTwo,
      "Editorial interpretation - the framing remains terminal-only.",
      checkedClaimOne
    ].join("\n\n")
  };
  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 3, claim_index: 2, paragraph: 2, text: checkedClaimTwo }),
    JSON.stringify({ schema, type: "stage", sequence: 4, stage: "validating_answer", message: "Validated." }),
    JSON.stringify({ schema, type: "complete", sequence: 5, result: reorderedGeneratedResult })
  ]);
  assert.deepEqual(
    await api.askQuestionProgressively(...requestArguments),
    reorderedGeneratedResult,
    "terminal reconciliation should accept independently preserved claims in generated prose order"
  );

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "heartbeat", sequence: 1 })
  ]);
  await assert.rejects(
    api.askQuestionProgressively(...requestArguments),
    (error) => error instanceof api.ProgressiveStreamError
      && error.receivedStreamEvent === true
      && /ended before a verified answer arrived/.test(error.message)
  );

  let acceptedFetchCalls = 0;
  globalThis.fetch = async () => {
    acceptedFetchCalls += 1;
    return responseForLines([
      JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
      JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
      JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
      JSON.stringify({ schema, type: "error", sequence: 3, error: { code: "safe_failure", message: "Archivist could not complete this response." } })
    ]);
  };
  await assert.rejects(
    api.askQuestionProgressively(...requestArguments),
    (error) => error instanceof api.ProgressiveStreamError
      && error.receivedStreamEvent === true
      && error.code === "safe_failure"
      && /could not complete this response/.test(error.message)
      && /incomplete checked-claim assembly was discarded/.test(error.message)
  );
  assert.equal(acceptedFetchCalls, 1, "the stream client must not retry after an accepted frame");

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "heartbeat", sequence: 1 })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /out of order/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "retrieving_sources", message: "Retrieving." }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "planning_search", message: "Late planning." })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /stages out of order/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "generating_answer", message: "Generating twice." })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /stages out of order/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "heartbeat", sequence: 0 })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /did not begin with acceptance/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema: "archivist.answer_stream/1", type: "stage", sequence: 0, stage: "accepted", message: "Old stream." })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /incompatible progressive response frame/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 1, claim_index: 1, paragraph: 1, text: checkedClaimOne })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /before answer generation began/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 2, paragraph: 1, text: checkedClaimOne })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /checked claims out of order/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: api.MAX_PROGRESSIVE_PARAGRAPH + 1, text: checkedClaimOne })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /invalid checked-claim paragraph/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 2, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 3, claim_index: 2, paragraph: 1, text: checkedClaimTwo })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /invalid checked-claim paragraph/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: "An uncited claim." })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /invalid checked claim/);

  const oversizedCheckedClaim = "x".repeat(api.MAX_PROGRESSIVE_CLAIM_CHARACTERS) + " [Source 1].";
  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: oversizedCheckedClaim })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /invalid checked claim/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "stage", sequence: 3, stage: "preparing_context", message: "Late non-final stage." })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /non-final progress stage/);

  const citationSuffix = " [Source 1].";
  const maximumClaim = "x".repeat(api.MAX_PROGRESSIVE_CLAIM_CHARACTERS - citationSuffix.length) + citationSuffix;
  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    ...Array.from({ length: 13 }, (_, index) => JSON.stringify({
      schema,
      type: "checked_claim",
      sequence: index + 2,
      claim_index: index + 1,
      paragraph: 1,
      text: maximumClaim
    }))
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /exceeded the client safety limit/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "complete", sequence: 3, result: framedResult })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /before the required checks finished/);

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "stage", sequence: 3, stage: "validating_answer", message: "Validated." }),
    JSON.stringify({ schema, type: "complete", sequence: 4, result: canonicalResult })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /did not match its canonical answer/);

  let publicProgressiveRequest;
  globalThis.fetch = async (url, init) => {
    publicProgressiveRequest = { url, body: JSON.parse(init.body) };
    return responseForLines([
      JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
      JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
      JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
      JSON.stringify({ schema, type: "stage", sequence: 3, stage: "checking_release", message: "Release check." }),
      JSON.stringify({ schema, type: "complete", sequence: 4, result: { ...canonicalResult, answer: checkedClaimOne } })
    ]);
  };
  assert.deepEqual(
    await api.askQuestionProgressively(
      ...requestArguments.slice(0, 5),
      {
        ...requestArguments[5],
        publicDemo: true
      }
    ),
    { ...canonicalResult, answer: checkedClaimOne }
  );
  assert.equal(
    Object.hasOwn(publicProgressiveRequest.body, "rag_policy_version"),
    false,
    "public progressive requests must never carry a developer RAG policy selector"
  );

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "checking_release", message: "Release check." }),
    JSON.stringify({ schema, type: "complete", sequence: 3, result: zeroClaimAuthoredResult })
  ]);
  assert.deepEqual(
    await api.askQuestionProgressively(
      ...requestArguments.slice(0, 5),
      { ...requestArguments[5], publicDemo: true }
    ),
    zeroClaimAuthoredResult,
    "a public authored response should also complete without provisional checked-claim frames"
  );

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "validating_answer", message: "Validated." }),
    JSON.stringify({ schema, type: "complete", sequence: 3, result: canonicalResult })
  ]);
  await assert.rejects(
    api.askQuestionProgressively(
      ...requestArguments.slice(0, 5),
      { ...requestArguments[5], publicDemo: true }
    ),
    /before the required checks finished/
  );

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "validating_answer", message: "Validated." }),
    JSON.stringify({ schema, type: "complete", sequence: 2, result: canonicalResult }),
    JSON.stringify({ schema, type: "heartbeat", sequence: 3 })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /data after a terminal/);

  for (const status of [404, 405, 501]) {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: { message: "Progressive endpoint unavailable." } }),
      { status, headers: { "Content-Type": "application/json" } }
    );
    await assert.rejects(
      api.askQuestionProgressively(...requestArguments),
      (error) => api.isProgressiveFallbackEligible(error)
        && error instanceof api.ProgressiveUnavailableError
        && error.receivedStreamEvent === false
    );
  }

  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: { message: "Service unavailable." } }),
    { status: 503, headers: { "Content-Type": "application/json" } }
  );
  await assert.rejects(
    api.askQuestionProgressively(...requestArguments),
    (error) => error instanceof api.ApiRequestError
      && !api.isProgressiveFallbackEligible(error)
  );

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "complete", sequence: 1, result: {} })
  ]);
  await assert.rejects(api.askQuestionProgressively(...requestArguments), /unknown progressive response frame/);
} finally {
  globalThis.fetch = originalFetch;
  await server.close();
}
