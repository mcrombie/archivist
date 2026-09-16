import type { AnswerFacets, ArchivistModeId } from "./api";

export type ArchivistMode = {
  id: ArchivistModeId;
  label: string;
  shortLabel: string;
  description: string;
  perspective: string;
  disclosure: string;
  defaultFacets: AnswerFacets;
};

// The facet map retains every historical ID so stored or server-reported modes continue to
// resolve. Only ARCHIVIST_MODES below is reader-selectable. A perspective never chooses the
// visual theme; that is a separate setting.
export const ARCHIVIST_MODE_DEFAULT_FACETS = {
  professional: { historiographicalLens: "evidence_first", voice: "plainspoken", worldview: "secular_humanist" },
  essential: { historiographicalLens: "evidence_first", voice: "scholarly", worldview: "none" },
  classical_chronicler: { historiographicalLens: "evidence_first", voice: "scholarly", worldview: "none" },
  pollyanna: { historiographicalLens: "triumphalist", voice: "plainspoken", worldview: "none" },
  doomsayer: { historiographicalLens: "tragic", voice: "plainspoken", worldview: "none" },
  forest: { historiographicalLens: "tragic", voice: "romantic", worldview: "none" },
  cromb_coo_coo: { historiographicalLens: "evidence_first", voice: "romantic", worldview: "secular_humanist" },
  pretty_pink_princess: { historiographicalLens: "triumphalist", voice: "romantic", worldview: "secular_humanist" },
  baleful_black_baron: { historiographicalLens: "tragic", voice: "romantic", worldview: "none" },
  tidal_archivist: { historiographicalLens: "evidence_first", voice: "romantic", worldview: "none" },
  ember_and_ink: { historiographicalLens: "evidence_first", voice: "plainspoken", worldview: "enlightenment_rationalist" },
  illuminated_codex: { historiographicalLens: "evidence_first", voice: "scholarly", worldview: "secular_humanist" },
  cosmic_almanac: { historiographicalLens: "evidence_first", voice: "scholarly", worldview: "enlightenment_rationalist" }
} satisfies Readonly<Record<ArchivistModeId, AnswerFacets>>;

export const ARCHIVIST_MODES: ReadonlyArray<ArchivistMode> = [
  {
    id: "professional",
    label: "Professional",
    shortLabel: "Professional",
    description: "A polished, diplomatic historian who gives substantive, present-minded answers.",
    perspective: "Measured and diplomatic, with a present-minded focus on human agency, institutions, and material consequences.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Professional's measured character and ends with one to three follow-up questions.",
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.professional
  },
  {
    id: "essential",
    label: "Essential",
    shortLabel: "Essential",
    description: "Direct, cited manuscript evidence with no prose-generation rewrite.",
    perspective: "No added interpretive persona: direct, cited evidence from the manuscript without a prose-generation rewrite.",
    disclosure: "Archivist returns its compiled evidence directly; no AI prose writer rewrites it into a new answer.",
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.essential
  },
  {
    id: "classical_chronicler",
    label: "Classical Chronicler",
    shortLabel: "Chronicler",
    description: "A narrative historian attentive to causes, testimony, character, and the longer arc.",
    perspective: "Narrative and evidence-first, attentive to causes, the limits of testimony, human character, and the long arc a single episode sits inside.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Chronicler's narrative character and ends with one to three follow-up questions.",
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.classical_chronicler
  },
  {
    id: "pollyanna",
    label: "Perky Pollyanna",
    shortLabel: "Pollyanna",
    description: "An irrepressible optimist who looks first for resilience, ingenuity, and recovery.",
    perspective: "Hopeful and optimistic, drawn to resilience, reform, and recovery while still stating harm and failure plainly.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Pollyanna's hopeful character and ends with one to three follow-up questions.",
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.pollyanna
  },
  {
    id: "doomsayer",
    label: "Dour Doomsayer",
    shortLabel: "Doomsayer",
    description: "A gloomy pessimist who looks first for fragility, overreach, and warnings ignored.",
    perspective: "Pessimistic and wary, drawn to fragility, overreach, and deferred costs while still crediting real achievement.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Doomsayer's gloomy character and ends with one to three follow-up questions.",
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.doomsayer
  }
];

export const DEFAULT_ARCHIVIST_MODE: ArchivistModeId = "professional";

export function isArchivistModeId(value: unknown): value is ArchivistModeId {
  return ARCHIVIST_MODES.some((mode) => mode.id === value);
}

export function archivistMode(modeId: ArchivistModeId): ArchivistMode {
  return ARCHIVIST_MODES.find((mode) => mode.id === modeId) ?? ARCHIVIST_MODES[0];
}

export function modeDefaultFacets(modeId: ArchivistModeId): AnswerFacets {
  return { ...archivistMode(modeId).defaultFacets };
}

export function modeHasOverrides(modeId: ArchivistModeId, facets: AnswerFacets) {
  const defaults = archivistMode(modeId).defaultFacets;
  return facets.historiographicalLens !== defaults.historiographicalLens
    || facets.voice !== defaults.voice
    || facets.worldview !== defaults.worldview;
}

export function archivistModeSummary(modeId: ArchivistModeId, facets: AnswerFacets) {
  const mode = archivistMode(modeId);
  return modeHasOverrides(modeId, facets) ? `${mode.label} · Custom` : mode.label;
}

export function authoredFallbackNotice(
  answerStatus: string | null | undefined,
  modeId: ArchivistModeId
) {
  if (answerStatus !== "retrieval_authored_fallback" || modeId === "essential") {
    return null;
  }
  return {
    heading: "Essential fallback",
    message: `Archivist could not complete the ${archivistMode(modeId).label} AI response, so it returned Essential's direct manuscript evidence instead.`
  };
}
