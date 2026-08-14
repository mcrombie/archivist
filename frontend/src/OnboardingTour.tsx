import { ArrowLeft, ArrowRight, Check, Library, X } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties
} from "react";

import "./onboarding.css";

const TARGET_ATTRIBUTE = "data-onboarding-target";
const SPOTLIGHT_PADDING = 9;
const VIEWPORT_GUTTER = 8;

type TourStep = {
  id: "welcome" | "ask" | "perspective" | "settings";
  target: "ask" | "perspective" | "settings" | null;
  eyebrow: string;
  title: string;
  body: string;
};

type SpotlightRect = {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
};

type CardPosition = {
  top: number;
  left: number;
  mobileBottom: number | null;
};

type TourCardStyle = CSSProperties & {
  "--onboarding-mobile-bottom"?: string;
};

export type OnboardingTourProps = {
  open: boolean;
  projectName: string;
  replay: boolean;
  replayInvoker: HTMLElement | null;
  onComplete: () => void;
  onSkip: () => void;
  onFinishFocus: () => void;
};

function tourSteps(projectName: string, replay: boolean): ReadonlyArray<TourStep> {
  return [
    {
      id: "welcome",
      target: null,
      eyebrow: replay ? "Quick refresher" : "First visit",
      title: replay ? "How Archivist works" : "Meet Archivist",
      body: `Archivist is a guided conversation with ${projectName}. Ask about people, events, themes, or arguments. It searches this manuscript—not the open web—and shows supporting passages for manuscript answers.`
    },
    {
      id: "ask",
      target: "ask",
      eyebrow: "Ask the manuscript",
      title: "Begin with a question",
      body: "Type your own question, choose a suggested starting point, or let Archivist help shape one. Your question is not sent until you press Ask."
    },
    {
      id: "perspective",
      target: "perspective",
      eyebrow: "Choose a point of view",
      title: "Perspective changes the reading",
      body: "A mode changes the voice and interpretive emphasis—not the manuscript Archivist searches. Essential shows direct cited evidence without a character voice. After the tour, click Perspective whenever you want to choose another mode."
    },
    {
      id: "settings",
      target: "settings",
      eyebrow: "Optional controls",
      title: "Keep the defaults—or go deeper",
      body: "Settings adjust evidence scope, answer delivery, interpretive details, and appearance. The defaults are ready, so you can ignore these controls until you need them."
    }
  ];
}

function isRendered(element: HTMLElement) {
  if (element.closest("[hidden], [aria-hidden=\"true\"]")) return false;
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function viewportIntersectionArea(rect: DOMRect) {
  const width = Math.max(
    0,
    Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0)
  );
  const height = Math.max(
    0,
    Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)
  );
  return width * height;
}

/**
 * Landing and thread controls can intentionally share a target name. Prefer the
 * rendered duplicate with the greatest viewport intersection; DOM order breaks
 * ties so target selection remains deterministic while layouts settle.
 */
function findTourTarget(targetName: TourStep["target"]) {
  if (!targetName) return null;
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>(`[${TARGET_ATTRIBUTE}]`)
  ).filter((element) => (
    element.dataset.onboardingTarget === targetName && isRendered(element)
  ));

  let selected: HTMLElement | null = null;
  let selectedArea = -1;
  for (const candidate of candidates) {
    const area = viewportIntersectionArea(candidate.getBoundingClientRect());
    if (area > selectedArea) {
      selected = candidate;
      selectedArea = area;
    }
  }
  return selected;
}

