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
    }
  };
  const expectedModeIds = Object.keys(expectedModes);
  const dormantModeIds = [
    "forest",
    "cromb_coo_coo",
    "tidal_archivist",
    "ember_and_ink",
    "illuminated_codex",
    "cosmic_almanac"
  ];

  assert.deepEqual(
    modes.ARCHIVIST_MODES.map((mode) => mode.id),
    expectedModeIds,
    "the mode picker should expose exactly the four supported answer experiences"
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
  assert.match(essentialCopy, /no prose-model/i, "Essential should disclose that no prose model writes its answer");
  assert.doesNotMatch(essentialCopy, /(?:no|without) (?:external )?API/i, "Essential should not imply that retrieval and embeddings make no API calls");

  const generatedCharacters = {
    professional: /Professional.*(?:measured|diplomatic|present-minded)/i,
    pretty_pink_princess: /(?:hopeful|charming).*Princess|Princess.*(?:hopeful|charming)/i,
    baleful_black_baron: /(?:brooding|condemnatory).*Baron|Baron.*(?:brooding|condemnatory)/i
  };
  for (const [modeId, characterPattern] of Object.entries(generatedCharacters)) {
    const mode = modes.archivistMode(modeId);
    assert.match(mode.disclosure, /single AI prose writer/i, `${mode.label} should disclose its single prose writer`);
    assert.match(`${mode.description} ${mode.disclosure}`, characterPattern, `${mode.label} should describe its distinct character`);
  }

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

  const expectedVibes = [
    ["professional", "Professional"],
    ["minimal", "Essential"],
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
  for (const vibeId of ["forest", "cromb", "whimsical", "codex", "ember", "ocean", "rose"]) {
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
