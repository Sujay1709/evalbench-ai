# EvalBench frontend

Read-only React/Vite shell for the Flask API. Jinja remains the default UI until
comparison, calibration, and leaderboard pages reach documented keyboard and
mobile parity.

## Local development

With the Flask app on port 5000:

```bash
cd frontend
npm ci
npm test
npm run build
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:5000` and does not enable CORS.

## Opt-in production serving

Build the app, then set `FRONTEND_ENABLED=true`. Flask serves the contents of
`frontend/dist` at `/app/`. Without a build, that route returns 503.

## Tooling recorded by this slice

- Vite 8, React 19, TypeScript 6
- Tailwind CSS 4 via `@tailwindcss/vite`
- shadcn CLI 4 with the official Vite + Radix Nova init, then EvalBench tokens
  from `.ulpi/design/DESIGN.md`
- Vitest 5 and Testing Library for offline UI tests
