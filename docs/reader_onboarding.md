# Reader onboarding

**Status:** implemented frontend presentation contract
**Scope:** first-visit orientation, replay, and the deferred Sources explanation
**Out of scope:** answer behavior, retrieval, model prompts, semantic evaluation, and analytics

## Product purpose

The landing page must explain Archivist without a tour. It names the manuscript and what the book is
about, states that manuscript answers search that book rather than the open web, and tells the
reader that supporting passages are cited. Advanced perspective settings, inside Settings,
separately explains that a perspective changes voice and emphasis rather than the manuscript being
searched.

The existing guided start and the first-visit tour have different jobs:

- **How Archivist works** teaches the product's mental model.
- **Help me choose a question** helps a reader compose a useful question.

Neither flow sends a request, creates a conversation turn, changes a mode or setting, or incurs a
provider call. The starter questions beside them behave differently: each is already a complete
question, so one click sends it.

## Orientation sequence

Nothing opens automatically. **How Archivist works** starts the orientation on request, beginning
with the welcome card and its **Show me around** and **Skip and explore** controls. The orientation
defines two informational spotlight steps and drops any whose control is not currently rendered,
so the opening screen runs only the first of them:

1. **Begin with a question.** Highlight the composer and explain free-form questions, the starter
   questions, and the local guide.
2. **Keep the defaults—or go deeper.** Highlight Settings, make clear that every default is ready to
   use, and name what it holds: a perspective, a visual theme, and answer delivery. A perspective
   changes voice and emphasis without changing the manuscript searched.

The perspective is an advanced setting, so the tour says where it lives but never spotlights the
chooser itself.

Finishing closes the modal and returns focus to the control that opened it. Because the orientation
is always opened on request, it never changes the saved disposition. **How Archivist works** sits
below the starter questions on the opening screen, and inside Settings once a conversation exists.

The tour is informational. Highlighted page controls are visual context only and cannot be clicked
through the modal. The tour cannot submit a question.

## Deferred Sources explanation

Sources and inline citations do not exist before an answer and are intentionally absent from some
social/persona replies. Consequently, they are not a spotlight step. One contextual explanation
stays pending from the first visit, whether or not the reader ever opens the orientation. After the
first completed turn that actually contains sources, a non-modal note appears immediately above that
turn's Sources disclosure. It explains that citation numbers open supporting passages and that
Sources contains excerpts and manuscript locations.

Opening Sources or choosing **Got it** marks the note seen. Dismissing it marks it skipped, and it
does not return. The note never steals focus or interrupts answer reading.

## Persistence contract

The browser stores a strict, versioned local record under `archivist:onboarding:v1`:

```text
version: 1
tour: unseen | completed | skipped
sourcesTip: pending | seen | skipped
```

Malformed, absent, or differently versioned data resolves to a new v1 state. Storage access is
wrapped in `try/catch`; when browser storage is unavailable, an in-memory copy preserves behavior
for the current page. A materially changed orientation may use a new version. Copy-only changes do
not force returning visitors through the tour again.

## Accessibility and responsive behavior

The orientation uses a native modal dialog. Focus enters the dialog, remains within it, and moves
to the visible step heading after Next or Back. Every step provides visible Back/Next or Finish and
Skip controls; Escape closes it. Automatic onboarding returns focus to the question field, while a
replay returns focus to its invoking control when that control still exists.

The page underneath is inert. The spotlight uses a visual hole and ring but never creates a
pointer-only interaction unavailable to keyboard or assistive-technology users. Missing or hidden
targets fall back to a centered explanation. Target geometry is recalculated on resize, scrolling,
and layout changes. Narrow screens use a bottom-sheet layout. Reduced-motion and forced-colors
preferences receive explicit treatment.

Stable `data-onboarding-target` attributes identify targets; layout class names are not part of the
tour contract.

## Offline acceptance checks

- strict storage parsing and pure state transitions;
- first-run completion and skip dispositions;
- replay without persistence mutation;
- source-tip eligibility and dismissal;
- exactly two stable spotlight targets, the composer and Settings;
- no network client or request primitive in the tour implementation;
- native modal, Escape, focus, resize, missing-target, reduced-motion, and forced-colors contracts;
- TypeScript compilation and production frontend build.

Rendered release review should additionally exercise keyboard-only use, mobile widths, zoom,
every selectable visual theme, and a source-bearing answer. That visual review does not establish
model or semantic quality.
