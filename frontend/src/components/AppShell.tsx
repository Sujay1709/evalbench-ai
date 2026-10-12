import { NavLink, Outlet } from 'react-router'

const links = [
  { to: '/', label: 'Runs', end: true },
  { to: '/compare', label: 'Compare runs' },
  { to: '/calibration', label: 'Calibration' },
  { to: '/leaderboard', label: 'Leaderboard' },
]

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:bg-card focus:px-4 focus:py-2"
      >
        Skip to content
      </a>
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-4 py-3 md:px-8">
        <NavLink to="/" className="flex items-center gap-2 text-foreground no-underline" aria-label="EvalBench home">
          <span className="flex size-8 items-center justify-center rounded-md bg-primary font-mono text-sm font-semibold text-primary-foreground">
            E
          </span>
          <span className="font-medium">EvalBench</span>
        </NavLink>
        <nav aria-label="Main navigation" className="flex flex-wrap gap-1">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm no-underline ${
                  isActive ? 'bg-secondary text-foreground' : 'text-accent-soft hover:bg-secondary'
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">
        <Outlet />
      </main>
      <footer className="border-t border-border px-4 py-4 text-sm text-muted-foreground md:px-8">
        Reproducible evaluation. Measurable decisions. No API key required.
      </footer>
    </div>
  )
}
