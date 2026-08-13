import assert from "node:assert/strict";

import { createServer } from "vite";

const server = await createServer({
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true }
});

const originalWindow = globalThis.window;

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
  const modes = await server.ssrLoadModule("/src/modes.ts");
  const vibes = await server.ssrLoadModule("/src/vibes.ts");

  const expectedModes = {
    professional: {
      label: "Professional",
      appearance: "professional",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "plainspoken",
        worldview: "secular_humanist"
      }
    },
    essential: {
      label: "Essential",
      appearance: "minimal",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "scholarly",
        worldview: "none"
      }
    },
    pretty_pink_princess: {
      label: "Pretty Pink Princess",
      appearance: "princess",
      defaultFacets: {
        historiographicalLens: "triumphalist",
        voice: "romantic",
        worldview: "secular_humanist"
      }
    },
    baleful_black_baron: {
      label: "Baleful Black Baron",
      appearance: "baron",
      defaultFacets: {
        historiographicalLens: "tragic",
        voice: "romantic",
        worldview: "none"
      }
    },
    ember_and_ink: {
      label: "Ruthless Red Realist",
      appearance: "ember",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "plainspoken",
        worldview: "enlightenment_rationalist"
      }
    }
  };
  const expectedModeIds = Object.keys(expectedModes);
  const dormantModeIds = [
    "forest",
    "cromb_coo_coo",
    "tidal_archivist",
    "illuminated_codex",
    "cosmic_almanac"
  ];

  assert.deepEqual(
    modes.ARCHIVIST_MODES.map((mode) => mode.id),
    expectedModeIds,
    "the mode picker should expose exactly the five supported answer experiences"
  );
  assert.equal(
    new Set(modes.ARCHIVIST_MODES.map((mode) => mode.id)).size,
    modes.ARCHIVIST_MODES.length,
    "selectable mode IDs should be unique"
  );
  assert.equal(modes.DEFAULT_ARCHIVIST_MODE, "professional");

  for (const [modeId, expected] of Object.entries(expectedModes)) {
    const mode = modes.archivistMode(modeId);
    assert.equal(modes.isArchivistModeId(modeId), true, `${modeId} should be selectable`);
    assert.equal(mode.label, expected.label);
    assert.equal(mode.appearance, expected.appearance, `${modeId} should select its matching appearance`);
    assert.deepEqual(mode.defaultFacets, expected.defaultFacets, `${modeId} should expose its preset`);
    assert.equal(modes.modeHasOverrides(modeId, expected.defaultFacets), false);
  }

  for (const modeId of dormantModeIds) {
    assert.equal(modes.isArchivistModeId(modeId), false, `${modeId} should remain dormant`);
    assert.ok(modeId in modes.ARCHIVIST_MODE_APPEARANCES, `${modeId} should retain appearance compatibility`);
    assert.ok(modeId in modes.ARCHIVIST_MODE_DEFAULT_FACETS, `${modeId} should retain facet compatibility`);
  }
  assert.equal(modes.isArchivistModeId("unknown"), false);
  assert.equal(modes.isArchivistModeId(null), false);

  const essential = modes.archivistMode("essential");
  const essentialCopy = `${essential.description} ${essential.disclosure}`;
  assert.match(essentialCopy, /direct.*evidence/i, "Essential should promise direct evidence");
  assert.match(essentialCopy, /no prose-generation rewrite/i, "Essential should disclose that no prose model rewrites its evidence");
  assert.doesNotMatch(essentialCopy, /(?:no|without) (?:external )?API/i, "Essential should not imply that retrieval and embeddings make no API calls");

  const generatedCharacters = {
    professional: /Professional.*(?:measured|diplomatic|present-minded)/i,
    pretty_pink_princess: /(?:hopeful|charming).*Princess|Princess.*(?:hopeful|charming)/i,
    baleful_black_baron: /(?:brooding|condemnatory).*Baron|Baron.*(?:brooding|condemnatory)/i,
    ember_and_ink: /Ruthless Red Realist.*calculating|ruthless strategic realist.*calculation/i
  };
  for (const [modeId, characterPattern] of Object.entries(generatedCharacters)) {
    const mode = modes.archivistMode(modeId);
    assert.match(mode.disclosure, /rich packet of retrieved manuscript evidence/i, `${mode.label} should disclose its rich evidence input`);
    assert.match(mode.disclosure, /one AI response call/i, `${mode.label} should disclose its single authored response call`);
    assert.match(mode.disclosure, /one to three follow-up questions/i, `${mode.label} should promise in-character follow-up questions`);
    assert.match(`${mode.description} ${mode.disclosure}`, characterPattern, `${mode.label} should describe its distinct character`);
  }
  const perspectivePatterns = {
    professional: /measured.*diplomatic.*human agency/i,
    essential: /no added interpretive persona.*direct.*cited evidence/i,
    pretty_pink_princess: /hopeful.*triumphalist.*bleak or frightening/i,
    baleful_black_baron: /tragic.*severe.*coercion.*human suffering/i,
    ember_and_ink: /cold-blooded strategic calculation.*power.*leverage.*incentives.*tradeoffs.*statecraft.*Machiavelli.*Kissinger.*without impersonating either/i
  };
  for (const [modeId, perspectivePattern] of Object.entries(perspectivePatterns)) {
    const mode = modes.archivistMode(modeId);
    assert.match(
      mode.perspective,
      perspectivePattern,
      `${mode.label} should disclose its interpretive bias beside the question field`
    );
  }
  const princessCopy = `${modes.archivistMode("pretty_pink_princess").description} ${modes.archivistMode("pretty_pink_princess").disclosure}`;
  assert.match(princessCopy, /songs/i, "the Princess should disclose her distinctive song-like tangents");
  assert.match(princessCopy, /decline.*bleak|bleak.*decline/i, "the Princess should disclose her bleak-material boundary");

  const copiedFacets = modes.modeDefaultFacets("essential");
  assert.notEqual(copiedFacets, essential.defaultFacets, "callers should receive a copy of preset facets");
  copiedFacets.voice = "romantic";
  assert.equal(essential.defaultFacets.voice, "scholarly", "caller mutation should not alter the registry");
  assert.equal(modes.modeHasOverrides("essential", copiedFacets), true);
  assert.equal(
    modes.modeHasOverrides("essential", { ...essential.defaultFacets, worldview: "pious" }),
    true,
    "each facet dimension should participate in override detection"
  );
  assert.equal(
    modes.archivistModeSummary("professional", modes.modeDefaultFacets("professional"), "professional"),
    "Professional",
    "a preset appearance and preset facets should retain the preset label"
  );
  assert.equal(
    modes.archivistModeSummary("professional", modes.modeDefaultFacets("professional"), "princess"),
    "Professional · Custom",
    "an appearance-only override should mark the snapshotted turn as Custom"
  );
  assert.equal(
    modes.archivistModeSummary(
      "professional",
      { ...modes.modeDefaultFacets("professional"), voice: "romantic" },
      "professional"
    ),
    "Professional · Custom",
    "an interpretive-facet override should continue to mark the turn as Custom"
  );

  for (const modeId of ["professional", "pretty_pink_princess", "baleful_black_baron", "ember_and_ink"]) {
    const fallback = modes.authoredFallbackNotice("retrieval_authored_fallback", modeId);
    assert.equal(fallback.heading, "Essential fallback");
    assert.match(fallback.message, new RegExp(modes.archivistMode(modeId).label));
    assert.match(fallback.message, /Essential's direct manuscript evidence instead/);
  }
  assert.equal(
    modes.authoredFallbackNotice("retrieval_authored_fallback", "essential"),
    null,
    "an Essential response must not claim that it fell back from a generated mode"
  );
  assert.equal(
    modes.authoredFallbackNotice("retrieval_authored", "baleful_black_baron"),
    null,
    "a successful generated response must not show a fallback notice"
  );
  assert.equal(
    modes.authoredFallbackNotice("character_conversation_fallback", "pretty_pink_princess"),
    null,
    "a local in-character social fallback must not be mislabeled as Essential evidence"
  );
  assert.equal(
    modes.authoredFallbackNotice("character_conversation_fallback", "ember_and_ink"),
    null,
    "the Realist's local in-character social fallback must not be mislabeled as Essential evidence"
  );

  const expectedVibes = [
    ["professional", "Professional"],
    ["minimal", "Essential"],
    ["ember", "Ember & Ink"],
    ["princess", "Pretty Pink Princess"],
    ["baron", "Baleful Black Baron"]
  ];
  assert.deepEqual(
    vibes.VIBES.map(({ id, label }) => [id, label]),
    expectedVibes,
    "the appearance picker should expose only appearances backed by selectable answer modes"
  );
  assert.equal(new Set(vibes.VIBES.map((vibe) => vibe.id)).size, vibes.VIBES.length);
  assert.ok(
    modes.ARCHIVIST_MODES.every((mode) => vibes.VIBES.some((vibe) => vibe.id === mode.appearance)),
    "every selectable mode should map to a selectable appearance"
  );
  for (const [vibeId] of expectedVibes) assert.equal(vibes.isVibeId(vibeId), true);
  for (const vibeId of ["forest", "cromb", "whimsical", "codex", "ocean", "rose"]) {
    assert.equal(vibes.isVibeId(vibeId), false, `${vibeId} should not be restored from storage as a selectable appearance`);
  }

  assert.equal(modes.storedArchivistMode(), "professional", "SSR should fall back without window storage");
  assert.equal(modes.storedAppearance("essential"), "minimal", "SSR should use the mode appearance");

  const storage = memoryStorage({
    [modes.ARCHIVIST_MODE_STORAGE_KEY]: "pretty_pink_princess",
    [vibes.VIBE_STORAGE_KEY]: "princess"
  });
  globalThis.window = { localStorage: storage };
  assert.equal(modes.storedArchivistMode(), "pretty_pink_princess");
  assert.equal(modes.storedAppearance("professional"), "princess");
  modes.persistArchivistMode("baleful_black_baron");
  modes.persistAppearance("baron");
  assert.equal(storage.value(modes.ARCHIVIST_MODE_STORAGE_KEY), "baleful_black_baron");
  assert.equal(storage.value(vibes.VIBE_STORAGE_KEY), "baron");

  const realistStorage = memoryStorage({
    [modes.ARCHIVIST_MODE_STORAGE_KEY]: "ember_and_ink",
    [vibes.VIBE_STORAGE_KEY]: "ember"
  });
  globalThis.window = { localStorage: realistStorage };
  assert.equal(modes.storedArchivistMode(), "ember_and_ink", "the new preset should restore from storage");
  assert.equal(modes.storedAppearance("ember_and_ink"), "ember", "the Ember & Ink appearance should restore with the Realist");

  globalThis.window = {
    localStorage: memoryStorage({
      [modes.ARCHIVIST_MODE_STORAGE_KEY]: "forest",
      [vibes.VIBE_STORAGE_KEY]: "forest"
    })
  };
  assert.equal(modes.storedArchivistMode(), "professional", "a dormant stored mode should fall back safely");
  assert.equal(modes.storedAppearance("essential"), "minimal", "a dormant stored appearance should fall back to the mode");
} finally {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  await server.close();
}
