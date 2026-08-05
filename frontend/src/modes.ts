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
  professional: {
    historiographicalLens: "evidence_first",
    voice: "plainspoken",
    worldview: "secular_humanist"
  },
  essential: {
    historiographicalLens: "evidence_first",
    voice: "scholarly",
    worldview: "none"
  },
  forest: {
    historiographicalLens: "tragic",
    voice: "romantic",
    worldview: "none"
  },
  cromb_coo_coo: {
    historiographicalLens: "evidence_first",
    voice: "romantic",
    worldview: "secular_humanist"
  },
  pretty_pink_princess: {
    historiographicalLens: "triumphalist",
    voice: "romantic",
    worldview: "secular_humanist"
  },
  baleful_black_baron: {
    historiographicalLens: "tragic",
    voice: "romantic",
    worldview: "none"
  },
  tidal_archivist: {
    historiographicalLens: "evidence_first",
    voice: "romantic",
    worldview: "none"
  },
  ember_and_ink: {
    historiographicalLens: "evidence_first",
    voice: "plainspoken",
    worldview: "enlightenment_rationalist"
  },
  illuminated_codex: {
    historiographicalLens: "evidence_first",
    voice: "scholarly",
    worldview: "secular_humanist"
  },
  cosmic_almanac: {
    historiographicalLens: "evidence_first",
    voice: "scholarly",
    worldview: "enlightenment_rationalist"
  }
} satisfies Readonly<Record<ArchivistModeId, AnswerFacets>>;

export const ARCHIVIST_MODES: ReadonlyArray<ArchivistMode> = [
  {
    id: "professional",
    label: "Professional",
    shortLabel: "Professional",
    description: "Accessible public-history framing in a crisp editorial reading room.",
    disclosure: "Reviewed methods distilled from Craven, Beard, and Du Bois guide framing; historical claims remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.professional,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.professional
  },
  {
    id: "essential",
    label: "Essential",
    shortLabel: "Essential",
    description: "The neutral scholarly baseline with no curated outside influence.",
    disclosure: "No curated outside influence is added; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.essential,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.essential
  },
  {
    id: "forest",
    label: "Mythical Forest Folio",
    shortLabel: "Forest Folio",
    description: "A tragic, romantic reading shaped by a mythopoetic forest sensibility.",
    disclosure: "Formal qualities distilled from Dunsany's The King of Elfland's Daughter guide atmosphere and framing, never historical evidence or citations.",
    appearance: ARCHIVIST_MODE_APPEARANCES.forest,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.forest
  },
  {
    id: "cromb_coo_coo",
    label: "Cromb Coo Coo",
    shortLabel: "Cromb Coo Coo",
    description: "A humane, mischievous reading alive to contingency, eccentric actors, and comic reversals.",
    disclosure: "Formal qualities distilled from the private owner-supplied manuscript Journey through Cromb Coo Coo guide framing only; historical facts and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.cromb_coo_coo,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.cromb_coo_coo
  },
  {
    id: "pretty_pink_princess",
    label: "Pretty Pink Princess",
    shortLabel: "Pink Princess",
    description: "A strongly optimistic, rose-tinted reading that never falsifies or omits harm.",
    disclosure: "A rose-tinted optimism profile shapes framing without falsifying or omitting harm; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.pretty_pink_princess,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.pretty_pink_princess
  },
  {
    id: "baleful_black_baron",
    label: "Baleful Black Baron",
    shortLabel: "Black Baron",
    description: "A severe tragic reading centered on costs, coercion, and loss.",
    disclosure: "A severe tragic profile emphasizes costs, coercion, and loss without inventing or exaggerating harm; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.baleful_black_baron,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.baleful_black_baron
  },
  {
    id: "tidal_archivist",
    label: "Tidal Archivist",
    shortLabel: "Tidal Archivist",
    description: "A Moby-Dick-informed maritime reading of scale, pressure, command, and uncertainty.",
    disclosure: "High-level maritime qualities associated with Moby-Dick guide framing without quotation, paraphrase, or imitation; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.tidal_archivist,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.tidal_archivist
  },
  {
    id: "ember_and_ink",
    label: "Ember & Ink",
    shortLabel: "Ember & Ink",
    description: "A realist statecraft reading associated with Henry Kissinger at the level of tradition, without using his works.",
    disclosure: "A high-level realist-statecraft tradition associated with Henry Kissinger guides framing without ingesting, quoting, paraphrasing, or imitating his works; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.ember_and_ink,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.ember_and_ink
  },
  {
    id: "illuminated_codex",
    label: "Illuminated Codex",
    shortLabel: "Illuminated Codex",
    description: "A modern liberal historical reading attentive to rights and dignity, pluralism, representative institutions, rule of law, reform, inclusion, toleration, and accountable power.",
    disclosure: "This profile examines gaps between ideals and access, treating progress as incremental and contested rather than automatic, without present-day party advocacy; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.illuminated_codex,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.illuminated_codex
  },
  {
    id: "cosmic_almanac",
    label: "Cosmic Almanac",
    shortLabel: "Cosmic Almanac",
    description: "A future-science historical reading attentive to long time horizons and systems: ecology and climate where supported, demography, technology, energy, infrastructure, information, and institutions.",
    disclosure: "This profile traces path dependence, feedback loops, uncertainty, and plausible futures without forecasting or inventing facts, writing science fiction, treating projections as evidence, or imposing deterministic, teleological, or anachronistic explanations; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: ARCHIVIST_MODE_APPEARANCES.cosmic_almanac,
    defaultFacets: ARCHIVIST_MODE_DEFAULT_FACETS.cosmic_almanac
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
  return (
    facets.historiographicalLens !== defaults.historiographicalLens
    || facets.voice !== defaults.voice
    || facets.worldview !== defaults.worldview
  );
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
