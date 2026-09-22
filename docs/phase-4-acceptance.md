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

## Acceptance record — September 21, 2026

**Result: passed.** Tested in the Codex in-app browser against an isolated local
SQLite database, not Supabase. The database contained three compatible completed
automotive development-split runs (three examples each): a correct offline mock
baseline, an intentionally regressed offline candidate with long, HTML-like output,
and a candidate with unknown cost. No model API calls were made.

- **Keyboard:** Selected the baseline and regressed candidate using Tab, Space,
  arrow keys, and Return; submitted the comparison with Return. The focused select
  and button displayed a visible accent outline.
- **Responsive layout:** At effective 375 × 812 and 1280 × 800 CSS-pixel viewports,
  `/compare`, `/compare/example`, `/leaderboard`, and `/runs/<id>` had document
  scroll width equal to viewport width. At 375px, the comparison and leaderboard
  tables scrolled only inside their labeled regions.
- **Regression evidence:** The Regressed filter showed three examples. Opening
  `auto-001` displayed both outputs and scorer evidence; long unbroken output and
  evidence wrapped without horizontal overflow, and the Back to comparison link
  returned to the paired report. HTML-like model output was escaped.
- **Leaderboard:** The exact, server-rendered table remained available independently
  of the SVG chart. It showed **Unknown** for missing cost, **Frontier** and
  **Dominated** as text, and distinct square/circle chart markers.
- **Read-only:** All four views loaded with `DEMO_READ_ONLY=true`. The isolated
  SQLite database SHA-256 was unchanged before and after visiting them:
  `b5a7162ad2a917a8df3766ece37ee454f0c2c49de430ba778a5f504130e3f7b8`.

No browser defect was observed. This accepts Phase 4 after the implementation merge
in PR #20; it does not validate a live Supabase deployment or a paid LLM provider.
