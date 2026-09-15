import assert from "node:assert/strict";

export async function testCostSummary(server) {
  const { createCostSummaryController } = await server.ssrLoadModule("/src/costSummary.ts");
  const originalFetch = globalThis.fetch;
  const requests = [];
  const updates = [];
  globalThis.fetch = (url, init) => new Promise((resolve, reject) => {
    requests.push({
      url,
      signal: init.signal,
      resolve(summary) {
        resolve(new Response(JSON.stringify(summary), {
          headers: { "Content-Type": "application/json" }
        }));
      },
      reject
    });
  });
  const controller = createCostSummaryController((state) => updates.push(state));
  const latest = () => updates.at(-1);
  const oldSummary = { conversation_usd: 2, month_usd: 5 };
  const newSummary = { conversation_usd: 0, month_usd: 5 };
  const answerSummary = { conversation_usd: 3, month_usd: 8 };

  try {
    const oldConversation = controller.activate("current", "old-conversation");
    assert.equal(new URL(requests[0].url, "http://localhost").searchParams.get("conversation_id"), "old-conversation");

    controller.clear();
    assert.equal(requests[0].signal.aborted, true);
    assert.deepEqual(latest(), { summary: null, loading: false, error: null });
    await controller.refresh();
    assert.equal(requests.length, 1, "clearing must deactivate callbacks from the previous conversation");

    const newConversation = controller.activate("current", "new-conversation");
    requests[0].resolve(oldSummary);
    await oldConversation;
    assert.deepEqual(latest(), { summary: null, loading: true, error: null },
      "an old response must not repopulate cleared costs or stop the new loading state");
    requests[1].resolve(newSummary);
    await newConversation;
    assert.deepEqual(latest(), { summary: newSummary, loading: false, error: null });

    const earlierRefresh = controller.refresh();
    const laterRefresh = controller.refresh();
    assert.equal(requests[2].signal.aborted, true);
    assert.equal(new URL(requests[3].url, "http://localhost").searchParams.get("conversation_id"), "new-conversation");
    requests[3].resolve(answerSummary);
    await laterRefresh;
    requests[2].resolve(newSummary);
    await earlierRefresh;
    assert.deepEqual(latest(), { summary: answerSummary, loading: false, error: null },
      "a slower refresh must not overwrite the newer response");

    const preAnswerRefresh = controller.refresh();
    controller.accept(answerSummary);
    assert.equal(requests[4].signal.aborted, true);
    requests[4].resolve(newSummary);
    await preAnswerRefresh;
    assert.deepEqual(latest(), { summary: answerSummary, loading: false, error: null },
      "pre-answer ledger reads must not overwrite costs delivered with the answer");

    const oldFailure = controller.refresh();
    const currentRefresh = controller.refresh();
    requests[5].reject(new Error("Outdated refresh failed."));
    await oldFailure;
    assert.deepEqual(latest(), { summary: answerSummary, loading: true, error: null },
      "a superseded failure must not clear the active request's loading indicator");
    const failure = new Error("Current refresh failed.");
    requests[6].reject(failure);
    await currentRefresh;
    assert.deepEqual(latest(), { summary: answerSummary, loading: false, error: failure });

    const unmountedRefresh = controller.refresh();
    controller.dispose();
    assert.equal(requests[7].signal.aborted, true);
    const beforeUnmountedCompletion = updates.length;
    requests[7].resolve(newSummary);
    await unmountedRefresh;
    await controller.refresh();
    controller.accept(newSummary);
    assert.equal(updates.length, beforeUnmountedCompletion, "disposed requests must not update state");
    assert.equal(requests.length, 8, "disposed callbacks must not start a request");
  } finally {
    controller.dispose();
    globalThis.fetch = originalFetch;
  }
}
