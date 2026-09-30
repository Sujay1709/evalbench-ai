# EvalBench interface direction

## Product register

EvalBench is a reproducible LLM evaluation and regression platform. The interface
must help an evaluator explain *why* a judgment is trustworthy, not simply show a
large score. This slice keeps the working Flask/Jinja stack and adds an interactive
calibration workbench; it is not the separate React/Vite migration.

## Locked visual language

- **Character:** a restrained industrial evidence console: dense, calm, legible,
  and intentionally closer to a lab notebook than a marketing dashboard.
- **Signature element:** the horizontal cohort trace rail. It exposes split,
  rubric, judge configuration, evidence count, and eligibility in one compact,
  persistent sequence.
- **Palette:** deep blue-black structural surfaces, light technical text, a single
  teal action accent (`#39b8a7`), and semantic success/warning/danger colors.
  Gradients, purple "AI" glows, and per-component arbitrary colors are excluded.
- **Type:** IBM Plex Sans for prose and controls; IBM Plex Mono for run IDs,
  hashes, scores, and matrices. Local/system fallbacks preserve offline operation.
- **Geometry:** four-pixel spacing rhythm; small 8px control rounding and larger
  16px panel rounding. Borders communicate structure; shadows are minimal.
- **Motion:** short opacity/border transitions only, with a full reduced-motion
  fallback. Motion may never hide state changes.

## System constraints

- Semantic CSS tokens are the sole color source for new components.
- Every state has text and structural cues; color is never the only signal.
- Forms retain selected values and show errors next to the affected evidence
  workflow. Native controls preserve keyboard and assistive-technology behavior.
- No remote font, icon, or analytics dependency is needed for the demo.

## Implementation boundary

The calibration workbench is read-only. It constructs an explicit cohort from
existing append-only judge and human evidence, calls no provider, and never changes
an evaluation result or release decision.
