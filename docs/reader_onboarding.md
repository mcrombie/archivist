# Reader onboarding

**Status:** implemented frontend presentation contract
**Scope:** first-visit orientation, replay, and the deferred Sources explanation
**Out of scope:** answer behavior, retrieval, model prompts, semantic evaluation, and analytics

## Product purpose

The landing page must explain Archivist even when a visitor skips the tour. It identifies the
application as a manuscript-grounded AI guide, names the kinds of manuscript questions it is for,
states that manuscript answers search the selected book rather than the open web, and tells the
reader that supporting passages are inspectable. Perspective copy separately explains that a mode
changes voice and emphasis rather than the manuscript being searched.

The existing guided start and the first-visit tour have different jobs:

- **How Archivist works** teaches the product's mental model.
- **Let Archivist guide me** helps a reader compose a useful question.

Neither flow sends a request, creates a conversation turn, changes a mode or setting, or incurs a
provider call.

## First-visit sequence

The public reader automatically offers an optional welcome card once per browser and tour version.
The welcome card offers **Show me around** and **Skip and explore**. The orientation then contains
three informational spotlight steps:

1. **Begin with a question.** Highlight the composer and explain free-form questions and the local
   starter flow.
2. **Perspective changes the reading.** Highlight the live Perspective note. Modes alter voice and
   interpretive emphasis; Essential displays direct cited evidence without a character voice. The
   step also tells readers that clicking Perspective after the tour opens the mode chooser.
3. **Keep the defaults—or go deeper.** Highlight Settings and make clear that every default is ready
   to use.

Finishing closes the modal and focuses the active question field. Skipping, the close control, and
Escape have the same persisted effect during automatic first-run onboarding. A replay never changes
the saved first-run disposition. **How Archivist works** remains available beside the landing
disclosure and inside Settings.

The tour is informational. Highlighted page controls are visual context only and cannot be clicked
through the modal. The tour cannot submit a question.

## Deferred Sources explanation

Sources and inline citations do not exist before an answer and are intentionally absent from some
social/persona replies. Consequently, they are not a first-run spotlight step. Completing the tour
leaves one contextual explanation pending. After the first completed turn that actually contains
sources, a non-modal note appears immediately above that turn's Sources disclosure. It explains
that citation numbers open supporting passages and that Sources contains excerpts and manuscript
locations.

Opening Sources or choosing **Got it** marks the note seen. Dismissing it marks it skipped. Skipping
the initial tour suppresses the later note entirely. The note never steals focus or interrupts
answer reading.

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
- exactly three stable spotlight targets;
- no network client or request primitive in the tour implementation;
- native modal, Escape, focus, resize, missing-target, reduced-motion, and forced-colors contracts;
- TypeScript compilation and production frontend build.

Rendered release review should additionally exercise keyboard-only use, mobile widths, zoom,
every selectable appearance, and a source-bearing answer. That visual review does not establish
model or semantic quality.
