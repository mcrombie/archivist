import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createServer } from "vite";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const tourSource = readFileSync(
  new URL("../src/OnboardingTour.tsx", import.meta.url),
  "utf8"
);
const tourCss = readFileSync(new URL("../src/onboarding.css", import.meta.url), "utf8");

const server = await createServer({
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true }
});

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

try {
  const onboarding = await server.ssrLoadModule("/src/onboarding.ts");
  await server.ssrLoadModule("/src/OnboardingTour.tsx");

  assert.match(appSource, /A manuscript-grounded AI guide/);
  assert.match(appSource, /not the open web/);
  assert.match(appSource, /How Archivist works/);
  assert.match(appSource, /openOnboardingReplay\(event\.currentTarget\)/);
  assert.match(appSource, /replayInvoker=\{onboardingInvokerRef\.current\}/);
  assert.match(appSource, /showSourcesTip=\{turn\.id === sourcesTipTurnId\}/);
  assert.match(appSource, /data-onboarding-target="sources"/);
  assert.deepEqual(
    [...appSource.matchAll(/data-onboarding-target="(ask|perspective|settings)"/g)]
      .map((match) => match[1]),
    ["ask", "perspective", "settings"],
    "the initial tour should expose exactly three stable spotlight targets"
  );

  assert.equal(
    [...tourSource.matchAll(/id: "(ask|perspective|settings)",\s+target: "\1"/g)].length,
    3,
    "the tour should contain exactly three targeted explanatory steps"
  );
  assert.match(tourSource, /dialog\.showModal\(\)/);
  assert.match(tourSource, /new ResizeObserver/);
  assert.match(tourSource, /onCancel=/);
  assert.match(tourSource, /invoker\?\.isConnected/);
  assert.match(tourSource, /replay && replayInvoker/);
  assert.match(tourSource, /Step \{numberedStep\} of \{numberedStepCount\}/);
  assert.doesNotMatch(tourSource, /\bfetch\s*\(|\baskQuestion\s*\(/);
  assert.doesNotMatch(appSource.match(/function openOnboardingReplay[\s\S]*?\n  }/)?.[0] ?? "", /askQuestion/);

  assert.match(tourCss, /@media \(max-width: 640px\)/);
  assert.match(tourCss, /@media \(forced-colors: active\)/);
  assert.match(tourCss, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(tourCss, /\.sources-onboarding-tip/);
  assert.match(tourCss, /html\[data-vibe="baron"\] \.onboarding-tour-next/);

  const initial = onboarding.initialOnboardingState();
  assert.deepEqual(initial, {
    version: 1,
    tour: "unseen",
    sourcesTip: "pending"
  });
  assert.equal(onboarding.ONBOARDING_VERSION, 1);
  assert.equal(onboarding.ONBOARDING_STORAGE_KEY, "archivist:onboarding:v1");
  assert.equal(onboarding.isOnboardingState(initial), true);
  assert.equal(onboarding.shouldAutoStartOnboarding(initial), true);
  assert.equal(onboarding.shouldRunOnboarding(initial), true);
  assert.equal(onboarding.shouldShowSourcesTip(initial), false);

  for (const invalid of [
    null,
    {},
    { version: 2, tour: "completed", sourcesTip: "pending" },
    { version: 1, tour: "unexpected", sourcesTip: "pending" },
    { version: 1, tour: "completed", sourcesTip: "unexpected" }
  ]) {
    assert.equal(onboarding.isOnboardingState(invalid), false);
    assert.deepEqual(
      onboarding.normalizeOnboardingState(invalid),
      initial,
      "invalid or differently versioned records should start the v1 orientation"
    );
  }
  assert.deepEqual(onboarding.parseOnboardingState(null), initial);
  assert.deepEqual(onboarding.parseOnboardingState("not-json"), initial);

  const completed = onboarding.completeOnboarding(initial);
  assert.deepEqual(completed, {
    version: 1,
    tour: "completed",
    sourcesTip: "pending"
  });
  assert.deepEqual(initial, {
    version: 1,
    tour: "unseen",
    sourcesTip: "pending"
  }, "pure transitions must not mutate their input");
  assert.equal(onboarding.shouldAutoStartOnboarding(completed), false);
  assert.equal(onboarding.shouldRunOnboarding(completed), false);
  assert.equal(onboarding.shouldShowSourcesTip(completed), true);

  const seen = onboarding.markSourcesTipSeen(completed);
  assert.equal(seen.sourcesTip, "seen");
  assert.equal(onboarding.shouldShowSourcesTip(seen), false);
  assert.equal(completed.sourcesTip, "pending", "marking the tip seen must not mutate its input");

  const sourceTipSkipped = onboarding.markSourcesTipSkipped(completed);
  assert.equal(sourceTipSkipped.sourcesTip, "skipped");
  assert.equal(onboarding.shouldShowSourcesTip(sourceTipSkipped), false);

  const skipped = onboarding.skipOnboarding(initial);
  assert.deepEqual(skipped, {
    version: 1,
    tour: "skipped",
    sourcesTip: "skipped"
  }, "skipping orientation must suppress the deferred source tip");
  assert.equal(onboarding.shouldAutoStartOnboarding(skipped), false);
  assert.equal(onboarding.shouldShowSourcesTip(skipped), false);

  for (const settled of [completed, seen, sourceTipSkipped, skipped]) {
    const beforeReplay = structuredClone(settled);
    assert.equal(onboarding.shouldRunOnboarding(settled, true), true);
    assert.deepEqual(
      settled,
      beforeReplay,
      "requesting a replay is transient and must not erase saved dispositions"
    );
  }
  assert.equal(
    onboarding.completeOnboarding(skipped).sourcesTip,
    "skipped",
    "finishing a replay after an earlier skip must not reactivate the deferred source tip"
  );
  assert.equal(
    onboarding.completeOnboarding(seen).sourcesTip,
    "seen",
    "finishing a replay must preserve a previously seen source tip"
  );

  const serialized = onboarding.serializeOnboardingState(completed);
  assert.deepEqual(onboarding.parseOnboardingState(serialized), completed);
  assert.deepEqual(
    onboarding.parseOnboardingState(JSON.stringify({
      version: 1,
      tour: "completed",
      sourcesTip: "pending",
      ignoredFutureField: true
    })),
    completed,
    "unknown fields must not leak into the stable stored contract"
  );

  const storage = memoryStorage({
    [onboarding.ONBOARDING_STORAGE_KEY]: onboarding.serializeOnboardingState(completed)
  });
  const store = onboarding.createOnboardingStore(storage);
  assert.deepEqual(store.read(), completed);
  const storedRead = store.read();
  storedRead.tour = "unseen";
  assert.deepEqual(store.read(), completed, "store reads must not expose mutable internal state");
  store.write(seen);
  assert.deepEqual(
    JSON.parse(storage.value(onboarding.ONBOARDING_STORAGE_KEY)),
    seen,
    "writes should persist the complete versioned record"
  );

  const noStorageStore = onboarding.createOnboardingStore(null);
  assert.deepEqual(noStorageStore.read(), initial);
  noStorageStore.write(completed);
  assert.deepEqual(
    noStorageStore.read(),
    completed,
    "an in-memory fallback should retain state when browser storage is absent"
  );

  const unreadableStore = onboarding.createOnboardingStore({
    getItem() {
      throw new Error("storage denied");
    },
    setItem() {
      throw new Error("storage denied");
    }
  });
  assert.deepEqual(unreadableStore.read(), initial);
  assert.doesNotThrow(() => unreadableStore.write(skipped));
  assert.deepEqual(
    unreadableStore.read(),
    skipped,
    "failed persistence should still retain the current page's state in memory"
  );

  const writeOnlyFailureStore = onboarding.createOnboardingStore({
    getItem() {
      return onboarding.serializeOnboardingState(completed);
    },
    setItem() {
      throw new Error("quota exceeded");
    }
  });
  assert.deepEqual(writeOnlyFailureStore.read(), completed);
  writeOnlyFailureStore.write(seen);
  assert.deepEqual(
    writeOnlyFailureStore.read(),
    seen,
    "an unsuccessful localStorage write must not roll back the in-memory state"
  );
} finally {
  await server.close();
}
