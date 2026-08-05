import assert from "node:assert/strict";

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

try {
  const delivery = await server.ssrLoadModule("/src/delivery.ts");
  const api = await server.ssrLoadModule("/src/api.ts");

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
  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Server text must not reach the UI." }),
    JSON.stringify({ schema, type: "heartbeat", sequence: 1 }),
    JSON.stringify({ schema, type: "stage", sequence: 2, stage: "generating_answer", message: "Another server-owned string." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 3, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "stage", sequence: 4, stage: "validating_answer", message: "Untrusted server copy." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 5, claim_index: 2, paragraph: 2, text: checkedClaimTwo }),
    JSON.stringify({ schema, type: "complete", sequence: 6, result: framedResult })
  ], [1, 7, 31, 88, 173]);
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
  assert.deepEqual(checkedClaims, [
    { claimIndex: 1, paragraph: 1, text: checkedClaimOne },
    { claimIndex: 2, paragraph: 2, text: checkedClaimTwo }
  ]);
  assert.equal(api.progressiveCheckedClaimsText(checkedClaims), `${checkedClaimOne}\n\n${checkedClaimTwo}`);
  assert.deepEqual(stages, [
    { stage: "accepted", message: "Starting your request." },
    { stage: "generating_answer", message: "Drafting a source-grounded answer." },
    { stage: "validating_answer", message: "Validating grounding and citations." }
  ]);
  assert.deepEqual(heartbeats, [{ count: 1 }]);
  assert.deepEqual(claimCallbackOrder, ["start:1", "end:1", "start:2", "end:2"]);

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

  globalThis.fetch = async () => responseForLines([
    JSON.stringify({ schema, type: "stage", sequence: 0, stage: "accepted", message: "Request accepted." }),
    JSON.stringify({ schema, type: "stage", sequence: 1, stage: "generating_answer", message: "Generating." }),
    JSON.stringify({ schema, type: "checked_claim", sequence: 2, claim_index: 1, paragraph: 1, text: checkedClaimOne }),
    JSON.stringify({ schema, type: "stage", sequence: 3, stage: "checking_release", message: "Release check." }),
    JSON.stringify({ schema, type: "complete", sequence: 4, result: { ...canonicalResult, answer: checkedClaimOne } })
  ]);
  assert.deepEqual(
    await api.askQuestionProgressively(
      ...requestArguments.slice(0, 5),
      { ...requestArguments[5], publicDemo: true }
    ),
    { ...canonicalResult, answer: checkedClaimOne }
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
