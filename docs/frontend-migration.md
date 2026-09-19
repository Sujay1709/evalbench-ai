# React/shadcn frontend migration sequence

Approved direction: adopt React/Vite with shadcn components in a **separate frontend
PR**, retaining Flask as the backend. This document is a migration plan, not an
implemented frontend or a reason to run `init` in the current Jinja project root.

## Sequence

1. Merge the database-integration PR and verify its hosted setup separately.
2. Complete the Phase 4 browser acceptance checklist; merged code alone is not
   evidence of responsive/keyboard acceptance.
3. Implement Phase 5's versioned rubric and structured judge-output contracts with
   offline fixtures. Keep judging logic independent of Flask and React.
4. Before the human-labeling UI slice, add a React/TypeScript/Vite app in `frontend/`
   and initialize shadcn there using the official Vite setup. Start with a read-only
   dashboard shell and one migrated run-detail page, behind a reversible opt-in.
5. Port comparisons and paired evidence only after keyboard, mobile, loading/error,
   escaping, and read-only behavior match the Jinja experience. Keep Jinja until
   feature parity is demonstrated.
6. Add authenticated annotation UX only with an explicit authorization/CSRF design.
   Supabase Auth is optional follow-up work, not enabled by database integration.

## Boundaries and acceptance

- Review and lock the existing product's design system with the UI/UX skills before
  implementing new screens. shadcn supplies components, not the visual identity.
- Flask returns explicit JSON response schemas; React never receives database
  credentials, privileged Supabase keys, or an unauthenticated model-call endpoint.
- Preserve shadcn's semantic controls, ARIA behavior, and focus management.
- Avoid raw HTML rendering of dataset/model content; treat it as untrusted text.
- Preserve development/holdout separation, exact paired evidence, unknown-cost
  disclosure, and text equivalents for charts.
- Start same-origin with a Vite development proxy and an intentional production
  asset build; do not add permissive CORS to avoid configuring deployment.
- Test on keyboard and at 375px/desktop; provide loading, empty, unavailable,
  incompatible-run, and validation-error states. Check contrast and reduced motion.
- Add frontend tests and build checks; keep all evaluation tests offline.

`npx shadcn@latest init` installs dependencies and modifies configuration. Run it
only inside the prepared React app; record the resolved tooling versions and
commit a lockfile. This backend PR intentionally adds no npm dependencies or UI
code, so the current local Flask application continues to work unchanged.

Sources: [shadcn Vite installation](https://ui.shadcn.com/docs/installation/vite)
and [shadcn CLI](https://ui.shadcn.com/docs/cli).
