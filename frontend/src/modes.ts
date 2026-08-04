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

export const ARCHIVIST_MODES: ReadonlyArray<ArchivistMode> = [
  {
    id: "professional",
    label: "Professional",
    shortLabel: "Professional",
    description: "Accessible public-history framing in a crisp editorial reading room.",
    disclosure: "Reviewed methods distilled from Craven, Beard, and Du Bois guide framing; historical claims remain grounded in Cradle of the Empire.",
    appearance: "professional",
    defaultFacets: {
      historiographicalLens: "evidence_first",
      voice: "plainspoken",
      worldview: "secular_humanist"
    }
  },
  {
    id: "essential",
    label: "Essential",
    shortLabel: "Essential",
    description: "The neutral scholarly baseline with no curated outside influence.",
    disclosure: "No curated outside influence is added; historical claims and citations remain grounded in Cradle of the Empire.",
    appearance: "minimal",
    defaultFacets: {
      historiographicalLens: "evidence_first",
      voice: "scholarly",
      worldview: "none"
    }
  },
  {
    id: "forest",
    label: "Mythical Forest Folio",
    shortLabel: "Forest Folio",
    description: "A tragic, romantic reading shaped by a mythopoetic forest sensibility.",
    disclosure: "Formal qualities distilled from Dunsany's The King of Elfland's Daughter guide atmosphere and framing, never historical evidence or citations.",
    appearance: "forest",
    defaultFacets: {
      historiographicalLens: "tragic",
      voice: "romantic",
      worldview: "none"
    }
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
