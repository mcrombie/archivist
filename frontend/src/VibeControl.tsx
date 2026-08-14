import { Check, ChevronDown, Palette, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { ArchivistModeId } from "./api";
import { ARCHIVIST_MODES, archivistMode } from "./modes";
import type { VibeId } from "./vibes";

export type VibeControlTriggerVariant = "header" | "perspective" | "settings" | "turn";

function setDocumentAppearance(appearance: VibeId) {
  document.documentElement.dataset.vibe = appearance;
}

export function VibeControl({
  mode,
  appearance,
  custom,
  onModeChange,
  compact = false,
  triggerVariant = "header",
  triggerLabel,
  triggerEyebrow,
  triggerAriaLabel,
  contextNote
}: {
  mode: ArchivistModeId;
  appearance: VibeId;
  custom: boolean;
  onModeChange: (mode: ArchivistModeId) => void;
  compact?: boolean;
  triggerVariant?: VibeControlTriggerVariant;
  triggerLabel?: string;
  triggerEyebrow?: string;
  triggerAriaLabel?: string;
  contextNote?: string;
}) {
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const pickerId = useId();
  const pickerHeadingId = `${pickerId}-heading`;
  const controlRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const current = archivistMode(mode);
  const displayLabel = triggerLabel ?? (custom ? "Custom" : current.shortLabel);
  const eyebrow = triggerEyebrow ?? "Archivist mode";
  const modalPicker = triggerVariant !== "header";
  const accessibleLabel = triggerAriaLabel
    ?? `Archivist mode: ${displayLabel}. Choose a perspective for future answers.`;

  useEffect(() => {
    setDocumentAppearance(appearance);
  }, [appearance]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideInteraction = (event: PointerEvent) => {
      if (!modalPicker && !controlRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !modalPicker) {
        event.preventDefault();
        setOpen(false);
        window.requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }));
      }
    };
    window.addEventListener("pointerdown", closeOnOutsideInteraction);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnOutsideInteraction);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [modalPicker, open]);

  useEffect(() => {
    if (!modalPicker) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [modalPicker, open]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      const root = modalPicker ? dialogRef.current : controlRef.current;
      root
        ?.querySelector<HTMLButtonElement>('.vibe-options > button[aria-pressed="true"]')
        ?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [modalPicker, mode, open]);

  function closeAndRestoreFocus() {
    setOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }));
  }

  function selectMode(nextMode: ArchivistModeId) {
    const option = archivistMode(nextMode);
    onModeChange(nextMode);
    setAnnouncement(`Archivist mode changed to ${option.label}. The new mode applies to future answers.`);
    closeAndRestoreFocus();
  }

  const pickerContent = (
    <>
      <div className="vibe-menu-heading">
        <span id={pickerHeadingId}>Choose a perspective for future answers</span>
        <button
          type="button"
          aria-label="Close perspective chooser"
          onClick={closeAndRestoreFocus}
        >
          <X size={15} aria-hidden="true" />
        </button>
      </div>
      <p className="vibe-menu-note">
        Modes guide framing and atmosphere. Their retrieved evidence packet and citations
        still come from <cite>Cradle of the Empire</cite>.
      </p>
      <p className="vibe-menu-future-note">
        Changes apply to future answers. Existing answers keep the perspective that produced them.
      </p>
      {contextNote ? <p className="vibe-menu-context">{contextNote}</p> : null}
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
    </>
  );

  return (
    <div
      ref={controlRef}
      className={`archivist-vibe-control is-${triggerVariant}${compact ? " is-compact" : ""}`}
    >
      <button
        ref={triggerRef}
        type="button"
        className={`vibe-trigger is-${triggerVariant}${custom ? " is-custom" : ""}`}
        aria-label={accessibleLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={pickerId}
        onClick={() => setOpen((value) => !value)}
      >
        {triggerVariant === "header" ? <Palette size={16} aria-hidden="true" /> : null}
        <span>
          <small>{eyebrow}</small>
          <strong>{displayLabel}</strong>
        </span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>

      {open && modalPicker ? (
        <dialog
          ref={dialogRef}
          className="vibe-picker-dialog"
          id={pickerId}
          aria-labelledby={pickerHeadingId}
          onCancel={(event) => {
            event.preventDefault();
            closeAndRestoreFocus();
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget) closeAndRestoreFocus();
          }}
        >
          <div className="vibe-menu">{pickerContent}</div>
        </dialog>
      ) : open ? (
        <div
          className="vibe-menu"
          id={pickerId}
          role="dialog"
          aria-labelledby={pickerHeadingId}
        >
          {pickerContent}
        </div>
      ) : null}

      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  );
}
