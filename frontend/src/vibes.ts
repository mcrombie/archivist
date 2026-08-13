export const VIBE_STORAGE_KEY = "archivist:vibe";
export const VIBE_CHANGE_EVENT = "archivist:vibe-change";

const VIBE_CATALOG = [
  { id: "professional", label: "Professional", description: "A crisp editorial reading room in slate and ivory." },
  { id: "forest", label: "Forest Folio", description: "Deep greens, vellum, and botanical warmth." },
  { id: "cromb", label: "Cromb Coo Coo", description: "Plum twilight, goblin green, cloud cream, and cheerful disorder." },
  { id: "minimal", label: "Essential", description: "Quiet monochrome with almost no ornament." },
  { id: "whimsical", label: "Cosmic Almanac", description: "Midnight blue, lavender, and celestial gold." },
  { id: "codex", label: "Illuminated Codex", description: "Archivist's original dark brass and old-paper style." },
  { id: "ember", label: "Ember & Ink", description: "Charcoal, oxblood, and burnished copper." },
  { id: "ocean", label: "Tidal Archive", description: "Deep ocean blue with sea-glass highlights." },
  { id: "princess", label: "Pretty Pink Princess", description: "Blush parchment, pearl light, and a little royal sparkle." },
  { id: "baron", label: "Baleful Black Baron", description: "Oxblood, iron, and a severe gothic reading chamber." },
  { id: "rose", label: "Rose & Ruin", description: "Dusty rose and black velvet finished in champagne gold." }
] as const;

export type VibeId = (typeof VIBE_CATALOG)[number]["id"];

const SELECTABLE_VIBE_IDS = new Set<VibeId>([
  "professional",
  "minimal",
  "princess",
  "baron"
]);

// Retain dormant appearance definitions and CSS for later modes, but do not present a visual
// theme as a choice until it has distinct answer behavior.
export const VIBES = VIBE_CATALOG.filter((vibe) => SELECTABLE_VIBE_IDS.has(vibe.id));

export const DEFAULT_VIBE: VibeId = "professional";

export function isVibeId(value: unknown): value is VibeId {
  return VIBES.some((vibe) => vibe.id === value);
}
