import assert from "node:assert/strict";

import { createServer } from "vite";

const server = await createServer({
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true }
});

try {
  const modes = await server.ssrLoadModule("/src/modes.ts");
  const vibes = await server.ssrLoadModule("/src/vibes.ts");

  const expectedModes = {
    professional: {
      label: "Professional",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "plainspoken",
        worldview: "secular_humanist"
      }
    },
    essential: {
      label: "Essential",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "scholarly",
        worldview: "none"
      }
    },
    classical_chronicler: {
      label: "Classical Chronicler",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "scholarly",
        worldview: "none"
      }
    },
    pollyanna: {
      label: "Perky Pollyanna",
      defaultFacets: {
        historiographicalLens: "triumphalist",
        voice: "plainspoken",
        worldview: "none"
      }
    },
    doomsayer: {
      label: "Dour Doomsayer",
      defaultFacets: {
        historiographicalLens: "tragic",
        voice: "plainspoken",
        worldview: "none"
      }
    }
  };
  const expectedModeIds = Object.keys(expectedModes);
  const dormantModeIds = [
    "pretty_pink_princess",
    "baleful_black_baron",
    "ember_and_ink",
    "forest",
    "cromb_coo_coo",
    "tidal_archivist",
    "illuminated_codex",
    "cosmic_almanac"
  ];

  assert.deepEqual(
    modes.ARCHIVIST_MODES.map((mode) => mode.id),
    expectedModeIds,
    "the perspective list should expose exactly the five supported answer experiences"
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
    assert.equal("appearance" in mode, false, `${modeId} should not choose a visual theme`);
    assert.deepEqual(mode.defaultFacets, expected.defaultFacets, `${modeId} should expose its preset`);
    assert.equal(modes.modeHasOverrides(modeId, expected.defaultFacets), false);
  }

  for (const modeId of dormantModeIds) {
    assert.equal(modes.isArchivistModeId(modeId), false, `${modeId} should remain dormant`);
    assert.ok(modeId in modes.ARCHIVIST_MODE_DEFAULT_FACETS, `${modeId} should retain facet compatibility`);
  }
  assert.equal(
    "ARCHIVIST_MODE_APPEARANCES" in modes,
    false,
    "perspectives should no longer map to visual themes"
  );
  assert.equal(modes.isArchivistModeId("unknown"), false);
  assert.equal(modes.isArchivistModeId(null), false);

  const essential = modes.archivistMode("essential");
  const essentialCopy = `${essential.description} ${essential.disclosure}`;
  assert.match(essentialCopy, /direct.*evidence/i, "Essential should promise direct evidence");
  assert.match(essentialCopy, /no prose-generation rewrite/i, "Essential should disclose that no prose model rewrites its evidence");
  assert.doesNotMatch(essentialCopy, /(?:no|without) (?:external )?API/i, "Essential should not imply that retrieval and embeddings make no API calls");

  const generatedCharacters = {
    professional: /Professional.*(?:measured|diplomatic|present-minded)/i,
    classical_chronicler: /Chronicler.*narrative|narrative historian.*causes/i,
    pollyanna: /optimist.*resilience|Pollyanna.*hopeful/i,
    doomsayer: /pessimist.*fragility|Doomsayer.*gloomy/i
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
    classical_chronicler: /narrative.*evidence-first.*causes.*testimony.*character/i,
    pollyanna: /hopeful.*resilience.*harm/i,
    doomsayer: /pessimistic.*fragility.*achievement/i
  };
  for (const [modeId, perspectivePattern] of Object.entries(perspectivePatterns)) {
    const mode = modes.archivistMode(modeId);
    assert.match(
      mode.perspective,
      perspectivePattern,
      `${mode.label} should disclose its interpretive bias`
    );
  }
  const chroniclerCopy = `${modes.archivistMode("classical_chronicler").description} ${modes.archivistMode("classical_chronicler").disclosure}`;
  assert.match(chroniclerCopy, /causes/i, "the Chronicler should disclose its attention to causes");
  assert.match(chroniclerCopy, /testimony|character/i, "the Chronicler should disclose its narrative-historian frame");

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
    modes.archivistModeSummary("professional", modes.modeDefaultFacets("professional")),
    "Professional",
    "preset facets should retain the preset label"
  );
  assert.equal(
    modes.archivistModeSummary(
      "professional",
      { ...modes.modeDefaultFacets("professional"), voice: "romantic" }
    ),
    "Professional · Custom",
    "an interpretive-facet override should mark the turn as Custom"
  );

  for (const modeId of ["professional", "classical_chronicler", "pollyanna", "doomsayer"]) {
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
    ["cradle", "Cradle of the Empire"],
    ["professional", "Professional"],
    ["minimal", "Essential"],
    ["forest", "Forest Folio"],
    ["codex", "Illuminated Codex"],
    ["ember", "Ember & Ink"],
    ["ocean", "Tidal Archive"],
    ["whimsical", "Cosmic Almanac"],
    ["princess", "Pretty Pink Princess"],
    ["baron", "Baleful Black Baron"],
    ["rose", "Rose & Ruin"],
    ["cromb", "Cromb Coo Coo"]
  ];
  assert.deepEqual(
    vibes.VIBES.map(({ id, label }) => [id, label]),
    expectedVibes,
    "every finished visual theme should be offered under its original name"
  );
  assert.equal(new Set(vibes.VIBES.map((vibe) => vibe.id)).size, vibes.VIBES.length);
  assert.equal(vibes.DEFAULT_VIBE, "cradle", "Archivist should open in the book's own theme");
  for (const [vibeId] of expectedVibes) assert.equal(vibes.isVibeId(vibeId), true);
  assert.equal(vibes.isVibeId("unknown"), false);

  for (const removed of ["storedArchivistMode", "persistArchivistMode", "storedAppearance", "persistAppearance"]) {
    assert.equal(
      removed in modes,
      false,
      `${removed} should not exist: the perspective is a per-visit advanced setting`
    );
  }
} finally {
  await server.close();
}
