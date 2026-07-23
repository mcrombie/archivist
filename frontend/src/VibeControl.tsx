import { Check, ChevronDown, Palette, RefreshCw } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import {
  DEFAULT_VIBE,
  isVibeId,
  VIBES,
  VIBE_CHANGE_EVENT,
  VIBE_STORAGE_KEY,
  type VibeId
} from "./vibes";

function setDocumentVibe(vibe: VibeId) {
  document.documentElement.dataset.vibe = vibe;
  window.dispatchEvent(new CustomEvent(VIBE_CHANGE_EVENT, { detail: vibe }));
}

export function VibeControl({ compact = false }: { compact?: boolean }) {
  const [vibe, setVibe] = useState<VibeId>(() => {
    const documentVibe = document.documentElement.dataset.vibe;
    return isVibeId(documentVibe) ? documentVibe : DEFAULT_VIBE;
  });
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const pickerId = useId();
  const controlRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const syncStoredVibe = (event: StorageEvent) => {
      if (event.key !== VIBE_STORAGE_KEY) return;
      const nextVibe = isVibeId(event.newValue) ? event.newValue : DEFAULT_VIBE;
      setDocumentVibe(nextVibe);
      setVibe(nextVibe);
    };
    const syncVisibleVibe = (event: Event) => {
      const nextVibe = (event as CustomEvent<unknown>).detail;
      if (isVibeId(nextVibe)) setVibe(nextVibe);
    };

    window.addEventListener("storage", syncStoredVibe);
    window.addEventListener(VIBE_CHANGE_EVENT, syncVisibleVibe);
    return () => {
      window.removeEventListener("storage", syncStoredVibe);
      window.removeEventListener(VIBE_CHANGE_EVENT, syncVisibleVibe);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideInteraction = (event: PointerEvent) => {
      if (!controlRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", closeOnOutsideInteraction);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnOutsideInteraction);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const current = VIBES.find((option) => option.id === vibe) ?? VIBES[0];
  const currentIndex = VIBES.findIndex((option) => option.id === current.id);
  const next = VIBES[(currentIndex + 1) % VIBES.length] ?? VIBES[0];

  function applyVibe(nextVibe: VibeId) {
    const option = VIBES.find((candidate) => candidate.id === nextVibe) ?? VIBES[0];
    setDocumentVibe(option.id);
    setVibe(option.id);
    setAnnouncement(`Appearance changed to ${option.label}.`);
    try {
      window.localStorage.setItem(VIBE_STORAGE_KEY, option.id);
    } catch {
      // The selected appearance still applies for this page when storage is unavailable.
    }
  }

  return (
    <div ref={controlRef} className={`archivist-vibe-control${compact ? " is-compact" : ""}`}>
      <button
        type="button"
        className="vibe-trigger"
        aria-expanded={open}
        aria-controls={pickerId}
        onClick={() => setOpen((value) => !value)}
      >
        <Palette size={16} aria-hidden="true" />
        <span>
          <small>Change vibe</small>
          <strong>{current.label}</strong>
        </span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>

      {open ? (
        <div className="vibe-menu" id={pickerId}>
          <div className="vibe-menu-heading">
            <span>Appearance only</span>
            <button
              type="button"
              onClick={() => applyVibe(next.id)}
              title={`Try ${next.label}`}
              aria-label={`Cycle to ${next.label}`}
            >
              <RefreshCw size={14} aria-hidden="true" />
              Next
            </button>
          </div>
          <div className="vibe-options" role="group" aria-label="Archivist appearance">
            {VIBES.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={option.id === vibe}
                className={option.id === vibe ? "is-selected" : ""}
                onClick={() => {
                  applyVibe(option.id);
                  setOpen(false);
                }}
              >
                <i className={`vibe-swatch vibe-swatch-${option.id}`} aria-hidden="true" />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                {option.id === vibe ? <Check size={15} aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  );
}
