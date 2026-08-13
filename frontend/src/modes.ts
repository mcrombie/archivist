import type { AnswerFacets, ArchivistModeId } from "./api";
import { isVibeId, VIBE_STORAGE_KEY, type VibeId } from "./vibes";

export const ARCHIVIST_MODE_STORAGE_KEY = "archivist:mode";

export type ArchivistMode = {
  id: ArchivistModeId;
  label: string;
  shortLabel: string;
  description: string;
  perspective: string;
  disclosure: string;
  appearance: VibeId;
  defaultFacets: AnswerFacets;
};

// Compatibility maps retain every historical ID so stored/server data and dormant appearances
// continue to resolve. Only ARCHIVIST_MODES below is reader-selectable.
export const ARCHIVIST_MODE_APPEARANCES = {
  professional: "professional",
  essential: "minimal",
  forest: "forest",
  cromb_coo_coo: "cromb",
  pretty_pink_princess: "princess",
  baleful_black_baron: "baron",
  tidal_archivist: "ocean",
  ember_and_ink: "ember",
  illuminated_codex: "codex",
  cosmic_almanac: "whimsical"
} satisfies Readonly<Record<ArchivistModeId, VibeId>>;

export const ARCHIVIST_MODE_DEFAULT_FACETS = {
  professional: { historiographicalLens: "evidence_first", voice: "plainspoken", worldview: "secular_humanist" },
  essential: { historiographicalLens: "evidence_first", voice: "scholarly", worldview: "none" },
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
    appearance: ARCHIVIST_MODE_APPEARANCES.professional,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.professional
  },
  {
    id: "essential",
    label: "Essential",
    shortLabel: "Essential",
    description: "Direct, cited manuscript evidence with no prose-generation rewrite.",
    perspective: "No added interpretive persona: direct, cited evidence from the manuscript without a prose-generation rewrite.",
    disclosure: "Archivist returns its compiled evidence directly; no AI prose writer rewrites it into a new answer.",
    appearance: ARCHIVIST_MODE_APPEARANCES.essential,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.essential
  },
  {
    id: "pretty_pink_princess",
    label: "Pretty Pink Princess",
    shortLabel: "Pink Princess",
    description: "A sparkling Princess with hopeful charm, tiny songs, and whimsical tangents.",
    perspective: "Hopeful and triumphalist, favoring achievement and charm while avoiding subjects she finds too bleak or frightening.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Princess's distinct character, may decline material she finds too bleak or frightening, and ends with one to three follow-up questions.",
    appearance: ARCHIVIST_MODE_APPEARANCES.pretty_pink_princess,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.pretty_pink_princess
  },
  {
    id: "baleful_black_baron",
    label: "Baleful Black Baron",
    shortLabel: "Black Baron",
    description: "A bleak Gothic Baron centered on coercion, loss, ruin, and severe judgment.",
    perspective: "Tragic and severe, emphasizing coercion, loss, ruin, and human suffering.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Baron's brooding, condemnatory character and ends with one to three follow-up questions.",
    appearance: ARCHIVIST_MODE_APPEARANCES.baleful_black_baron,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.baleful_black_baron
  },
  {
    id: "ember_and_ink",
    label: "Ruthless Red Realist",
    shortLabel: "Red Realist",
    description: "A ruthless strategic realist who reads history through calculation, leverage, and constrained choice.",
    perspective: "Cold-blooded strategic calculation centered on power, leverage, incentives, tradeoffs, and statecraft; loosely inspired by Machiavelli and Kissinger without impersonating either.",
    disclosure: "Archivist assembles a rich packet of retrieved manuscript evidence; one AI response call then authors the answer in the Ruthless Red Realist's calculating character, without impersonating any historical figure, and ends with one to three follow-up questions.",
    appearance: ARCHIVIST_MODE_APPEARANCES.ember_and_ink,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.ember_and_ink
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

export function archivistModeSummary(
  modeId: ArchivistModeId,
  facets: AnswerFacets,
  appearance?: VibeId
) {
  const mode = archivistMode(modeId);
  const appearanceOverride = appearance !== undefined && appearance !== mode.appearance;
  return modeHasOverrides(modeId, facets) || appearanceOverride
    ? `${mode.label} · Custom`
    : mode.label;
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

export function storedArchivistMode(): ArchivistModeId {
  try {
    const stored = window.localStorage.getItem(ARCHIVIST_MODE_STORAGE_KEY);
    return isArchivistModeId(stored) ? stored : DEFAULT_ARCHIVIST_MODE;
  } catch {
    return DEFAULT_ARCHIVIST_MODE;
  }
}

export function persistArchivistMode(modeId: ArchivistModeId) {
  try {
    window.localStorage.setItem(ARCHIVIST_MODE_STORAGE_KEY, modeId);
  } catch {
    // The controlled mode still applies to this page when storage is unavailable.
  }
}

export function storedAppearance(modeId: ArchivistModeId): VibeId {
  try {
    const stored = window.localStorage.getItem(VIBE_STORAGE_KEY);
    return isVibeId(stored) ? stored : archivistMode(modeId).appearance;
  } catch {
    return archivistMode(modeId).appearance;
  }
}

export function persistAppearance(appearance: VibeId) {
  try {
    window.localStorage.setItem(VIBE_STORAGE_KEY, appearance);
  } catch {
    // The appearance still applies to this page when storage is unavailable.
  }
}
