# Calibration workbench

## Route and intent

`GET /calibration` lets a reviewer choose a completed development or holdout run,
pair exactly one completed judge attempt and human label per result, and view an
advisory agreement report. It does not create labels, judge attempts, or runs.

## Primary flow

1. Select a completed run with an explicit development or holdout split.
2. Inspect the cohort trace rail before pairing any evidence.
3. Select matching judge and human evidence within each result row.
4. Build an advisory report only when all selected rows contain complete pairs.
5. Review aggregate agreement, confidence information, and disagreement links.

## Layout

- **Masthead:** concise phase label, task title, and read-only boundary.
- **Cohort trace rail:** split → rubric → judge configuration → paired evidence →
  eligibility. It is the page’s visual signature and provides the safety context
  before a report is constructed.
- **Evidence ledger:** each evaluation result is a row with two labelled native
  selects. The records stay inspectable rather than being hidden in a wizard.
- **Asymmetric report field:** aggregate statistics on the left; criterion table,
  confusion matrix, and disagreements beneath it. This focuses attention on
  evidence and uncertainty rather than a single "quality" gauge.

## States

- Empty: no eligible completed development/holdout runs; show the offline CLI
  command needed to create one.
- Run selected, no pair: explain the next evidence-selection action.
- Partial row: retain the controls, show a live count, and prevent report building.
- Invalid/mixed evidence: display the backend validation message; never coerce it.
- Valid report: clearly label it advisory only and include all known kappa/
  bootstrap caveats.
- No disagreements: explicitly say all selected criterion scores matched.

## Accessibility and responsiveness

Every select has a visible label and descriptive hint. The evidence table is inside
a labelled horizontal-scroll region on narrow screens. The trace rail becomes a
two-column grid below 760px, while report grids collapse to one column. Focus,
native disabled state, and reduced-motion preferences are all supported.
