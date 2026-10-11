import { Navigate, Route, Routes } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { RunDetailPage } from '@/pages/RunDetailPage'
import { RunListPage } from '@/pages/RunListPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<RunListPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="compare" element={<PlaceholderPage title="Compare runs" />} />
        <Route path="calibration" element={<PlaceholderPage title="Calibration" />} />
        <Route path="leaderboard" element={<PlaceholderPage title="Leaderboard" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
