import type { AnswerFacets, ArchivistModeId } from "./api";
import { isVibeId, VIBE_STORAGE_KEY, type VibeId } from "./vibes";

export const ARCHIVIST_MODE_STORAGE_KEY = "archivist:mode";

export type ArchivistMode = {
  id: ArchivistModeId;
  label: string;
  shortLabel: string;
  description: string;
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
    description: "A polished, diplomatic Professional voice for contemporary public history.",
    disclosure: "Archivist compiles the evidence first; a single AI prose writer then answers in the Professional's measured, present-minded character.",
    appearance: ARCHIVIST_MODE_APPEARANCES.professional,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.professional
  },
  {
    id: "essential",
    label: "Essential",
    shortLabel: "Essential",
    description: "Direct, cited manuscript evidence with no prose-model rewrite.",
    disclosure: "Archivist returns its compiled evidence directly; no AI prose writer rewrites the answer.",
    appearance: ARCHIVIST_MODE_APPEARANCES.essential,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.essential
  },
  {
    id: "pretty_pink_princess",
    label: "Pretty Pink Princess",
    shortLabel: "Pink Princess",
    description: "A sparkling, rose-tinted Princess who seeks hope in the evidence.",
    disclosure: "Archivist compiles the evidence first; a single AI prose writer then speaks as the hopeful, charming Princess without inventing historical facts.",
    appearance: ARCHIVIST_MODE_APPEARANCES.pretty_pink_princess,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.pretty_pink_princess
  },
  {
    id: "baleful_black_baron",
    label: "Baleful Black Baron",
    shortLabel: "Black Baron",
    description: "A bleak, severe Baron centered on coercion, loss, and ruin.",
    disclosure: "Archivist compiles the evidence first; a single AI prose writer then speaks as the brooding, condemnatory Baron without inventing historical facts.",
    appearance: ARCHIVIST_MODE_APPEARANCES.baleful_black_baron,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.baleful_black_baron
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
