import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TabBar, { type Tab } from './components/TabBar'
import UsageTab from './components/UsageTab'
import SettingsPage from './components/SettingsPage'
import './theme.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
})

function parseStartParam(): Tab {
  const tg = window.Telegram?.WebApp
  const param = tg?.initDataUnsafe?.start_param
  if (param === 'settings' || param === 'usage') {
    return param
  }
  return 'settings'
}

function AppContent() {
  const [tab, setTab] = useState<Tab>(parseStartParam)

  return (
    <div style={{ paddingBottom: 64 }}>
      {tab === 'usage' && <UsageTab />}
      {tab === 'settings' && <SettingsPage />}
      <TabBar active={tab} onChange={setTab} />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  )
}