function paddedTargetRect(element: HTMLElement): SpotlightRect | null {
  const raw = element.getBoundingClientRect();
  if (raw.width <= 0 || raw.height <= 0) return null;

  const left = Math.max(
    VIEWPORT_GUTTER,
    Math.floor(raw.left - SPOTLIGHT_PADDING)
  );
  const right = Math.min(
    window.innerWidth - VIEWPORT_GUTTER,
    Math.ceil(raw.right + SPOTLIGHT_PADDING)
  );
  const top = Math.max(
    VIEWPORT_GUTTER,
    Math.floor(raw.top - SPOTLIGHT_PADDING)
  );
  const bottom = Math.min(
    window.innerHeight - VIEWPORT_GUTTER,
    Math.ceil(raw.bottom + SPOTLIGHT_PADDING)
  );

  if (right <= left || bottom <= top) return null;
  return {
    top,
    right,
    bottom,
    left,
    width: right - left,
    height: bottom - top
  };
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function placeCard(
  spotlight: SpotlightRect,
  card: DOMRect
): CardPosition {
  const gap = 18;
  const gutter = 16;
  const maxLeft = Math.max(gutter, window.innerWidth - card.width - gutter);
  const centeredLeft = clamp(
    spotlight.left + (spotlight.width - card.width) / 2,
    gutter,
    maxLeft
  );
  const maxTop = Math.max(gutter, window.innerHeight - card.height - gutter);
  const centeredTop = clamp(
    spotlight.top + (spotlight.height - card.height) / 2,
    gutter,
    maxTop
  );

  let top: number;
  let left: number;
  if (window.innerHeight - spotlight.bottom >= card.height + gap + gutter) {
    top = spotlight.bottom + gap;
    left = centeredLeft;
  } else if (spotlight.top >= card.height + gap + gutter) {
    top = spotlight.top - card.height - gap;
    left = centeredLeft;
  } else if (window.innerWidth - spotlight.right >= card.width + gap + gutter) {
    top = centeredTop;
    left = spotlight.right + gap;
  } else if (spotlight.left >= card.width + gap + gutter) {
    top = centeredTop;
    left = spotlight.left - card.width - gap;
  } else {
    top = clamp((window.innerHeight - card.height) / 2, gutter, maxTop);
    left = clamp((window.innerWidth - card.width) / 2, gutter, maxLeft);
  }

  const mobileBottom = spotlight.top > window.innerHeight * 0.55
    ? Math.max(12, window.innerHeight - spotlight.top + 12)
    : null;
  return { top, left, mobileBottom };
}

function sameRect(current: SpotlightRect | null, next: SpotlightRect | null) {
  if (current === next) return true;
  if (!current || !next) return false;
  return current.top === next.top
    && current.right === next.right
    && current.bottom === next.bottom
    && current.left === next.left
    && current.width === next.width
    && current.height === next.height;
}

function samePosition(current: CardPosition | null, next: CardPosition | null) {
  if (current === next) return true;
  if (!current || !next) return false;
  return current.top === next.top
    && current.left === next.left
    && current.mobileBottom === next.mobileBottom;
}

export function OnboardingTour({
  open,
  projectName,
  replay,
  replayInvoker,
  onComplete,
  onSkip,
  onFinishFocus
}: OnboardingTourProps) {
  const steps = tourSteps(projectName, replay);
  const [stepIndex, setStepIndex] = useState(0);
  const [spotlight, setSpotlight] = useState<SpotlightRect | null>(null);
  const [cardPosition, setCardPosition] = useState<CardPosition | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const cardRef = useRef<HTMLElement>(null);
  const invokerRef = useRef<HTMLElement | null>(null);
  const activeStep = steps[stepIndex] ?? steps[0];
  const isWelcome = activeStep.id === "welcome";
  const numberedStep = Math.max(1, stepIndex);
  const numberedStepCount = steps.length - 1;
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    if (open) setStepIndex(0);
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      invokerRef.current = replay && replayInvoker
        ? replayInvoker
        : document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      dialog.showModal();
    }
    if (!open && dialog.open) dialog.close();
  }, [open, replay, replayInvoker]);

  useEffect(() => () => {
    if (dialogRef.current?.open) dialogRef.current.close();
  }, []);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => headingRef.current?.focus({
      preventScroll: true
    }));
    return () => window.cancelAnimationFrame(frame);
  }, [activeStep.id, open]);

  useEffect(() => {
    if (!open || !activeStep.target) {
      setSpotlight(null);
      setCardPosition(null);
      return;
    }

    let frame = 0;
    let observedTarget: HTMLElement | null = null;
    const observer = new ResizeObserver(() => scheduleMeasure());

    function measure() {
      frame = 0;
      const target = findTourTarget(activeStep.target);
      if (target !== observedTarget) {
        if (observedTarget) observer.unobserve(observedTarget);
        observedTarget = target;
        if (observedTarget) observer.observe(observedTarget);
      }

      const nextSpotlight = target ? paddedTargetRect(target) : null;
      setSpotlight((current) => sameRect(current, nextSpotlight) ? current : nextSpotlight);
      const cardBounds = cardRef.current?.getBoundingClientRect();
      const nextPosition = nextSpotlight && cardBounds
        ? placeCard(nextSpotlight, cardBounds)
        : null;
      setCardPosition((current) => (
        samePosition(current, nextPosition) ? current : nextPosition
      ));
    }

    function scheduleMeasure() {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(measure);
    }

    const initialTarget = findTourTarget(activeStep.target);
    if (initialTarget) {
      const bounds = initialTarget.getBoundingClientRect();
      const outsideViewport = bounds.top < VIEWPORT_GUTTER
        || bounds.bottom > window.innerHeight - VIEWPORT_GUTTER;
      if (outsideViewport) {
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        initialTarget.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: window.innerWidth <= 640 ? "start" : "center",
          inline: "nearest"
        });
      }
    }

    if (cardRef.current) observer.observe(cardRef.current);
    window.addEventListener("resize", scheduleMeasure);
    window.addEventListener("scroll", scheduleMeasure, true);
    window.visualViewport?.addEventListener("resize", scheduleMeasure);
    window.visualViewport?.addEventListener("scroll", scheduleMeasure);
    scheduleMeasure();

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", scheduleMeasure);
      window.removeEventListener("scroll", scheduleMeasure, true);
      window.visualViewport?.removeEventListener("resize", scheduleMeasure);
      window.visualViewport?.removeEventListener("scroll", scheduleMeasure);
    };
  }, [activeStep.target, open]);

  function finish(callback: () => void) {
    const invoker = invokerRef.current;
    const restoreInvoker = replay;
    if (dialogRef.current?.open) dialogRef.current.close();
    callback();
    window.requestAnimationFrame(() => {
      if (restoreInvoker) {
        if (invoker?.isConnected) invoker.focus({ preventScroll: true });
        return;
      }
      onFinishFocus();
    });
  }

  function skip() {
    finish(onSkip);
  }

  function advance() {
    if (isLastStep) {
      finish(onComplete);
      return;
    }
    setStepIndex((current) => Math.min(steps.length - 1, current + 1));
  }

  const cardStyle: TourCardStyle | undefined = cardPosition
    ? {
        top: cardPosition.top,
        left: cardPosition.left,
        ...(cardPosition.mobileBottom === null
          ? {}
          : { "--onboarding-mobile-bottom": `${cardPosition.mobileBottom}px` })
      }
    : undefined;

  return (
    <dialog
      ref={dialogRef}
      className="onboarding-tour-dialog"
      aria-labelledby="onboarding-tour-title"
      aria-describedby="onboarding-tour-description"
      onCancel={(event) => {
        event.preventDefault();
        skip();
      }}
    >
      {spotlight ? (
        <>
          <span
            className="onboarding-tour-dim is-top"
            style={{ height: spotlight.top }}
            aria-hidden="true"
          />
          <span
            className="onboarding-tour-dim is-bottom"
            style={{ top: spotlight.bottom }}
            aria-hidden="true"
          />
          <span
            className="onboarding-tour-dim is-left"
            style={{
              top: spotlight.top,
              width: spotlight.left,
              height: spotlight.height
            }}
            aria-hidden="true"
          />
          <span
            className="onboarding-tour-dim is-right"
            style={{
              top: spotlight.top,
              left: spotlight.right,
              height: spotlight.height
            }}
            aria-hidden="true"
          />
          <span
            className="onboarding-tour-spotlight"
            style={{
              top: spotlight.top,
              left: spotlight.left,
              width: spotlight.width,
              height: spotlight.height
            }}
            aria-hidden="true"
          />
        </>
      ) : (
        <span className="onboarding-tour-dim is-full" aria-hidden="true" />
      )}

      <article
        ref={cardRef}
        className={`onboarding-tour-card${spotlight && cardPosition ? " is-positioned" : " is-centered"}`}
        style={cardStyle}
      >
        <header className="onboarding-tour-header">
          <span className="onboarding-tour-mark" aria-hidden="true">
            <Library size={18} />
          </span>
          <div>
            <p>{activeStep.eyebrow}</p>
            <h2 id="onboarding-tour-title" ref={headingRef} tabIndex={-1}>
              {!isWelcome ? (
                <span className="sr-only">
                  Step {numberedStep} of {numberedStepCount}.{" "}
                </span>
              ) : null}
              {activeStep.title}
            </h2>
          </div>
          <button
            type="button"
            className="onboarding-tour-close"
            aria-label={replay ? "Close tour" : "Skip tour"}
            onClick={skip}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <p className="onboarding-tour-description" id="onboarding-tour-description">
          {activeStep.body}
        </p>

        {isWelcome ? (
          <ul className="onboarding-tour-summary" aria-label="Archivist at a glance">
            <li><Check size={14} aria-hidden="true" /> One manuscript</li>
            <li><Check size={14} aria-hidden="true" /> Inspectable sources</li>
            <li><Check size={14} aria-hidden="true" /> Optional perspectives</li>
          </ul>
        ) : null}

        <footer className="onboarding-tour-footer">
          <span className="onboarding-tour-progress">
            {isWelcome ? "30-second orientation" : `${numberedStep} of ${numberedStepCount}`}
          </span>
          <div className="onboarding-tour-actions">
            <button type="button" className="onboarding-tour-skip" onClick={skip}>
              {replay ? "Close" : isWelcome ? "Skip and explore" : "Skip tour"}
            </button>
            {!isWelcome ? (
              <button
                type="button"
                className="onboarding-tour-back"
                onClick={() => setStepIndex((current) => Math.max(0, current - 1))}
              >
                <ArrowLeft size={15} aria-hidden="true" />
                Back
              </button>
            ) : null}
            <button type="button" className="onboarding-tour-next" onClick={advance}>
              {isWelcome
                ? "Show me around"
                : isLastStep
                  ? "Start exploring"
                  : "Next"}
              {isLastStep
                ? <Check size={15} aria-hidden="true" />
                : <ArrowRight size={15} aria-hidden="true" />}
            </button>
          </div>
        </footer>
      </article>
    </dialog>
  );
}

export default OnboardingTour;
