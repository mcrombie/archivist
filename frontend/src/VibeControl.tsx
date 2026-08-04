import { Check, ChevronDown, Palette } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { ArchivistModeId } from "./api";
import { ARCHIVIST_MODES, archivistMode } from "./modes";
import type { VibeId } from "./vibes";

function setDocumentAppearance(appearance: VibeId) {
  document.documentElement.dataset.vibe = appearance;
}

export function VibeControl({
  mode,
  appearance,
  custom,
  onModeChange,
  compact = false
}: {
  mode: ArchivistModeId;
  appearance: VibeId;
  custom: boolean;
  onModeChange: (mode: ArchivistModeId) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const pickerId = useId();
  const controlRef = useRef<HTMLDivElement>(null);
  const current = archivistMode(mode);

  useEffect(() => {
    setDocumentAppearance(appearance);
  }, [appearance]);

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

  function selectMode(nextMode: ArchivistModeId) {
    const option = archivistMode(nextMode);
    onModeChange(nextMode);
    setAnnouncement(`Archivist mode changed to ${option.label}. The new mode applies to future answers.`);
    setOpen(false);
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
          <small>Archivist mode</small>
          <strong>{current.shortLabel}{custom ? " · Custom" : ""}</strong>
        </span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>

      {open ? (
        <div className="vibe-menu" id={pickerId}>
          <div className="vibe-menu-heading">
            <span>Reading style and appearance</span>
          </div>
          <p className="vibe-menu-note">
            Modes guide framing and atmosphere. Historical claims and citations still come from
            <cite> Cradle of the Empire</cite>.
          </p>
          <div className="vibe-options" role="group" aria-label="Archivist mode">
            {ARCHIVIST_MODES.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={option.id === mode}
                className={option.id === mode ? "is-selected" : ""}
                onClick={() => selectMode(option.id)}
              >
                <i className={`vibe-swatch vibe-swatch-${option.appearance}`} aria-hidden="true" />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                {option.id === mode ? <Check size={15} aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
          <p className="vibe-mode-disclosure">{current.disclosure}</p>
          {appearance !== current.appearance ? (
            <p className="vibe-appearance-override">Advanced appearance override active.</p>
          ) : null}
        </div>
      ) : null}

      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  );
}
