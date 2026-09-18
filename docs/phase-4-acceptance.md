# Phase 4 browser acceptance

Phase 4 is complete only after the final PR is merged and this browser check passes
against a local database containing two compatible completed runs.

1. Open `/compare`, use only the keyboard to select baseline and candidate, and
   submit. Confirm the focus indicator remains visible.
2. At 375px and desktop width, confirm there is no page-level horizontal overflow;
   data tables may scroll inside their labeled regions.
3. Filter **Regressed**, open one example, confirm both outputs and scorer evidence
   wrap safely, then use **Back to comparison**.
4. Open `/leaderboard`. Confirm the exact table is usable without the SVG, unknown
   costs say **Unknown**, and frontier/dominated states have text labels and distinct
   marker shapes.
5. Confirm run detail, comparison, leaderboard, and drill-down load in
   `DEMO_READ_ONLY=true` mode without creating or changing database rows.

Record the date, browser, viewport, and any defect in the PR before merging. Do not
mark Phase 4 complete or begin Phase 5 if a required check fails.
