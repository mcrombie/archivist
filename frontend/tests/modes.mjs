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

  const expectedModeIds = [
    "professional",
    "essential",
    "forest",
    "cromb_coo_coo",
    "pretty_pink_princess",
    "baleful_black_baron",
    "tidal_archivist",
    "ember_and_ink",
    "illuminated_codex",
    "cosmic_almanac"
  ];
  const expectedNewModes = {
    pretty_pink_princess: {
      appearance: "princess",
      defaultFacets: {
        historiographicalLens: "triumphalist",
        voice: "romantic",
        worldview: "secular_humanist"
      }
    },
    baleful_black_baron: {
      appearance: "baron",
      defaultFacets: {
        historiographicalLens: "tragic",
        voice: "romantic",
        worldview: "none"
      }
    },
    tidal_archivist: {
      appearance: "ocean",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "romantic",
        worldview: "none"
      }
    },
    ember_and_ink: {
      appearance: "ember",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "plainspoken",
        worldview: "enlightenment_rationalist"
      }
    },
    illuminated_codex: {
      appearance: "codex",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "scholarly",
        worldview: "secular_humanist"
      }
    },
    cosmic_almanac: {
      appearance: "whimsical",
      defaultFacets: {
        historiographicalLens: "evidence_first",
        voice: "scholarly",
        worldview: "enlightenment_rationalist"
      }
    }
  };

  assert.deepEqual(
    modes.ARCHIVIST_MODES.map((mode) => mode.id),
    expectedModeIds,
    "the semantic mode picker should expose the complete ordered registry"
  );
  assert.equal(
    new Set(modes.ARCHIVIST_MODES.map((mode) => mode.id)).size,
    modes.ARCHIVIST_MODES.length,
    "semantic mode IDs should be unique"
  );

  for (const [modeId, expected] of Object.entries(expectedNewModes)) {
    const mode = modes.archivistMode(modeId);
    assert.equal(mode.appearance, expected.appearance, `${modeId} should select its legacy theme`);
    assert.deepEqual(mode.defaultFacets, expected.defaultFacets, `${modeId} should expose its preset`);
    assert.equal(modes.modeHasOverrides(modeId, expected.defaultFacets), false);
  }

  assert.deepEqual(modes.modeDefaultFacets("essential"), {
    historiographicalLens: "evidence_first",
    voice: "scholarly",
    worldview: "none"
  });
  assert.equal(modes.ARCHIVIST_MODE_APPEARANCES.essential, "minimal");
  assert.equal(modes.DEFAULT_ARCHIVIST_MODE, "professional");

  const illuminatedCodex = modes.archivistMode("illuminated_codex");
  assert.equal(illuminatedCodex.label, "Illuminated Codex");
  assert.equal(illuminatedCodex.shortLabel, "Illuminated Codex");
  assert.match(illuminatedCodex.description, /rights and dignity.*pluralism.*representative institutions.*rule of law.*reform.*inclusion.*toleration.*accountable power/i);
  assert.match(illuminatedCodex.disclosure, /gaps between ideals and access.*incremental and contested rather than automatic.*without present-day party advocacy/i);

  const cosmicAlmanac = modes.archivistMode("cosmic_almanac");
  assert.equal(cosmicAlmanac.label, "Cosmic Almanac");
  assert.equal(cosmicAlmanac.shortLabel, "Cosmic Almanac");
  assert.match(cosmicAlmanac.description, /future-science.*long time horizons.*systems.*ecology and climate where supported.*demography.*technology.*energy.*infrastructure.*information.*institutions/i);
  assert.match(cosmicAlmanac.disclosure, /path dependence.*feedback loops.*uncertainty.*plausible futures.*without forecasting or inventing facts.*writing science fiction.*treating projections as evidence.*deterministic.*teleological.*anachronistic/i);

  const vibeIds = vibes.VIBES.map((vibe) => vibe.id);
  assert.deepEqual(vibeIds, [
    "professional",
    "forest",
    "cromb",
    "minimal",
    "whimsical",
    "codex",
    "ember",
    "ocean",
    "princess",
    "baron",
    "rose"
  ]);
  assert.ok(
    modes.ARCHIVIST_MODES.every((mode) => vibeIds.includes(mode.appearance)),
    "every semantic mode should map to an appearance still offered by the legacy picker"
  );
} finally {
  await server.close();
}
