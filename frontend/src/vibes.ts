export const VIBE_STORAGE_KEY = "archivist:vibe";
export const VIBE_CHANGE_EVENT = "archivist:vibe-change";

export const VIBES = [
  {
    id: "professional",
    label: "Professional",
    description: "A crisp editorial reading room in slate and ivory."
  },
  {
    id: "forest",
    label: "Forest Folio",
    description: "Deep greens, vellum, and botanical warmth."
  },
  {
    id: "minimal",
    label: "Essential",
    description: "Quiet monochrome with almost no ornament."
  },
  {
    id: "whimsical",
    label: "Cosmic Almanac",
    description: "Midnight blue, lavender, and celestial gold."
  },
  {
    id: "codex",
    label: "Illuminated Codex",
    description: "Archivist's original dark brass and old-paper style."
  },
  {
    id: "ember",
    label: "Ember & Ink",
    description: "Charcoal, oxblood, and burnished copper."
  },
  {
    id: "ocean",
    label: "Tidal Archive",
    description: "Deep ocean blue with sea-glass highlights."
  }
] as const;

export type VibeId = (typeof VIBES)[number]["id"];

export const DEFAULT_VIBE: VibeId = "codex";

export function isVibeId(value: unknown): value is VibeId {
  return VIBES.some((vibe) => vibe.id === value);
}
